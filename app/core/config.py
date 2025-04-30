# app/core/config.py
import os
from dotenv import load_dotenv
import logging # Gunakan logging untuk output yang lebih baik

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Muat variabel dari .env
# Cari file .env di direktori root proyek (satu level di atas 'app')
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')

if os.path.exists(dotenv_path):
    logger.info(f"Loading environment variables from: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    logger.warning(f".env file not found at {dotenv_path}. Relying on system environment variables.")

# --- JWT Configuration ---
SECRET_KEY: str = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    logger.error("FATAL: SECRET_KEY environment variable is not set. Application cannot start securely.")
    # Sebaiknya hentikan aplikasi jika kunci rahasia tidak ada
    raise ValueError("SECRET_KEY environment variable is not set.")

ALGORITHM: str = os.getenv("ALGORITHM", "HS256") # Default ke HS256 jika tidak diset

_expire_minutes_str = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30") # Ambil sebagai string, default 30
try:
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(_expire_minutes_str)
except ValueError:
    logger.warning(
        f"Invalid ACCESS_TOKEN_EXPIRE_MINUTES value ('{_expire_minutes_str}') in environment variables. "
        f"Using default: 30 minutes."
    )
    ACCESS_TOKEN_EXPIRE_MINUTES = 30

# --- Database Configuration ---
MONGODB_URL: str = os.getenv("MONGODB_URL")

# Ambil DATABASE_NAME dari env, gunakan hasil parse URL atau default jika tidak ada
DATABASE_NAME: str = os.getenv("DATABASE_NAME")

# --- Logging Konfigurasi yang Dimuat (Hati-hati dengan info sensitif) ---
logger.info(f"JWT Algorithm: {ALGORITHM}")
logger.info(f"Access Token Expire Minutes: {ACCESS_TOKEN_EXPIRE_MINUTES}")
# Hindari logging penuh URL DB di production jika memungkinkan
logger.info(f"MongoDB URL: Ending with ...{MONGODB_URL[-10:]}" if len(MONGODB_URL) > 10 else "MongoDB URL set.")
logger.info(f"Database Name: {DATABASE_NAME}")

# Tidak ada instance `settings` lagi, variabel di atas langsung diekspor oleh modul ini.