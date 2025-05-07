# app/api/v1/endpoints/categories.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Path, Body, Query, Request
from bson import ObjectId
from loguru import logger
from datetime import datetime, timezone
from pydantic import ValidationError

# Import security dependency
from app.core.security import require_staff_or_admin, User

# Import models
from app.models.category import Category # Import Category
from app.models.item import Item # Import Item
from app.core.utils import get_next_sequence_value
# Import Rate Limiter
from app.core.rate_limiter import limiter

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

# --- Helper validate_category_response ---
def validate_category_response(cat_doc: Category) -> Category.Response:
    """Konversi manual ObjectId dan validasi ke Category.Response."""
    if not cat_doc: raise ValueError("Invalid category document")
    cat_id_log = str(getattr(cat_doc, 'id', 'N/A'))
    logger.debug(f"[{cat_id_log}] Validating category response...")
    try:
        cat_data = cat_doc.model_dump(mode='json', by_alias=True)
        if 'id' not in cat_data or not isinstance(cat_data['id'], str):
             _id = cat_data.get('_id') or getattr(cat_doc,'id', None)
             if _id: cat_data['id'] = str(_id)
             else: raise ValueError("Missing Category ID")
        # Cek field wajib lain
        if 'name' not in cat_data or not cat_data['name']: raise ValueError("Missing category name")
        if 'category_code' not in cat_data or not cat_data['category_code']: raise ValueError("Missing category code") # Asumsi wajib
        # ... (cek created_at, updated_at jika wajib di response) ...
        return Category.Response.model_validate(cat_data)
    except ValidationError as ve: raise HTTPException(status_code=500, detail=f"Validation error: {ve}") from ve
    except ValueError as verr: raise HTTPException(status_code=500, detail=f"Data error: {verr}") from verr
    except Exception as e: raise HTTPException(status_code=500, detail="Error preparing response.") from e

@router.post(
    "/",
    response_model=Category.Response,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_staff_or_admin)]
)
@limiter.limit("20/hour") 
async def create_category(
    request: RecursionError,
    category_in: Category.Create = Body(...), # Input tidak ada kode
    current_user: User = Depends(require_staff_or_admin)
):
    """Create a new category. Requires Admin or Staff role."""
    logger.info(f"User '{current_user.username}' attempting to create category: {category_in.name}")
    # --- (Logika generate category_code jika otomatis - dari contoh sebelumnya) ---
    # --- (Logika cek duplikat nama & kode - dari contoh sebelumnya) ---
    if await Category.find_one(Category.name == category_in.name): raise HTTPException(status_code=400, detail="Category name exists.")
    # Jika category_code di-generate otomatis atau di-input dari skema Create:
    generated_code = "" # Placeholder, ganti dengan logic Anda
    if hasattr(category_in, 'category_code') and category_in.category_code: # Jika dari input
        generated_code = category_in.category_code
        if await Category.find_one(Category.category_code == generated_code): raise HTTPException(status_code=400, detail="Category code exists.")
    else: # Jika digenerate
        # generated_code = await get_next_sequence_value("category_code_seq").zfill(3)
        # if await Category.find_one(Category.category_code == generated_code): raise HTTPException(status_code=500, detail="Generated code collision.")
        raise HTTPException(status_code=400, detail="Category code is required if not auto-generated.") # Atau generate di sini

    category_obj = Category(
        name=category_in.name,
        description=category_in.description,
        category_code=generated_code
        # Timestamps akan otomatis
    )
    try: await category_obj.insert()
    except Exception as e: raise HTTPException(status_code=500, detail="Failed to save category.") from e

    # Fetch ulang dari PRIMARY dan validasi
    created_category = await Category.find_one({"_id": category_obj.id})
    if not created_category: raise HTTPException(status_code=500, detail="Failed to retrieve created category.")
    return validate_category_response(created_category)


# --- GET / --- (List all categories)
@router.get(
    "/",
    response_model=List[Category.Response],
    summary="List All Categories (Admin/Staff)"
    # dependencies sudah di level router
)
@limiter.limit("60/minute")
async def read_categories(
    request: Request, # Untuk limiter
    skip: int = 0,
    limit: int = 100
):
    """Retrieve a list of all categories. Requires Admin or Staff role."""
    try:
        categories_docs = await Category.find_all(skip=skip, limit=limit).sort("+name").to_list()
        response_list: List[Category.Response] = []
        for cat_doc in categories_docs:
             try: response_list.append(validate_category_response(cat_doc))
             except Exception as val_err: logger.error(f"Skipping category {cat_doc.id} in list: {val_err}"); continue
        return response_list
    except Exception as e:
        logger.error(f"Error listing categories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving categories.")


# --- GET /{category_id} --- (Get a specific category)
@router.get(
    "/{category_id}",
    response_model=Category.Response,
    summary="Get Category Details (Admin/Staff)"
    # dependencies sudah di level router
)
@limiter.limit("120/minute")
async def read_category(
    request: Request, # Untuk limiter
    category_id: str = Path(..., description="The ID of the category to retrieve")
):
    """Retrieve details for a specific category by ID. Requires Admin or Staff role."""
    category = await get_category_or_404(category_id)
    return validate_category_response(category)


# --- PUT /{category_id} --- (Update a category)
@router.put(
    "/{category_id}",
    response_model=Category.Response,
    summary="Update Category (Admin/Staff)"
    # dependencies sudah di level router
)
@limiter.limit("30/hour")
async def update_category(
    request: Request, # Untuk limiter
    category_id: str = Path(...),
    category_in: Category.Update = Body(...), # Skema Update (tanpa kode jika tidak bisa diubah)
    current_user: User = Depends(require_staff_or_admin) # Untuk logging
):
    """Update category details (name, description). Category code is not updatable. Requires Admin/Staff."""
    logger.info(f"User '{current_user.username}' attempting to update category: {category_id}")
    category_to_update = await get_category_or_404(category_id)
    update_data = category_in.model_dump(exclude_unset=True)
    if not update_data: raise HTTPException(status_code=400, detail="No update data provided.")

    # Cek duplikasi nama jika nama diupdate
    if "name" in update_data and update_data["name"] != category_to_update.name:
        if await Category.find_one(Category.name == update_data["name"], Category.id != category_to_update.id):
            raise HTTPException(status_code=400, detail=f"Category name '{update_data['name']}' already exists.")
    # Cek duplikasi KODE jika kode diizinkan diupdate & diupdate (contoh sebelumnya)
    # if "category_code" in update_data and update_data["category_code"] != category_to_update.category_code: ...

    update_data["updated_at"] = datetime.now(timezone.utc)
    try: await category_to_update.update({"$set": update_data})
    except Exception as e: raise HTTPException(status_code=500, detail="Failed to update category.") from e

    updated_category = await Category.find_one({"_id": ObjectId(category_id)})
    if not updated_category: raise HTTPException(status_code=404, detail="Category not found after update.")
    return validate_category_response(updated_category)


# --- DELETE /{category_id} --- (Delete a category)
@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Category (Admin/Staff)"
    # dependencies sudah di level router
)
@limiter.limit("10/hour")
async def delete_category(
    request: Request, # Untuk limiter
    category_id: str = Path(...),
    current_user: User = Depends(require_staff_or_admin) # Untuk logging
):
    """Delete a category ONLY if it's not linked to any items. Requires Admin or Staff role."""
    logger.warning(f"User '{current_user.username}' attempting to delete category: {category_id}")
    category_to_delete = await get_category_or_404(category_id)

    # Pengecekan item
    try:
        if category_to_delete.id is None: raise ValueError("Category ID missing")
        item_count = await Item.find(Item.category.id == category_to_delete.id, {"is_active": True}).count() # Hitung hanya item aktif
        if item_count > 0:
            raise HTTPException(status_code=400, detail=f"Cannot delete category '{category_to_delete.name}' as it is linked to {item_count} active item(s).")
    except Exception as e: raise HTTPException(status_code=500, detail="Error checking item dependencies.") from e

    # Hapus
    try:
        delete_result = await category_to_delete.delete()
        if not delete_result or delete_result.deleted_count == 0: raise HTTPException(status_code=404, detail="Category found but not deleted.")
    except Exception as e: raise HTTPException(status_code=500, detail="Failed to delete category.") from e
    logger.info(f"Category '{category_to_delete.name}' (ID: {category_id}) deleted by user '{current_user.username}'.")
    return None