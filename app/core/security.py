# app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Optional, List # Import List
import logging # Use logging

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from beanie.odm.operators.find.comparison import Eq # Import Eq for queries

# Import config variables directly
from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.dto.token import TokenData
# Import User model and UserRole Enum
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

# Konteks password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Skema OAuth2 - UPDATE tokenUrl
# The path is now relative to the root, including the API version prefix
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# --- Password Functions (verify_password, get_password_hash) ---
# ... (fungsi sama seperti sebelumnya) ...
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# --- Token Function (create_access_token) ---
# ... (fungsi sama seperti sebelumnya) ...
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- Get Current User Function (get_current_user) ---
async def get_current_user(
    request: Request, # Tambahkan request untuk akses state
    token: str = Depends(oauth2_scheme) # Token tetap didapat dari header
) -> User: # Return objek Beanie User Model
    """
    Gets the current user from the request state (set by AuthMiddleware)
    or decodes the token if state is not available.
    Raises credentials exception if user not found or token invalid.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    username: Optional[str] = getattr(request.state, "username", None)

    if not username: # Jika middleware tidak set username (misal error atau middleware tidak jalan)
        logger.warning("Username not found in request state, attempting token decode in dependency.")
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if username is None:
                raise credentials_exception
            # token_data = TokenData(username=username) # Tidak perlu TokenData lagi
        except JWTError:
            logger.warning("Token decode failed in get_current_user dependency.")
            raise credentials_exception
        except Exception as e:
             logger.error(f"Unexpected error decoding token in dependency: {e}")
             raise credentials_exception

    if not username: # Jika masih tidak ada username setelah semua usaha
         logger.error("Could not determine username from state or token.")
         raise credentials_exception

    # Cari user di DB berdasarkan username
    user = await User.find_one(Eq(User.username, username))
    if user is None:
        logger.warning(f"User '{username}' not found in database.")
        raise credentials_exception

    # Kembalikan objek Beanie User
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user) # Terima objek Beanie User
) -> User:
    """Checks if the retrieved user is active."""
    if current_user.disabled:
        logger.warning(f"Access denied for disabled user '{current_user.username}'.")
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# --- Fungsi require_role / require_roles tetap sama ---
# Mereka menerima user dari Depends(get_current_active_user)
def require_role(required_role: UserRole):
    async def role_checker(current_user: User = Depends(get_current_active_user)):        # ... (cek current_user.role) ...
        if current_user.role != required_role: ... # Raise 403
        return current_user
    return role_checker


# --- NEW: Role Checking Dependency ---
def require_role(required_role: UserRole):
    """
    Factory for a dependency that checks if the current user has the specific required role.
    """
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role != required_role:
            logger.warning(
                f"Forbidden: User '{current_user.username}' with role '{current_user.role.value}' "
                f"attempted action requiring role '{required_role.value}'."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required role: {required_role.value}"
            )
        return current_user
    return role_checker

def require_roles(required_roles: List[UserRole]):
    """
    Factory for a dependency that checks if the current user has one of the required roles.
    """
    async def roles_checker(current_user: User = Depends(get_current_active_user)):
        if current_user.role not in required_roles:
             logger.warning(
                f"Forbidden: User '{current_user.username}' with role '{current_user.role.value}' "
                f"attempted action requiring one of roles: {[r.value for r in required_roles]}."
            )
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {[r.value for r in required_roles]}"
             )
        return current_user
    return roles_checker

# Convenience dependencies for common roles
require_admin = require_role(UserRole.ADMIN)
require_staff_or_admin = require_roles([UserRole.ADMIN, UserRole.STAFF])