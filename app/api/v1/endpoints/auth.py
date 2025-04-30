# app/api/v1/endpoints/auth.py
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

# Core imports should still work
from app.core.security import (
    create_access_token,
    verify_password,
    get_current_active_user,
    get_password_hash,
)
from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES

# Model imports should still work
from app.models.token import Token
from app.models.user import User, UserRole # Import UserRole

# Router setup for authentication endpoints
router = APIRouter(
    # No prefix here, it will be added by the parent router in api.py
    tags=["Authentication"] # Tag for docs
)

# --- Endpoint /token ---
# Path will become /api/v1/auth/token
@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    # ... (logika login sama seperti sebelumnya) ...
    user = await User.find_one(User.username == form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # Add user role to token data if needed elsewhere, or keep it simple with 'sub'
    access_token = create_access_token(
        data={"sub": user.username},#, "role": user.role.value},
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- Endpoint /register ---
# Path will become /api/v1/auth/register
@router.post("/register", response_model=User.Response, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: User.Create):
    # ... (logika registrasi sama seperti sebelumnya) ...
    existing_user = await User.find_one(User.username == user_in.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    if user_in.email:
         existing_email = await User.find_one(User.email == user_in.email)
         if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

    hashed_password = get_password_hash(user_in.password)
    user_obj = User(
        username=user_in.username,
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hashed_password,
        disabled=False,
        role=UserRole.USER # Explicitly set role
    )
    await user_obj.insert()

    created_user = await User.find_one(User.username == user_in.username)
    if not created_user:
         raise HTTPException(status_code=500, detail="Failed to retrieve created user")
    # Return created user data using the Response schema
    return User.Response.model_validate(created_user) # Pydantic V2 style


# --- Endpoint /users/me ---
# Path will become /api/v1/auth/users/me (or maybe move it to users.py?)
# Let's keep it here for now as it's closely tied to the logged-in user's token
@router.get("/users/me") # Tanpa response_model
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    print(f"--- Debug: Current User Object ---")
    print(current_user)
    print(f"--- Debug: User ID Type: {type(current_user.id)} ---")
    try:
        # Coba return dict sederhana
        return {
            "username": current_user.username,
            "role": current_user.role.value,
            "user_id_str": str(current_user.id) # Konversi manual ke string
         }
    except Exception as e:
         print(f"Error creating debug dict: {e}")
         raise # Biarkan error asli muncul jika terjadi di sini