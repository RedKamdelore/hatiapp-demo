import os
import ssl
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

import models
from database import engine
from services.rate_limit import limiter
from routers import auth, schedule, leader, admin, profile, chat, sse, logs, slots


templates = Jinja2Templates(directory="templates")

models.Base.metadata.create_all(bind=engine)
Path("static/avatars").mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Расписание волонтёров")
app.state.limiter = limiter
app.mount("/static", StaticFiles(directory="static"), name="static")


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Запрещает HTTP-кэширование HTML-страниц — Service Worker управляет кэшем сам."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Skip caching headers for static assets (let Service Worker handle them)
        if request.url.path.startswith('/static/'):
            return response
        if isinstance(response, (HTMLResponse, RedirectResponse)):
            # Don't use no-store - it prevents Service Worker from caching!
            response.headers["Cache-Control"] = "no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


app.add_middleware(NoCacheMiddleware)
app.add_middleware(SlowAPIMiddleware)

app.include_router(auth.router)
app.include_router(schedule.router)
app.include_router(leader.router)
app.include_router(admin.router)
app.include_router(profile.router)
app.include_router(chat.router)
app.include_router(sse.router)
app.include_router(logs.router)
app.include_router(slots.router)


@app.get("/sw.js")
def serve_sw():
    """Отдаёт Service Worker с корневого пути для правильного scope."""
    return FileResponse("static/sw.js", media_type="application/javascript")


@app.exception_handler(401)
def unauthorized(request: Request, exc):
    return RedirectResponse("/")


@app.exception_handler(403)
def forbidden(request: Request, exc):
    return RedirectResponse("/")


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return RedirectResponse("/?error=too_many_requests", status_code=302)


@app.exception_handler(500)
@app.exception_handler(Exception)
def internal_error_handler(request: Request, exc: Exception):
    return templates.TemplateResponse("error.html", {
        "request": request,
        "status_code": 500,
        "title": "Ошибка сервера",
        "message": "Что-то пошло не так. Мы уже работаем над этим.",
    }, status_code=500)


# Auto-detect HTTPS certificates and run server accordingly
CERT_FILE = "cert.pem"
KEY_FILE = "key.pem"

if __name__ == "__main__":
    import uvicorn
    
    # Check for forced protocol from hotspot.py
    forced_protocol = os.environ.get('APP_PROTOCOL')
    
    if forced_protocol == 'http':
        print("🔓 HTTP mode (forced by --http)")
        uvicorn.run(app, host="0.0.0.0", port=8000)
    elif forced_protocol == 'https':
        if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
            print("🔒 HTTPS mode enabled (forced by --https)")
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(CERT_FILE, KEY_FILE)
            uvicorn.run(app, host="0.0.0.0", port=8000, ssl=ssl_context)
        else:
            print("❌ HTTPS mode requested but certificates not found!")
            print(f"   Expected: {CERT_FILE} and {KEY_FILE}")
            print("   Run: python generate_cert.py")
            sys.exit(1)
    else:
        # Auto-detect
        if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
            print("🔒 HTTPS mode enabled (cert.pem + key.pem found)")
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(CERT_FILE, KEY_FILE)
            uvicorn.run(app, host="0.0.0.0", port=8000, ssl=ssl_context)
        else:
            print("🔓 HTTP mode (no SSL certificates found)")
            uvicorn.run(app, host="0.0.0.0", port=8000)
