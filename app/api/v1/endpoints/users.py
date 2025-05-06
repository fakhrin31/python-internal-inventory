# app/api/v1/endpoints/users.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Path, Body, Query, Request
from bson import ObjectId
from loguru import logger
from datetime import datetime, timezone # Import datetime
from pydantic_core import ValidationError

from app.core.security import (
    get_password_hash,
    # get_current_active_user, # Tidak perlu jika hanya pakai require_admin
    require_admin,
    # require_staff_or_admin
    User, UserRole
)
from app.models.user import User, UserRole
from app.core.rate_limiter import limiter

router = APIRouter(
    tags=["Users - Admin"],
    dependencies=[Depends(require_admin)]
)

# --- Helper get_user_or_404 ---
# (Pastikan ini sudah benar: cek validitas ID, query by ObjectId, cek not found)
# Helper ini TIDAK secara default mengecek user.disabled, endpoint yg relevan yg cek
async def get_user_or_404(user_id: str) -> User:
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid user ID format.")
    try:
        # Cukup find_one, fetch_links tidak relevan untuk User saat ini
        user = await User.find_one({"_id": ObjectId(user_id)})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error retrieving user '{user_id}'.") from e
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID '{user_id}' not found")
    return user
async def get_user_or_404(user_id: str) -> User:
    if not ObjectId.is_valid(user_id): raise HTTPException(status_code=400, detail="Invalid user ID format.")
    try: user = await User.find_one({"_id": ObjectId(user_id)})
    except Exception as e: raise HTTPException(status_code=500, detail="DB error finding user.") from e
    if not user: raise HTTPException(status_code=404, detail=f"User with ID '{user_id}' not found")
    return user

# --- Helper validate_user_response (Mirip helper lain) ---
# Diperlukan jika response endpoint tidak secara otomatis divalidasi/dikonversi dengan benar
def validate_user_response(user_doc: User) -> User.Response:
    """Konversi manual ObjectId dan validasi ke User.Response."""
    if not user_doc: raise ValueError("Invalid user document")
    user_id_log = str(getattr(user_doc, 'id', 'N/A'))
    logger.debug(f"[{user_id_log}] Validating user response...")
    try:
        user_data = user_doc.model_dump(mode='json', by_alias=True)
        # Pastikan ID utama sudah string
        if 'id' not in user_data or not isinstance(user_data['id'], str):
             _id = user_data.get('_id') or getattr(user_doc,'id', None)
             if _id: user_data['id'] = str(_id)
             else: raise ValueError("Missing User ID")
        # Cek field wajib lain jika perlu (username, role, disabled, timestamps)
        if 'username' not in user_data or not user_data['username']: raise ValueError("Missing username")
        # ... cek field wajib lain ...
        validated_user = User.Response.model_validate(user_data)
        return validated_user
    except ValidationError as ve: raise HTTPException(status_code=500, detail=f"Validation error: {ve}") from ve
    except ValueError as verr: raise HTTPException(status_code=500, detail=f"Data error: {verr}") from verr
    except Exception as e: raise HTTPException(status_code=500, detail="Error preparing response.") from e


# --- GET / --- (List all users)
@router.get(
    "/",
    response_model=List[User.Response],
    summary="List All Users (Admin Only)"
    # Dependensi require_admin sudah di level router
)
# Tambahkan rate limit (contoh: 30 per menit)
@limiter.limit("30/minute")
async def read_users(
    request: Request, # Diperlukan oleh limiter
    skip: int = 0,
    limit: int = 100
):
    """Retrieve a list of all users. Requires Admin role."""
    try:
        users_docs = await User.find_all(skip=skip, limit=limit).sort("+username").to_list()
        # Gunakan helper validasi di loop
        response_list: List[User.Response] = []
        for user_doc in users_docs:
             try: response_list.append(validate_user_response(user_doc))
             except Exception as val_err: logger.error(f"Skipping user {user_doc.id} in list: {val_err}"); continue
        return response_list
    except Exception as e:
        logger.error(f"Error listing users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving users.")

# --- POST / --- (Create a user by Admin)
@router.post(
    "/",
    response_model=User.Response,
    status_code=status.HTTP_201_CREATED,
    summary="Create User (Admin Only)"
    # Dependensi require_admin sudah di level router
)
# Tambahkan rate limit (contoh: 10 per jam)
@limiter.limit("10/hour")
async def create_user_by_admin(
    request: Request, # Diperlukan oleh limiter
    user_in: User.AdminCreate = Body(...), # Gunakan skema AdminCreate
    # current_admin: User = Depends(require_admin) # Bisa didapat dari dependensi router
):
    """Create a new user with specified role and status. Requires Admin role."""
    logger.info(f"Admin attempting to create user: {user_in.username}")
    # --- (Logika cek duplikat username/email - sama) ---
    if await User.find_one(User.username == user_in.username): raise HTTPException(status_code=400, detail="Username exists.")
    if user_in.email and await User.find_one(User.email == user_in.email): raise HTTPException(status_code=400, detail="Email exists.")
    # --- (Logika hash password - sama) ---
    try: hashed_password = get_password_hash(user_in.password)
    except Exception as e: raise HTTPException(status_code=500, detail="Password processing failed.") from e
    # --- (Logika buat User object - sama) ---
    user_obj = User(**user_in.model_dump(exclude={"password"}), hashed_password=hashed_password)
    # --- (Logika insert - sama) ---
    try: await user_obj.insert()
    except Exception as e: raise HTTPException(status_code=500, detail="Failed to save user.") from e
    # --- (Logika fetch ulang & return pakai helper - sama) ---
    created_user = await User.find_one(User.username == user_in.username) # Baca dari primary
    if not created_user: raise HTTPException(status_code=500, detail="Failed to retrieve created user.")
    return validate_user_response(created_user)


# --- GET /{user_id} --- (Get a specific user)
@router.get(
    "/{user_id}",
    response_model=User.Response,
    summary="Get User Details (Admin Only)"
    # Dependensi require_admin sudah di level router
)
# Tambahkan rate limit (contoh: 60 per menit)
@limiter.limit("60/minute")
async def read_user(
    request: Request, # Diperlukan oleh limiter
    user_id: str = Path(..., description="The ID of the user to retrieve")
):
    """Retrieve details for a specific user by ID. Requires Admin role."""
    user = await get_user_or_404(user_id)
    # Gunakan helper validasi response
    return validate_user_response(user)


# --- PUT /{user_id} --- (Update a user)
@router.put(
    "/{user_id}",
    response_model=User.Response,
    summary="Update User (Admin Only)"
    # Dependensi require_admin sudah di level router
)
# Tambahkan rate limit (contoh: 20 per hour)
@limiter.limit("20/hour")
async def update_user(
    request: Request, # Diperlukan oleh limiter
    user_id: str = Path(...),
    user_in: User.AdminUpdate = Body(...), # Gunakan skema AdminUpdate
    # current_admin: User = Depends(require_admin) # Bisa didapat dari dependensi router
):
    """Update user details (email, name, password, role, disabled). Requires Admin role."""
    logger.info(f"Admin attempting to update user: {user_id}")
    user_to_update = await get_user_or_404(user_id)
    update_data = user_in.model_dump(exclude_unset=True)
    if not update_data: raise HTTPException(status_code=400, detail="No update data provided.")
    # --- (Logika cek email duplikat jika email diupdate - sama) ---
    if "email" in update_data and update_data["email"] is not None:
        if update_data["email"] != user_to_update.email:
             if await User.find_one(User.email == update_data["email"], User.id != user_to_update.id):
                 raise HTTPException(status_code=400, detail=f"Email exists.")
    # --- (Logika hash password baru jika password diupdate - sama) ---
    if "password" in update_data:
        if update_data["password"]:
            try: update_data["hashed_password"] = get_password_hash(update_data["password"])
            except Exception as e: raise HTTPException(status_code=500, detail="Password processing failed.") from e
        del update_data["password"]
    # --- (Set updated_at - sama) ---
    update_data["updated_at"] = datetime.now(timezone.utc)
    # --- (Lakukan update $set - sama) ---
    try: await user_to_update.update({"$set": update_data})
    except Exception as e: raise HTTPException(status_code=500, detail="Failed to update user.") from e
    # --- (Fetch ulang & return pakai helper - sama) ---
    updated_user = await User.find_one({"_id": ObjectId(user_id)}) # Baca dari primary
    if not updated_user: raise HTTPException(status_code=404, detail="User not found after update.")
    return validate_user_response(updated_user)


# --- PATCH /{user_id}/disable --- (Disable a user)
@router.patch(
    "/{user_id}/disable",
    # response_model=User.Response, # Ganti ke response simpel
    status_code=status.HTTP_200_OK, # 200 OK karena aksi berhasil (atau state sudah sesuai)
    summary="Disable User (Admin Only)"
    # Dependensi require_admin sudah di level router
)
# Tambahkan rate limit
@limiter.limit("30/hour")
async def disable_user(
    request: Request, # Diperlukan oleh limiter
    user_id: str = Path(...)
    # current_admin: User = Depends(require_admin) # Bisa didapat dari dependensi router
):
    """Mark a user as disabled (sets disabled=True). Requires Admin role."""
    logger.info(f"Admin attempting to disable user: {user_id}")
    user = await get_user_or_404(user_id)
    if not user.disabled:
        try:
            update_data = {"disabled": True, "updated_at": datetime.now(timezone.utc)}
            await user.update({"$set": update_data})
            logger.info(f"User '{user.username}' (ID: {user_id}) disabled.")
        except Exception as e: raise HTTPException(status_code=500, detail="Failed to disable user.") from e
    else: logger.info(f"User {user_id} already disabled.")
    # Kembalikan response sederhana
    return {"message": "User disabled successfully", "user_id": user_id, "disabled": True}


# --- PATCH /{user_id}/enable --- (Enable a user)
@router.patch(
    "/{user_id}/enable",
    # response_model=User.Response, # Ganti ke response simpel
    status_code=status.HTTP_200_OK,
    summary="Enable User (Admin Only)"
    # Dependensi require_admin sudah di level router
)
# Tambahkan rate limit
@limiter.limit("30/hour")
async def enable_user(
    request: Request, # Diperlukan oleh limiter
    user_id: str = Path(...)
    # current_admin: User = Depends(require_admin) # Bisa didapat dari dependensi router
):
    """Mark a user as enabled (sets disabled=False). Requires Admin role."""
    logger.info(f"Admin attempting to enable user: {user_id}")
    user = await get_user_or_404(user_id)
    if user.disabled:
        try:
            update_data = {"disabled": False, "updated_at": datetime.now(timezone.utc)}
            await user.update({"$set": update_data})
            logger.info(f"User '{user.username}' (ID: {user_id}) enabled.")
        except Exception as e: raise HTTPException(status_code=500, detail="Failed to enable user.") from e
    else: logger.info(f"User {user_id} already enabled.")
    # Kembalikan response sederhana
    return {"message": "User enabled successfully", "user_id": user_id, "disabled": False}


# --- DELETE /{user_id} --- (Delete a user)
@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete User (Admin Only)"
    # Dependensi require_admin sudah di level router
)
# Tambahkan rate limit
@limiter.limit("5/hour")
async def delete_user(
    request: Request, # Diperlukan oleh limiter
    user_id: str = Path(...),
    # Dapatkan current_admin dari dependensi router
    current_admin: User = Depends(require_admin)
):
    """Delete a user permanently. Requires Admin role."""
    logger.warning(f"Admin '{current_admin.username}' attempting to delete user: {user_id}")
    user_to_delete = await get_user_or_404(user_id)
    # --- (Logika safety check: self-delete, last admin - sama) ---
    if user_to_delete.id == current_admin.id: raise HTTPException(status_code=403, detail="Admins cannot delete themselves.")
    if user_to_delete.role == UserRole.ADMIN:
        admin_count = await User.find(User.role == UserRole.ADMIN).count()
        if admin_count <= 1: raise HTTPException(status_code=403, detail="Cannot delete the last admin.")
    # --- (Logika delete - sama) ---
    try:
        delete_result = await user_to_delete.delete()
        if not delete_result or delete_result.deleted_count == 0: raise HTTPException(status_code=404, detail="User found but not deleted.")
    except Exception as e: raise HTTPException(status_code=500, detail="Failed to delete user.") from e
    logger.info(f"User '{user_to_delete.username}' (ID: {user_id}) deleted by admin '{current_admin.username}'.")
    return None # 204 No Content