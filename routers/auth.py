from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from config import COOKIE_NAME, COOKIE_MAX_AGE, APP_WIFI_SSID, APP_WIFI_PASS, APP_SERVER_IP, APP_DOMAIN
from services.auth import verify_password, sign_cookie
from services.rate_limit import limiter
from config import ROLE_ADMIN, ROLE_LEADER, ROLE_VOLUNTEER, ROLE_PERMANENT
import models

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _get_device_type(user_agent: str) -> str:
    """Определяет тип устройства по User-Agent."""
    if not user_agent:
        return "unknown"
    ua = user_agent.lower()
    if "mobile" in ua or "android" in ua or "iphone" in ua or "ipad" in ua:
        return "mobile"
    if "tablet" in ua:
        return "tablet"
    return "desktop"


def _log_login(db: Session, user_id: int, request: Request):
    """Записывает лог входа пользователя."""
    user_agent = request.headers.get("user-agent", "")
    # Client IP
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else None

    db.add(models.LoginLog(
        user_id=user_id,
        ip_address=ip,
        user_agent=user_agent,
        device_type=_get_device_type(user_agent),
    ))
    db.commit()


def _get_local_ip():
    """Определяет локальный IP адрес сервера."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@router.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    import base64, io
    wifi_ssid = APP_WIFI_SSID
    wifi_pass = APP_WIFI_PASS
    server_ip = APP_SERVER_IP or _get_local_ip()
    domain    = APP_DOMAIN or server_ip

    # Determine protocol from env (set by hotspot.py) or auto-detect
    import os
    protocol = os.environ.get('APP_PROTOCOL')
    if not protocol:
        cert_exists = os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'cert.pem'))
        key_exists = os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'key.pem'))
        protocol = "https" if (cert_exists and key_exists) else "http"
    
    site_url = f"{protocol}://{domain}:8000" if domain else ""

    wifi_qr_b64 = ""
    site_qr_b64 = ""

    try:
        import qrcode
        
        # WiFi QR (если есть SSID)
        if wifi_ssid:
            qr = qrcode.QRCode(box_size=4, border=2)
            qr.add_data(f"WIFI:T:WPA;S:{wifi_ssid};P:{wifi_pass};;")
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            wifi_qr_b64 = base64.b64encode(buf.getvalue()).decode()

        # Site QR (всегда показываем)
        qr2 = qrcode.QRCode(box_size=4, border=2)
        qr2.add_data(site_url or f"{protocol}://{server_ip}:8000")
        qr2.make(fit=True)
        img2 = qr2.make_image(fill_color="black", back_color="white")
        buf2 = io.BytesIO()
        img2.save(buf2, format="PNG")
        site_qr_b64 = base64.b64encode(buf2.getvalue()).decode()
    except Exception:
        pass

    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
        "wifi_ssid": wifi_ssid,
        "wifi_pass": wifi_pass,
        "server_ip": domain or server_ip,
        "wifi_qr_b64": wifi_qr_b64,
        "site_qr_b64": site_qr_b64,
        "site_url": site_url,
    })


@router.post("/login")
@limiter.limit("10/minute")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    # Determine protocol for error page
    import os
    cert_exists = os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'cert.pem'))
    key_exists = os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'key.pem'))
    # Determine protocol from env (set by hotspot.py) or auto-detect
    protocol = os.environ.get('APP_PROTOCOL')
    if not protocol:
        cert_exists = os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'cert.pem'))
        key_exists = os.path.exists(os.path.join(os.path.dirname(__file__), '..', 'key.pem'))
        protocol = "https" if (cert_exists and key_exists) else "http"
    
    user = db.query(models.User).filter_by(username=username, is_active=True).first()
    if not user or not verify_password(password, user.password_hash):
        ip = _get_local_ip()
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Неверный логин или пароль",
                "wifi_ssid": APP_WIFI_SSID,
                "wifi_pass": APP_WIFI_PASS,
                "server_ip": ip,
                "wifi_qr_b64": "",
                "site_qr_b64": "",
                "site_url": f"{protocol}://{ip}:8000",
            },
            status_code=401,
        )

    # Куда редиректить в зависимости от роли
    redirect_map = {
        ROLE_ADMIN:     "/admin",
        ROLE_LEADER:    "/leader",
        ROLE_VOLUNTEER: "/schedule",
        ROLE_PERMANENT: "/schedule",
    }
    # Логируем вход
    _log_login(db, user.id, request)

    target = redirect_map.get(user.role, "/schedule")
    response = RedirectResponse(target, status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=sign_cookie(user.id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response
