# app/core/rate_limiter.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

# Konfigurasi Limiter
# Opsi 1: In-Memory (untuk development/simpel)
limiter = Limiter(key_func=get_remote_address)
# Opsi 2: Redis (untuk production)
# import os
# redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# limiter = Limiter(key_func=get_remote_address, storage_uri=redis_url)

# Fungsi untuk mendapatkan state rate limiter untuk FastAPI
def get_rate_limiter() -> Limiter:
    return limiter

# Handler untuk RateLimitExceeded error
# (Anda bisa pindahkan ini ke main.py jika mau)
def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    # Anda bisa log exc.detail di sini
    from fastapi.responses import JSONResponse # Impor lokal
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )