# app/core/config.py
import os
import sys # Import sys untuk stderr
from dotenv import load_dotenv
from loguru import logger # Import logger Loguru
import logging
from pathlib import Path # Import Path

try:
    # Cara pathlib murni
    project_root = Path(__file__).resolve().parent.parent.parent
    dotenv_path = project_root / '.env' # Gunakan operator / untuk join path
    logger.debug(f"Calculated .env path using pathlib: {dotenv_path}")
except Exception as e:
    logger.error(f"Error calculating project root/dotenv path: {e}", exc_info=True)
    # Fallback jika __file__ tidak terdefinisi dengan benar (jarang terjadi)
    dotenv_path = Path(".env") # Asumsi .env ada di direktori kerja
    logger.warning(f"Using fallback .env path: {dotenv_path.resolve()}")

# --- Muat file .env JIKA ADA menggunakan metode Path ---
if dotenv_path.is_file(): # <-- Gunakan metode is_file() dari Path
    logger.info(f"Loading environment variables from: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path, override=True)
else:
    logger.warning(f".env file not found at {dotenv_path}. Relying on system environment variables.")

# --- Fungsi Intercept Handler (untuk Loguru menangkap log standar) ---
# (Pindahkan dari logging_config.py ke sini)
class InterceptHandler(logging.Handler):
    """Handler untuk mencegat log standar Python dan mengarahkannya ke Loguru."""
    def emit(self, record: logging.LogRecord) -> None:
        try: level = logger.level(record.levelname).name
        except ValueError: level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__: # Tambah cek 'frame'
            frame = frame.f_back
            depth += 1
        # Gunakan frame terakhir yang valid
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

# --- Fungsi Setup Logging (Pindahkan dari logging_config.py ke sini) ---
def setup_logging():
    """Konfigurasi Loguru untuk aplikasi."""
    # Baca konfigurasi dari environment variables atau set default
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = logging.getLevelName(log_level_name) # Dapatkan level numerik

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    log_file_path_str = os.getenv("LOG_FILE_PATH", "logs/app_{time:YYYY-MM-DD}.log")
    log_file_path = Path(log_file_path_str)
    log_rotation = os.getenv("LOG_ROTATION", "1 day")
    log_retention = os.getenv("LOG_RETENTION", "7 days")
    log_serialize_str = os.getenv("LOG_SERIALIZE", "False").lower()
    log_serialize = log_serialize_str == 'true'

    # --- Konfigurasi Loguru ---
    logger.remove() # Hapus handler default

    # Handler Console
    logger.add(
        sys.stderr,
        level=log_level,
        format=log_format,
        colorize=True,
    )

    # Handler File
    try:
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file_path,
            level=log_level,
            format=log_format,
            rotation=log_rotation,
            retention=log_retention,
            serialize=log_serialize,
            enqueue=True,
            backtrace=True,
            diagnose=True,
            encoding="utf-8"
        )
        logger.info(f"File logging enabled at: {log_file_path}")
    except Exception as e:
        logger.error(f"Failed to setup file logging at {log_file_path}: {e}")

    # --- Intercept Log Standar ---
    try:
        # Set level root logger ke 0 agar semua log diteruskan ke handler
        logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
        # Arahkan logger Uvicorn Access
        uvicorn_access = logging.getLogger("uvicorn.access")
        if uvicorn_access: # Cek jika logger ada
             uvicorn_access.handlers = [InterceptHandler()]
             uvicorn_access.propagate = False # Jangan teruskan ke root lagi
        # Arahkan logger FastAPI/Starlette lainnya (opsional, basicConfig mungkin cukup)
        for name in logging.root.manager.loggerDict:
            if name.startswith("uvicorn.") or name.startswith("fastapi.") or name.startswith("starlette."):
                 existing_logger = logging.getLogger(name)
                 existing_logger.handlers = [InterceptHandler()]
                 existing_logger.propagate = False # Hindari duplikasi jika root logger juga di-intercept

        logger.info("Standard library logging intercepted.")
    except Exception as e:
         logger.error(f"Failed to intercept standard logging: {e}")


    logger.info("Loguru logging setup complete.")
    logger.info(f"Logging level set to: {log_level_name} ({log_level})")

# --- Konfigurasi Aplikasi Lainnya ---

# Muat variabel dari .env (letakkan sebelum akses variabel env)
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env') # Path ke root/.env
if os.path.exists(dotenv_path):
    logger.debug(f"Loading environment variables from: {dotenv_path}") # Gunakan logger yg sudah ada
    load_dotenv(dotenv_path=dotenv_path)
else:
    logger.warning(f".env file not found at {dotenv_path}. Relying on system environment variables.")


# --- JWT Configuration ---
SECRET_KEY: str = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    # Log error sebelum raise agar tercatat
    logger.critical("FATAL: SECRET_KEY environment variable is not set.")
    raise ValueError("SECRET_KEY environment variable is not set.")

ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
try:
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
except ValueError:
    logger.warning(f"Invalid ACCESS_TOKEN_EXPIRE_MINUTES. Using default: 30.")
    ACCESS_TOKEN_EXPIRE_MINUTES = 30

# --- Database Configuration ---
MONGODB_URL: str = os.getenv("MONGODB_URL")
if not MONGODB_URL:
    logger.critical("FATAL: MONGODB_URL environment variable is not set.")
    raise ValueError("MONGODB_URL environment variable is not set.")

# Coba ekstrak nama DB (optional)
_default_db_name = "inventory_app_db" # Ganti default jika perlu
try:
    path_part = MONGODB_URL.split('/')[-1].split('?')[0]
    if path_part and '/' in MONGODB_URL: _default_db_name = path_part
except Exception: pass
DATABASE_NAME: str = os.getenv("DATABASE_NAME", _default_db_name)


# --- Log Konfigurasi yang Dimuat ---
# Gunakan logger Loguru yang sudah dikonfigurasi
# logger.info(f"SECRET_KEY loaded: {'*' * 5 if SECRET_KEY else 'None'}") # Hindari log secret
logger.info(f"JWT Algorithm: {ALGORITHM}")
logger.info(f"Access Token Expire Minutes: {ACCESS_TOKEN_EXPIRE_MINUTES}")
# logger.info(f"MongoDB URL: {MONGODB_URL[:15]}...") # Samarkan URL
logger.info(f"Database Name: {DATABASE_NAME}")