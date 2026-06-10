from pathlib import Path
from enum import Enum
from pydantic_settings import BaseSettings
from pydantic import Field


class UserRole(str, Enum):
    ADMIN = "admin"
    LEADER = "leader"
    VOLUNTEER = "volunteer"
    LOTOS = "lotos"
    PERMANENT = "permanent"


class Settings(BaseSettings):
    # --- Пути ---
    base_dir: Path = Path(__file__).resolve().parent
    
    # --- Безопасность ---
    secret_key: str = Field(..., description="Секретный ключ для подписи cookie")
    cookie_name: str = "session_token"
    cookie_max_age: int = 60 * 60 * 12  # 12 часов
    
    # --- База данных ---
    database_url: str = Field(default="", description="URL базы данных (оставьте пустым для SQLite)")
    
    # --- Роли ---
    role_admin: str = "admin"
    role_leader: str = "leader"
    role_volunteer: str = "volunteer"
    role_lotos: str = "lotos"
    role_permanent: str = "permanent"
    
    # --- Расписание ---
    schedule_file: Path = Field(default_factory=lambda: Path(__file__).resolve().parent / "schedule.txt")
    directions_file: Path = Field(default_factory=lambda: Path(__file__).resolve().parent / "directions.txt")
    times_file: Path = Field(default_factory=lambda: Path(__file__).resolve().parent / "times.txt")
    bookings_per_day: int = 2
    
    # --- WiFi (для QR на странице логина) ---
    app_wifi_ssid: str = ""
    app_wifi_pass: str = ""
    app_server_ip: str = ""
    app_domain: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()

# --- Обратная совместимость ---
BASE_DIR = settings.base_dir
DATABASE_URL = settings.database_url or f"sqlite:///{BASE_DIR}/app.db"
SECRET_KEY = settings.secret_key
COOKIE_NAME = settings.cookie_name
COOKIE_MAX_AGE = settings.cookie_max_age

ROLE_ADMIN = UserRole.ADMIN
ROLE_LEADER = UserRole.LEADER
ROLE_VOLUNTEER = UserRole.VOLUNTEER
ROLE_LOTOS = UserRole.LOTOS
ROLE_PERMANENT = UserRole.PERMANENT

SCHEDULE_FILE = settings.schedule_file
DIRECTIONS_FILE = settings.directions_file
TIMES_FILE = settings.times_file
BOOKINGS_PER_DAY = settings.bookings_per_day

APP_WIFI_SSID = settings.app_wifi_ssid
APP_WIFI_PASS = settings.app_wifi_pass
APP_SERVER_IP = settings.app_server_ip
APP_DOMAIN = settings.app_domain
