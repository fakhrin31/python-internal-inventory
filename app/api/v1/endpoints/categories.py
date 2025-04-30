# app/api/v1/endpoints/categories.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Path, Body
from bson import ObjectId
import logging
from datetime import datetime
from pydantic import ValidationError

# Import security dependency
from app.core.security import require_staff_or_admin, User

# Import models
from app.models.category import Category # Import Category
from app.models.item import Item # Import Item
from app.core.utils import get_next_sequence_value

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Categories"]
)

# --- Helper function get_category_or_404 (Tetap sama) ---
async def get_category_or_404(category_id: str) -> Category:
    if not ObjectId.is_valid(category_id):
        raise HTTPException(status_code=400, detail="Invalid category ID format.")
    try:
        category = await Category.find_one({"_id": ObjectId(category_id)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving category '{category_id}'.") from e
    if not category:
        raise HTTPException(status_code=404, detail=f"Category with ID '{category_id}' not found")
    return category


# --- POST /categories/ --- (Create Category - PERBAIKI RETURN)
# --- POST /categories/ --- (Create Category - Auto Code)
@router.post(
    "/",
    response_model=Category.Response,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_staff_or_admin)]
)
async def create_category(
    category_in: Category.Create = Body(...), # Input tidak ada kode
    current_user: User = Depends(require_staff_or_admin)
):
    """Create a new category with an automatically generated code."""
    # 1. Cek duplikasi nama
    if await Category.find_one(Category.name == category_in.name):
        raise HTTPException(status_code=400, detail=f"Category name '{category_in.name}' already exists.")

    # --- Generate Category Code ---
    try:
        # Gunakan counter global untuk kategori
        sequence_name = "category_code_seq"
        next_cat_number = await get_next_sequence_value(sequence_name)
        generated_code = str(next_cat_number).zfill(3) # Format 001, 002, dst.

        # Safety check (meskipun counter harusnya unik) - cek jika kode sudah dipakai
        # Ini seharusnya tidak terjadi jika counter bekerja benar
        if await Category.find_one(Category.category_code == generated_code):
             logger.error(f"Generated category code '{generated_code}' collision detected! Counter: {sequence_name}")
             raise HTTPException(status_code=500, detail="Category code generation conflict.")

    except Exception as e:
        logger.error(f"Failed to generate category code: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate category code.") from e
    # --- End Code Generation ---

    # 2. Buat objek Category, termasuk kode yang digenerate
    category_obj = Category(
        name=category_in.name,
        description=category_in.description,
        category_code=generated_code # Set kode di sini
        # Timestamps akan otomatis
    )

    # 3. Insert into DB
    try:
        await category_obj.insert()
        logger.info(f"Category '{category_obj.name}' (Code: {category_obj.category_code}) created by user '{current_user.username}'.")
    except Exception as e:
        # ... (error handling insert, cek duplicate name) ...
         if "duplicate key error" in str(e).lower() and "name" in str(e).lower():
              raise HTTPException(status_code=400, detail=f"Category name '{category_in.name}' already exists (race condition).") from e
         # Error duplicate code seharusnya ditangkap oleh safety check di atas
         logger.error(f"Database error inserting category '{category_in.name}': {e}", exc_info=True)
         raise HTTPException(status_code=500, detail="Failed to save category to database.") from e


    # 4. Fetch ulang & Return response (dengan konversi ObjectId)
    # Cari berdasarkan kode yang baru dibuat untuk memastikan
    created_category = await Category.find_one(Category.category_code == generated_code)
    try:
        # 1. Konversi ke Dict
        category_data = created_category.model_dump(by_alias=False)
        logger.debug(f"Raw category data after dump: {category_data}") # <-- Log data mentah

        # 2. Konversi ObjectId ke String 'id'
        category_id_obj = category_data.get('_id') # Ambil _id
        if category_id_obj and isinstance(category_id_obj, ObjectId):
            category_data['id'] = str(category_id_obj)
            # Anda bisa hapus _id asli jika perlu, tapi coba tanpa dulu
            # del category_data['_id']
            logger.debug(f"Converted ObjectId to string ID: {category_data['id']}")
        # Fallback jika ID ada di atribut .id (jarang terjadi setelah dump)
        elif hasattr(created_category, 'id') and created_category.id:
            category_data['id'] = str(created_category.id)
            logger.debug(f"Using string ID from attribute: {category_data['id']}")
        else:
            # Jika tidak ada ID sama sekali, ini error serius
            logger.error(f"CRITICAL: Missing ID field in fetched category data: {category_data}")
            raise ValueError("Missing ID field in fetched category data")

        # 3. PASTIKAN SEMUA TIPE DATA SESUAI SEBELUM VALIDASI
        # Pydantic V2 lebih ketat. Periksa tipe yang mungkin bermasalah.
        # 'name', 'category_code', 'description' seharusnya string/None
        # 'created_at', 'updated_at' HARUS objek datetime
        if 'created_at' in category_data and not isinstance(category_data['created_at'], datetime):
            logger.warning(f"created_at is not datetime: {type(category_data['created_at'])}. Attempting parse?")
            # Coba parsing jika perlu, atau biarkan validasi gagal
        if 'updated_at' in category_data and not isinstance(category_data['updated_at'], datetime):
            logger.warning(f"updated_at is not datetime: {type(category_data['updated_at'])}. Attempting parse?")

        # 4. Validasi dengan Skema Response
        logger.debug(f"Attempting to validate data with Category.Response: {category_data}")
        validated_response = Category.Response.model_validate(category_data)
        logger.debug(f"Validation successful. Returning response.")
        return validated_response

    except ValidationError as ve: # Tangkap ValidationError Pydantic
         logger.error(f"Pydantic validation failed preparing category response: {ve}", exc_info=True)
         logger.error(f"Data attempted validation: {category_data}") # Log data yang gagal
         # Kembalikan pesan error yang lebih spesifik jika bisa diambil dari 've'
         # detail_errors = ve.errors() # Dapatkan detail error Pydantic
         # raise HTTPException(status_code=500, detail={"message": "Validation error preparing response", "errors": detail_errors})
         raise HTTPException(status_code=500, detail="Validation error preparing category data for response.") from ve
    except Exception as e:
        # Tangkap error lain (misal, ValueError dari cek ID, error konversi tak terduga)
        logger.error(f"Generic error preparing created category response for '{created_category.name if created_category else 'N/A'}'", exc_info=True)
        raise HTTPException(status_code=500, detail="Error preparing category data for response.") from e

    # ==============================


# --- GET /categories/ --- (List Categories - PERBAIKI RETURN)
@router.get(
    "/",
    response_model=List[Category.Response],
    dependencies=[Depends(require_staff_or_admin)]
)
async def read_categories(skip: int = 0, limit: int = 100):
    """Retrieve a list of item categories."""
    try:
        # 1. Ambil dokumen Beanie
        categories_docs: List[Category] = await Category.find_all(skip=skip, limit=limit).sort("+name").to_list()
        # 2. Siapkan list hasil
        response_list: List[Category.Response] = []
        # 3. Loop, konversi manual, validasi
        for cat_doc in categories_docs:
            try:
                cat_data = cat_doc.model_dump(by_alias=False)
                if '_id' in cat_data and isinstance(cat_data['_id'], ObjectId):
                    cat_data['id'] = str(cat_data['_id'])
                elif hasattr(cat_doc, 'id') and cat_doc.id:
                     cat_data['id'] = str(cat_doc.id)
                else:
                     logger.warning(f"Category document missing ID: {cat_data.get('name', 'N/A')}")
                     continue
                validated_cat = Category.Response.model_validate(cat_data)
                response_list.append(validated_cat)
            except Exception as validation_error:
                cat_id_str = str(cat_doc.id) if hasattr(cat_doc, 'id') and cat_doc.id else "N/A"
                logger.error(f"Failed to validate category data for list response. Cat ID: {cat_id_str}. Error: {validation_error}. Raw Data: {cat_data}", exc_info=True)
                continue # Lewati kategori yang gagal validasi
        # 4. Kembalikan list hasil
        return response_list
    except Exception as e:
        logger.error(f"Error retrieving categories list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred while retrieving categories.") from e


# --- GET /categories/{category_id} --- (Get Category by ID - PERBAIKI RETURN)
@router.get(
    "/{category_id}",
    response_model=Category.Response,
    dependencies=[Depends(require_staff_or_admin)]
)
async def read_category(category_id: str = Path(...)):
    """Retrieve details for a specific category by its ID."""
    category = await get_category_or_404(category_id)
    # === BAGIAN RETURN DIPERBAIKI ===
    try:
        # Coba validasi langsung (mungkin berhasil di GET by ID)
        return Category.Response.model_validate(category)
    except Exception as e:
        logger.warning(f"Direct validation failed for category {category_id}, attempting manual conversion. Error: {e}")
        # Fallback ke konversi manual jika validasi langsung gagal
        try:
            category_data = category.model_dump(by_alias=False)
            if '_id' in category_data and isinstance(category_data['_id'], ObjectId):
                category_data['id'] = str(category_data['_id'])
            elif hasattr(category, 'id') and category.id:
                 category_data['id'] = str(category.id)
            else: raise ValueError("Missing ID")
            return Category.Response.model_validate(category_data)
        except Exception as final_e:
             logger.error(f"Manual conversion/validation failed for category ID '{category_id}'", exc_info=True)
             raise HTTPException(status_code=500, detail="Error preparing category data for response.") from final_e
    # ==============================


# --- PUT /categories/{category_id} --- (Update Category - PERBAIKI RETURN)
@router.put(
    "/{category_id}",
    response_model=Category.Response,
    dependencies=[Depends(require_staff_or_admin)]
)
async def update_category(
    category_id: str = Path(...),
    category_in: Category.Update = Body(...), # Skema Update sudah tidak ada category_code
    current_user: User = Depends(require_staff_or_admin)
):
    """Update category details (name, description). Category code cannot be changed."""
    category_to_update = await get_category_or_404(category_id)
    update_data = category_in.model_dump(exclude_unset=True) # Tidak akan ada category_code

    if not update_data: raise HTTPException(status_code=400, detail="No update data provided.")

    # Cek duplikasi NAMA jika nama diupdate
    if "name" in update_data and update_data["name"] != category_to_update.name:
        if await Category.find_one(Category.name == update_data["name"], Category.id != category_to_update.id):
            raise HTTPException(status_code=400, detail=f"Category name exists.")

    update_data["updated_at"] = datetime.now()
    try:
        await category_to_update.update({"$set": update_data})
        # ... logging ...
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update category.") from e

    # ... (fetch ulang dan return response) ...
    updated_category = await get_category_or_404(category_id)
    try:
        category_data = updated_category.model_dump(by_alias=False); category_data['id'] = str(category_data['_id'])
        return Category.Response.model_validate(category_data)
    except Exception as e: raise HTTPException(status_code=500, detail="Error preparing response.") from e
    # ==============================


# --- DELETE /categories/{category_id} --- (Delete Category - Tidak mengembalikan body)
@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_staff_or_admin)]
)
async def delete_category(
    category_id: str = Path(...),
    current_user: User = Depends(require_staff_or_admin)
):
    """Delete a category ONLY if it's not linked to any items."""
    category_to_delete = await get_category_or_404(category_id)
    # --- Pengecekan item ---
    try:
        if category_to_delete.id is None: raise ValueError("Category ID missing")
        item_count = await Item.find(Item.category.id == category_to_delete.id).count()
        if item_count > 0:
            raise HTTPException(status_code=400, detail=f"Cannot delete category linked to {item_count} item(s).")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error checking item dependencies.") from e
    # --- Hapus ---
    try:
        await category_to_delete.delete()
        logger.info(f"Category '{category_to_delete.name}' deleted by user '{current_user.username}'.")
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete category.") from e