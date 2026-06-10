"""
hotspot.py - HatiApp server launcher.
Podklyuchite noutbuk k WiFi routeru, zapustite etot fajl.
"""
import os, sys, subprocess, socket, time, argparse

PORT = 8000

def parse_args():
    parser = argparse.ArgumentParser(description='HatiApp Server Launcher')
    parser.add_argument('--http', action='store_true', help='Force HTTP mode (no SSL)')
    parser.add_argument('--https', action='store_true', help='Force HTTPS mode (requires cert.pem + key.pem)')
    return parser.parse_args()


def download_tailwind():
    static = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    os.makedirs(static, exist_ok=True)
    tw = os.path.join(static, "tailwind.min.js")
    if os.path.exists(tw):
        print("  [OK] Tailwind uzhe est.")
        return
    print("  Skachivanie Tailwind...")
    try:
        import urllib.request
        urllib.request.urlretrieve("https://cdn.tailwindcss.com", tw)
        print(f"  [OK] Skachan ({os.path.getsize(tw)//1024} KB)")
    except Exception as e:
        print(f"  [!] {e}")


def print_qr(data, label):
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=1, border=1)
        qr.add_data(data)
        qr.make(fit=True)
        print(f"\n  {label}:")
        qr.print_ascii(invert=True)
    except ImportError:
        print("  (pip install qrcode[pil])")
    except Exception as e:
        print(f"  QR error: {e}")


def get_local_ip():
    """IP ноутбука в локальной сети."""
    r = subprocess.run("ipconfig", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines = r.stdout.decode("cp866", errors="ignore").splitlines()
    for line in lines:
        if "IPv4" in line and "192.168." in line and "192.168.137" not in line:
            ip = line.split(":")[-1].strip()
            if ip:
                return ip
    for line in lines:
        if "IPv4" in line and "127.0.0.1" not in line and "169.254" not in line:
            ip = line.split(":")[-1].strip()
            if ip:
                return ip
    return socket.gethostbyname(socket.gethostname())


def _decode(data):
    """Пробуем несколько кодировок, возвращаем первую успешную."""
    for enc in ("utf-8", "cp866", "cp1251", "latin-1"):
        try:
            return data.decode(enc, errors="strict")
        except Exception:
            pass
    return data.decode("utf-8", errors="ignore")


def get_current_wifi():
    """Имя и пароль текущей WiFi сети."""
    r = subprocess.run("netsh wlan show interfaces", shell=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    text = _decode(r.stdout)
    ssid = None
    for line in text.splitlines():
        if "SSID" in line and "BSSID" not in line:
            ssid = line.split(":", 1)[-1].strip()
            if ssid:
                break
    if not ssid:
        return None, None

    r2 = subprocess.run(f'netsh wlan show profile name="{ssid}" key=clear',
                        shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    text2 = _decode(r2.stdout)

    # Windows выводит это поле по-разному в зависимости от языка и версии
    KEY_MARKERS = [
        "Key Content",           # EN
        "Содержимое ключа",      # RU вариант 1
        "Ключевое содержимое",   # RU вариант 2
        "Содержание ключа",      # RU вариант 3
        "Klucz",                 # PL (на всякий случай)
    ]
    password = None
    for line in text2.splitlines():
        for marker in KEY_MARKERS:
            if marker in line:
                password = line.split(":", 1)[-1].strip()
                break
        if password:
            break
    return ssid, password


def main():
    args = parse_args()
    
    print()
    print("=" * 44)
    print("  HatiApp Server")
    print("=" * 44)
    print()

    print("[1/3] Proverka fajlov...")
    download_tailwind()
    print()

    print("[2/3] Opredelenie seti...")
    server_ip = get_local_ip()
    wifi_ssid, wifi_pass = get_current_wifi()

    print(f"  IP v seti:  {server_ip}")
    if wifi_ssid:
        print(f"  WiFi set:   {wifi_ssid}")
    if wifi_pass:
        print(f"  Parol:      {wifi_pass}")
    else:
        print(f"  Parol:      [ne najden — нужны права администратора или netsh ne vydajot parol]")
    print()

    # Determine protocol
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cert_file = os.path.join(script_dir, "cert.pem")
    key_file = os.path.join(script_dir, "key.pem")
    cert_exists = os.path.exists(cert_file)
    key_exists = os.path.exists(key_file)
    
    if args.http:
        use_https = False
        protocol = "http"
        print("  [РЕЖИМ] Принудительный HTTP (--http)")
    elif args.https:
        if not (cert_exists and key_exists):
            print("  [ОШИБКА] Сертификаты не найдены! Нельзя запустить в HTTPS режиме.")
            print(f"  Ожидаются: {cert_file} и {key_file}")
            print("  Запустите generate_cert.py или используйте --http")
            input("\nНажмите Enter для выхода...")
            return
        use_https = True
        protocol = "https"
        print("  [РЕЖИМ] Принудительный HTTPS (--https)")
    else:
        # Auto-detect
        use_https = cert_exists and key_exists
        protocol = "https" if use_https else "http"
        if use_https:
            print("  [РЕЖИМ] Автоопределение: HTTPS (сертификаты найдены)")
        else:
            print("  [РЕЖИМ] Автоопределение: HTTP (сертификаты не найдены)")
    
    site_url = f"{protocol}://{server_ip}:{PORT}"

    os.environ.update({
        "APP_WIFI_SSID": wifi_ssid or "",
        "APP_WIFI_PASS": wifi_pass or "",
        "APP_SERVER_IP": server_ip,
        "APP_DOMAIN":    server_ip,
        "APP_PROTOCOL":  protocol,
    })

    print("[3/3] QR kody i instruktsiya:")
    print()

    # ШАГ 1 — WiFi: QR + текст рядом
    if wifi_ssid:
        print("  ШАГ 1 — Подключитесь к WiFi (отсканируйте QR или введите вручную):")
        wifi_qr_data = f"WIFI:T:WPA;S:{wifi_ssid};P:{wifi_pass or ''};;"\
                       if wifi_pass else f"WIFI:T:nopass;S:{wifi_ssid};P:;;"
        print_qr(wifi_qr_data, f"  WiFi: {wifi_ssid}")
        print(f"  ┌─────────────────────────────────────┐")
        ssid_pad = f"Сеть:   {wifi_ssid}"
        print(f"  │  {ssid_pad:<35}│")
        if wifi_pass:
            pass_pad = f"Пароль: {wifi_pass}"
            print(f"  │  {pass_pad:<35}│")
        else:
            print(f"  │  (сеть без пароля){'':<17}│")
        print(f"  └─────────────────────────────────────┘")
        print()

    # ШАГ 2 — URL сайта
    step = "2" if wifi_ssid else "1"
    print(f"  ШАГ {step} — Отсканируйте QR или откройте ссылку:")
    print_qr(site_url, f"  Открыть сайт: {site_url}")

    print()
    print(f"  Адрес для телефонов: {site_url}")
    print()
    
    if use_https:
        print("  [HTTPS] Сертификаты найдены — сервер запустится на HTTPS")
        print("  ⚠️  На телефонах Chrome покажет 'Not Secure' — нажмите")
        print("     'Дополнительные' → 'Перейти на сайт (небезопасно)'")
        print("  ⚠️  PWA (добавление на домашний экран + offline) работает")
        print("     только в HTTPS-режиме")
    else:
        print("  [HTTP] Без сертификатов — PWA offline недоступен")
        print("         (для HTTPS создайте cert.pem + key.pem)")
    print()
    print("Zapusk servera...")
    print("=" * 44)
    print()

    subprocess.Popen(
        f"timeout /t 2 /nobreak >nul && start {protocol}://localhost:8000",
        shell=True)

    uvicorn_cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", "0.0.0.0", "--port", str(PORT), "--loop", "asyncio"
    ]
    if use_https:
        uvicorn_cmd.extend(["--ssl-keyfile", key_file, "--ssl-certfile", cert_file])

    try:
        subprocess.run(
            uvicorn_cmd,
            env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"}
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()