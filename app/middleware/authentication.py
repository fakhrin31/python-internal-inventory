# app/middleware/authentication.py
from typing import Optional, Tuple, List, Set, Callable, Awaitable
# ------------------------------------
from fastapi import Request, HTTPException, status, Depends
from fastapi.security.utils import get_authorization_scheme_param
# --- Import BaseHTTPMiddleware SAJA ---
from starlette.middleware.base import BaseHTTPMiddleware
# ------------------------------------
# Import Response untuk type hint return middleware
from starlette.responses import Response
from starlette.types import ASGIApp, Scope, Receive, Send
from loguru import logger
from jose import JWTError, jwt
from fastapi.responses import JSONResponse

# Import dari core/config
from app.core.config import SECRET_KEY, ALGORITHM


# Daftar path yang TIDAK memerlukan autentikasi
# Gunakan regex atau string matching sederhana
PUBLIC_PATHS: Set[str] = {
    "/",
    "/docs",
    "/openapi.json",
    "/redoc",
    # --- TAMBAHKAN PATH HEALTH CHECK ANDA DI SINI ---
    "/health",         # Jika path-nya /health
    "/health/db",      # Jika path-nya /health/db
    "/ping-mongodb",   # Jika path-nya persis seperti ini
    #-------------------------------------------------
    "/api/v1/auth/token",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
}

# ... (Helper is_public_path - Pastikan bisa handle path baru ini) ...
def is_public_path(path: str) -> bool:
    """Checks if the given path matches or starts with any public path prefix."""
    # Cek kecocokan persis dulu
    if path in PUBLIC_PATHS:
        return True
    # Cek prefix untuk dokumentasi
    if path.startswith("/docs") or path.startswith("/redoc"):
         return True
    # Cek prefix untuk health check jika ada sub-path (misal /health/live, /health/ready)
    if path.startswith("/health"): # Cukup cek prefix /health
         return True
    # --- Tambahkan prefix lain jika perlu ---
    return False

class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    # --- Gunakan Type Hint yang Benar untuk call_next ---
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response: # <-- Return type adalah Response Starlette
    # -------------------------------------------------
        path = request.url.path
        request_id = getattr(request.state, 'request_id', 'N/A')

        if is_public_path(path):
            logger.debug(f"RID:{request_id} Public path accessed: {path}. Skipping auth.")
            response = await call_next(request) # Panggil call_next
            return response # Kembalikan response

        # ... (Logika validasi token: get header, scheme/token check) ...
        authorization: Optional[str] = request.headers.get("Authorization")
        scheme, token = get_authorization_scheme_param(authorization or "")
        # Cek token Bearer
        if not authorization or scheme.lower() != "bearer" or not token:
            logger.warning(f"RID:{request_id} Auth failed: No valid Bearer token for protected path {path}.")
            return JSONResponse(
                 status_code=status.HTTP_401_UNAUTHORIZED,
                 content={"detail": "Not authenticated"},
                 headers={"WWW-Authenticate": "Bearer"},
            )

        # Decode & Validasi Token
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: Optional[str] = payload.get("sub")
            if username is None:
                logger.warning(f"RID:{request_id} Auth failed: 'sub' claim missing in token for path {path}.")
                raise JWTError("Username ('sub') missing in token payload.")

            # Set username di state untuk dependensi nanti
            request.state.username = username
            logger.debug(f"RID:{request_id} Auth successful for user '{username}' accessing protected path {path}.")

        except JWTError as e:
            logger.warning(f"RID:{request_id} Auth failed: Invalid token for path {path}. Error: {e}")
            return JSONResponse(
                 status_code=status.HTTP_401_UNAUTHORIZED,
                 content={"detail": f"Invalid token: {str(e)}"}, # Beri pesan error JWT
                 headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e: # Tangkap error tak terduga saat decode
            logger.error(f"RID:{request_id} Unexpected auth error for path {path}: {e}", exc_info=True)
            return JSONResponse(
                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                 content={"detail": "An internal error occurred during authentication."},
            )

        # Lanjutkan ke endpoint jika token valid
        response = await call_next(request)
        return response