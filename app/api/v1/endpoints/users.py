# app/api/v1/endpoints/users.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Path, Body
from bson import ObjectId
import logging
from datetime import datetime # Import datetime

from app.core.security import (
    get_password_hash,
    # get_current_active_user, # Tidak perlu jika hanya pakai require_admin
    require_admin,
    # require_staff_or_admin
)
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Users - Admin"]
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

# --- (GET list /users/ dan POST /users/ - sudah diperbaiki sebelumnya) ---
# ... (kode GET /users/ dan POST /users/ dengan konversi manual di return) ...
@router.get("/", response_model=List[User.Response], dependencies=[Depends(require_admin)])
async def read_users(skip: int = 0, limit: int = 100):
    # ... (kode list user yang sudah diperbaiki) ...
    try:
        users_docs: List[User] = await User.find_all(skip=skip, limit=limit).sort("+username").to_list()
        response_list: List[User.Response] = []
        for user_doc in users_docs:
            try:
                user_data = user_doc.model_dump(by_alias=False)
                if '_id' in user_data and isinstance(user_data['_id'], ObjectId):
                    user_data['id'] = str(user_data['_id'])
                elif hasattr(user_doc, 'id') and user_doc.id:
                     user_data['id'] = str(user_doc.id)
                else:
                     logger.warning(f"User document missing ID field: {user_data.get('username', 'N/A')}")
                     continue
                validated_user = User.Response.model_validate(user_data)
                response_list.append(validated_user)
            except Exception as validation_error:
                user_id_str = str(user_doc.id) if hasattr(user_doc, 'id') and user_doc.id else "N/A"
                logger.error(f"Failed to validate user data for list response. User ID: {user_id_str}. Error: {validation_error}. Raw Data: {user_data}", exc_info=True)
                continue
        return response_list
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while retrieving users.") from e


@router.post("/", response_model=User.Response, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def create_user_by_admin(user_in: User.AdminCreate = Body(...)):
    # ... (kode create user yang sudah diperbaiki) ...
    if await User.find_one(User.username == user_in.username): raise HTTPException(status_code=400, detail=f"Username exists.")
    if user_in.email and await User.find_one(User.email == user_in.email): raise HTTPException(status_code=400, detail=f"Email exists.")
    try: hashed_password = get_password_hash(user_in.password)
    except Exception as e: raise HTTPException(status_code=500, detail="Password processing failed.") from e
    user_obj = User(**user_in.model_dump(exclude={"password"}), hashed_password=hashed_password) # Lebih ringkas
    try: await user_obj.insert()
    except Exception as e: raise HTTPException(status_code=500, detail="Failed to save user.") from e
    created_user = await User.find_one(User.username == user_in.username)
    if not created_user: raise HTTPException(status_code=500, detail="Failed to retrieve created user.")
    try:
        user_data = created_user.model_dump(by_alias=False)
        if '_id' in user_data and isinstance(user_data['_id'], ObjectId): user_data['id'] = str(user_data['_id'])
        elif hasattr(created_user, 'id') and created_user.id: user_data['id'] = str(created_user.id)
        else: raise ValueError("Missing ID")
        return User.Response.model_validate(user_data)
    except Exception as e: raise HTTPException(status_code=500, detail="Error preparing created user data for response.") from e


# --- GET /users/{user_id} --- (Get User by ID)
@router.get("/{user_id}", response_model=User.Response, dependencies=[Depends(require_admin)])
async def read_user(user_id: str = Path(...)):
    user = await get_user_or_404(user_id)
    try:
        # Coba validasi langsung dulu
        return User.Response.model_validate(user)
    except Exception as e:
        logger.warning(f"Direct validation failed for user {user_id}, attempting manual conversion. Error: {e}")
        # Fallback ke konversi manual jika validasi langsung gagal
        try:
            user_data = user.model_dump(by_alias=False)
            if '_id' in user_data and isinstance(user_data['_id'], ObjectId): user_data['id'] = str(user_data['_id'])
            elif hasattr(user, 'id') and user.id: user_data['id'] = str(user.id)
            else: raise ValueError("Missing ID")
            return User.Response.model_validate(user_data)
        except Exception as final_e:
            logger.error(f"Manual conversion/validation failed for user {user_id}: {final_e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error preparing user data for response.") from final_e


# --- PUT /users/{user_id} --- (Update User - DIPERBAIKI BAGIAN RETURN)
@router.put("/{user_id}", response_model=User.Response, dependencies=[Depends(require_admin)])
async def update_user(
    user_id: str = Path(...),
    user_in: User.AdminUpdate = Body(...) # Skema tidak ada created_at
):
    """Update user details. Requires Admin access."""
    user_to_update = await get_user_or_404(user_id)
    update_data = user_in.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="No update data provided.")

    # --- (Logika cek email, hash password baru) ---
    # ... (sama seperti sebelumnya) ...

    # Tambahkan update timestamp HANYA untuk updated_at
    update_data["updated_at"] = datetime.now() # Ini sudah benar

    # Lakukan update
    try:
        # Operasi $set tidak akan menyentuh created_at jika tidak ada di update_data
        await user_to_update.update({"$set": update_data})
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update user in database.") from e

    updated_user = await get_user_or_404(user_id)

    # --- Return Response (dengan konversi ObjectId) ---
    try:
        user_data = updated_user.model_dump(by_alias=False)
        if '_id' in user_data and isinstance(user_data['_id'], ObjectId): user_data['id'] = str(user_data['_id'])
        elif hasattr(updated_user, 'id') and updated_user.id: user_data['id'] = str(updated_user.id)
        else: raise ValueError("Missing ID after update")
        return User.Response.model_validate(user_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error preparing updated user data for response.") from e


# --- PATCH /users/{user_id}/disable --- (Exclude created_at from response)
@router.patch(
    "/{user_id}/disable",
    response_model=User.Response,
    # --- TAMBAHKAN INI ---
    response_model_exclude={"created_at"}, # Beritahu FastAPI untuk tidak menyertakan field ini di response
    # ---------------------
    dependencies=[Depends(require_admin)]
)
async def disable_user(user_id: str = Path(...)):
    """Mark a user as disabled. Excludes created_at from response."""
    # 1. Get user awal
    user = await get_user_or_404(user_id)
    operation_attempted = False

    # 2. Lakukan update HANYA jika user saat ini aktif
    if not user.disabled:
        operation_attempted = True
        try:
            update_payload = {"disabled": True, "updated_at": datetime.now()}
            await user.update({"$set": update_payload})
            logger.info(f"Update command sent to disable user '{user.username}' (ID: {user_id}).")
        except Exception as e:
            logger.error(f"Error during user update ($set) for disabling {user_id}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to disable user.") from e
    else:
        logger.info(f"User {user_id} is already disabled. No update attempted.")

    # --- Bagian Return: Selalu fetch ulang ---
    try:
        # 3. Fetch ulang user dari DB
        final_user_state = await get_user_or_404(user_id)
        # 4. (Opsional) Verifikasi state jika operasi dicoba
        if operation_attempted and not final_user_state.disabled:
             raise HTTPException(status_code=500, detail="State inconsistency after update attempt.")

        # 5. Konversi manual dan validasi response (INTERNAL validation masih pakai User.Response LENGKAP)
        user_data = final_user_state.model_dump(by_alias=False)
        if '_id' in user_data and isinstance(user_data['_id'], ObjectId): user_data['id'] = str(user_data['_id'])
        elif hasattr(final_user_state, 'id') and final_user_state.id: user_data['id'] = str(final_user_state.id)
        else: raise ValueError("Missing ID after disable operation and re-fetch")

        validated_response_object = User.Response.model_validate(user_data)
        # Kembalikan objek Pydantic yang sudah divalidasi.
        # FastAPI akan otomatis MENGECUALIKAN 'created_at' saat serialisasi ke JSON
        # karena ada response_model_exclude di decorator.
        return validated_response_object

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error preparing/validating final user state response for '{user_id}' after disable", exc_info=True)
        raise HTTPException(status_code=500, detail="Error preparing final user data for response.") from e


# --- PATCH /users/{user_id}/enable --- (Exclude created_at from response)
@router.patch(
    "/{user_id}/enable",
    response_model=User.Response,
    # --- TAMBAHKAN INI ---
    response_model_exclude={"created_at"}, # Beritahu FastAPI untuk tidak menyertakan field ini di response
    # ---------------------
    dependencies=[Depends(require_admin)]
)
async def enable_user(user_id: str = Path(...)):
    """Mark a user as enabled. Excludes created_at from response."""
    # 1. Get user awal
    user = await get_user_or_404(user_id)
    operation_attempted = False

    # 2. Lakukan update HANYA jika user saat ini disabled
    if user.disabled:
        operation_attempted = True
        try:
            update_payload = {"disabled": False,"updated_at": datetime.now()}
            await user.update({"$set": update_payload})
            logger.info(f"Update command sent to enable user '{user.username}' (ID: {user_id}).")
        except Exception as e:
            logger.error(f"Error during user update ($set) for enabling {user_id}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to enable user.") from e
    else:
        logger.info(f"User {user_id} is already enabled. No update attempted.")

    # --- Bagian Return: Selalu fetch ulang ---
    try:
        # 3. Fetch ulang user dari DB
        final_user_state = await get_user_or_404(user_id)
        # 4. (Opsional) Verifikasi state jika operasi dicoba
        if operation_attempted and final_user_state.disabled:
             raise HTTPException(status_code=500, detail="State inconsistency after update attempt.")

        # 5. Konversi manual dan validasi response (INTERNAL validation masih pakai User.Response LENGKAP)
        user_data = final_user_state.model_dump(by_alias=False)
        if '_id' in user_data and isinstance(user_data['_id'], ObjectId): user_data['id'] = str(user_data['_id'])
        elif hasattr(final_user_state, 'id') and final_user_state.id: user_data['id'] = str(final_user_state.id)
        else: raise ValueError("Missing ID after enable operation and re-fetch")

        validated_response_object = User.Response.model_validate(user_data)
        # Kembalikan objek Pydantic yang sudah divalidasi.
        # FastAPI akan otomatis MENGECUALIKAN 'created_at' saat serialisasi ke JSON.
        return validated_response_object

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error preparing/validating final user state response for '{user_id}' after enable", exc_info=True)
        raise HTTPException(status_code=500, detail="Error preparing final user data for response.") from e

