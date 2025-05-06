# app/api/v1/endpoints/items.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Path, Body, Query
from bson import ObjectId
import logging
from datetime import datetime, timezone
import uuid
from pydantic import ValidationError, BaseModel # <-- Tambahkan BaseModel
from beanie import Link
from pymongo import ReadPreference

# Import security dependency
from app.core.security import require_staff_or_admin, User # (Asumsi get_current_active_user ada jika perlu auth umum)

# Import models and schemas
from app.models.item import Item # Item sudah termasuk skema nested-nya
from app.models.category import Category
from app.models.borrowing import Borrowing, BorrowingStatus # <-- Tambahkan import Borrowing

# Helper dari categories endpoint
from app.api.v1.endpoints.categories import get_category_or_404
from app.core.utils import get_next_sequence_value

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Items"]
)

async def get_item_or_404(item_id: str) -> Item:
    """
    Retrieves an ACTIVE item by its string ObjectId.
    Raises 404 if not found, invalid format, or if item is inactive.
    """
    if not ObjectId.is_valid(item_id):
        logger.warning(f"Invalid ObjectId format for item: {item_id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item ID format.")
    try:
        # Cari berdasarkan ID dan pastikan aktif
        item = await Item.find_one({"_id": ObjectId(item_id), "is_active": True}, fetch_links=True)
    except Exception as e:
        logger.error(f"Error finding item by ID '{item_id}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error retrieving item '{item_id}'.") from e

    if not item: # find_one mengembalikan None jika tidak ditemukan ATAU tidak aktif
        logger.info(f"Active item lookup failed for ID '{item_id}'.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active item with ID '{item_id}' not found."
        )
    return item
# -----------------------------------------------------------------------

# --- Fungsi Helper untuk Konversi dan Validasi Item Response (Tetap sama) ---
def validate_item_response(item_doc: Item) -> Item.Response:
    """Konversi manual ObjectId dan validasi ke Item.Response."""
    # ... (kode helper validate_item_response dari contoh sebelumnya) ...
    if not item_doc: raise ValueError("Invalid item document provided")
    try:
        item_data = item_doc.model_dump(by_alias=False)
        if '_id' in item_data and isinstance(item_data['_id'], ObjectId): item_data['id'] = str(item_data['_id'])
        elif hasattr(item_doc, 'id') and item_doc.id: item_data['id'] = str(item_doc.id)
        else: raise ValueError("Missing Item ID")

        if 'category' in item_data and isinstance(item_data['category'], dict):
            cat_data = item_data['category']
            if '_id' in cat_data and isinstance(cat_data['_id'], ObjectId): cat_data['id'] = str(cat_data['_id'])
            elif 'id' in cat_data and isinstance(cat_data.get('id'), ObjectId): cat_data['id'] = str(cat_data['id'])
            elif isinstance(item_doc.category, Link) and item_doc.category.ref: cat_data['id'] = str(item_doc.category.ref.id)

        validated_item = Item.Response.model_validate(item_data)
        return validated_item
    except ValidationError as ve:
        item_id_str = item_data.get('id', 'N/A') if 'item_data' in locals() else "UNKNOWN"
        logger.error(f"Pydantic validation failed for item {item_id_str}: {ve}. Data: {item_data}", exc_info=True)
        raise HTTPException(status_code=500, detail="Validation error preparing item data for response.") from ve
    except Exception as e:
        item_id_str = item_data.get('id', 'N/A') if 'item_data' in locals() else "UNKNOWN"
        logger.error(f"Generic error preparing item response for item {item_id_str}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error preparing item data for response.") from e


# --- POST /items/ --- (Create Item - Lengkapi pembuatan item_obj)
@router.post(
    "/",
    response_model=Item.Response,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_staff_or_admin)]
)
async def create_item(
    item_in: Item.Create = Body(...),
    current_user: User = Depends(require_staff_or_admin)
):
    """Create item with auto SKU: [CATCODE]-[UUID6]-[PER_CAT_SEQ]."""
    # 1. Validate Category ID and get Category Object
    category_obj = await get_category_or_404(item_in.category_id)

    # 2. --- Generate SKU (Contoh KODEKAT-UUID6) ---
    #    (Jika pakai counter per kategori, pastikan get_next_sequence_value diimpor dan dipanggil)
    if not category_obj.category_code:
        raise HTTPException(status_code=500, detail=f"Category '{category_obj.name}' missing code.")

    generated_sku = None
    max_retries = 5
    for _ in range(max_retries):
        # Ganti bagian ini jika pakai counter sekuensial
        uuid_part = str(uuid.uuid4()).upper()[:6]
        # item_seq_str = str(await get_next_sequence_value(f"item_seq_{category_obj.category_code}")).zfill(4)
        # potential_sku = f"{category_obj.category_code}-{uuid_part}-{item_seq_str}"
        potential_sku = f"{category_obj.category_code}-{uuid_part}" # Contoh tanpa sequence

        if not await Item.find_one(Item.sku == potential_sku):
            generated_sku = potential_sku
            break
    if not generated_sku:
        raise HTTPException(status_code=500, detail="Failed to generate unique SKU.")
    # --- End SKU Generation ---

    # 3. Create Item object - LENGKAPI
    # Ambil semua field dari input KECUALI category_id dan initial_stock
    # karena itu akan ditangani secara terpisah
    item_data_to_create = item_in.model_dump(exclude={"category_id", "initial_stock"})

    item_obj = Item(
        **item_data_to_create,      # Masukkan name, description, price, image_url, location_*
        sku=generated_sku,          # SKU yang digenerate
        category=category_obj,      # Objek Category (Beanie akan membuat Link)
        current_stock=item_in.initial_stock, # Stok awal
        is_active=True,             # Pastikan aktif saat dibuat
        # created_at dan updated_at akan diisi oleh default_factory
    )

    # 4. Insert into DB
    try:
        await item_obj.insert()
        logger.info(f"Item '{item_obj.name}' (SKU: {item_obj.sku}) created by '{current_user.username}'.")
        # TODO: Create Initial Stock Transaction Record
    except Exception as e:
        # ... (error handling insert) ...
        raise HTTPException(status_code=500, detail="Failed to save item.") from e

    # 5. Fetch after insert
    created_item = await Item.find_one({"_id": item_obj.id}, fetch_links=True)
    if not created_item:
         raise HTTPException(status_code=500, detail="Failed to retrieve created item.")

    # 6. Return validated response using helper
    return validate_item_response(created_item)


# --- (Endpoint GET list, GET by ID, PUT, DELETE - Gunakan helper validate_item_response) ---
# ... (Pastikan semua return yang menggunakan Item.Response memanggil validate_item_response) ...

@router.get(
    "/{item_id}",
    response_model=Item.Response,
    dependencies=[Depends(require_staff_or_admin)] # <-- Tambahkan dependensi keamanan
)
async def read_item(
    item_id: str = Path(..., description="The ID of the item to retrieve") # <-- Path parameter sudah benar
):
    """Retrieve details for a specific active item by ID."""
    item = await get_item_or_404(item_id) # Helper sudah fetch_links dan cek active
    return validate_item_response(item) # Gunakan helper


# --- PUT /items/{item_id} --- (Update Item Metadata - LENGKAPI DECORATOR & PARAMETER)
@router.put(
    "/{item_id}",
    response_model=Item.Response,
    dependencies=[Depends(require_staff_or_admin)]
)
async def update_item(
    item_id: str = Path(..., description="The ID of the item to update"),
    item_in: Item.Update = Body(...), # Skema Update TIDAK punya SKU/stock
    current_user: User = Depends(require_staff_or_admin)
):
    """
    Update item details (name, desc, category, price, location, is_active).
    Stock level is NOT updated here. Category updated via ID.
    """
    item_to_update = await get_item_or_404(item_id)
    update_data = item_in.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="No update data provided.")

    # --- Penanganan Kategori (seperti sebelumnya, mengandalkan Beanie) ---
    if "category_id" in update_data:
        new_category_id_str = update_data.pop("category_id")
        logger.debug(f"Attempting to update category for item {item_id} to category ID {new_category_id_str}")
        if new_category_id_str:
             try:
                 new_category_obj = await get_category_or_404(new_category_id_str)
                 # Tetapkan objek Category Beanie, biarkan Beanie handle konversi ke Link/DBRef saat save/update
                 update_data["category"] = new_category_obj
                 logger.debug(f"Category object for update: {new_category_obj.id}")
             except HTTPException as e:
                 raise HTTPException(status_code=e.status_code, detail=f"Invalid new category_id: {e.detail}")
        else:
             # User mengirim null/kosong, abaikan perubahan kategori
             logger.warning(f"Received null/empty category_id for item update {item_id}. Category not changed.")
             if "category" in update_data: del update_data["category"] # Hapus key jika ada
    # -----------------------------------------------------------------

    # --- Set updated_at timestamp ---
    update_data["updated_at"] = datetime.now(timezone.utc)
    logger.debug(f"Final update payload for item {item_id}: {update_data}")

    # --- Lakukan update menggunakan $set ---
    try:
        # Panggil update pada instance. Jika gagal, akan raise Exception.
        # TIDAK perlu menangkap hasilnya atau cek modified_count.
        await item_to_update.update({"$set": update_data})

        logger.info(f"Item '{item_to_update.name}' (ID: {item_id}) update command sent by user '{current_user.username}'. Fields attempted: {list(update_data.keys())}")

    except Exception as e:
        logger.error(f"Database error updating item '{item_id}': {e}", exc_info=True)
        # Cek duplicate key error jika SKU diizinkan diupdate di masa depan
        # if "duplicate key error" ... raise HTTPException(409, ...)
        raise HTTPException(status_code=500, detail="Failed to update item in database.") from e

    # --- Fetch ulang + Validasi Response (seperti sebelumnya) ---
    try:
        logger.info(f"Fetching updated item state for {item_id} for response...")
        # Fetch ulang dengan links dari PRIMARY
        updated_item = await Item.find_one(
            {"_id": ObjectId(item_id)},
            fetch_links=True
        )
        if not updated_item:
            raise HTTPException(status_code=404, detail="Item not found after update (possible immediate deletion or error).") # Ubah jadi 404

        # Gunakan helper validasi item (buat jika belum ada, mirip validate_borrowing_response)
        # Asumsikan helper validate_item_response sudah ada
        return validate_item_response(updated_item)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error preparing response for updated item {item_id}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error preparing item data for response.") from e

# --- Helper validate_item_response (Contoh) ---
# (Harus dibuat mirip validate_borrowing_response, handle ID item & nested category ID)
def validate_item_response(item_doc: Item) -> Item.Response:
    if not item_doc: raise ValueError("Invalid item document")
    item_id_log = str(getattr(item_doc, 'id', 'N/A'))
    logger.debug(f"[{item_id_log}] Validating item response...")
    try:
        item_data = item_doc.model_dump(mode='json', by_alias=True)
        # Konversi/cek ID utama
        if 'id' not in item_data or not isinstance(item_data['id'], str):
             _id = item_data.get('_id') or getattr(item_doc,'id', None)
             if _id: item_data['id'] = str(_id)
             else: raise ValueError("Missing Item ID")
        # Konversi/cek ID & field wajib nested Category
        if 'category' in item_data and isinstance(item_data['category'], dict):
            cat_data = item_data['category']
            if 'id' not in cat_data or not isinstance(cat_data['id'], str):
                 cat_link = getattr(item_doc, 'category', None)
                 if isinstance(cat_link, Link) and cat_link.id: cat_data['id'] = str(cat_link.id)
                 else: raise ValueError("Missing nested category 'id'")
            if 'name' not in cat_data or not cat_data['name']: raise ValueError("Missing nested category 'name'")
            if 'category_code' not in cat_data: raise ValueError("Missing nested category 'category_code'") # Asumsi wajib ada
        elif 'category' not in item_data: raise ValueError("Missing required field 'category'")
        # Validasi Pydantic
        return Item.Response.model_validate(item_data)
    except Exception as e:
         logger.error(f"Error validating item response for {item_id_log}: {e}", exc_info=True)
         raise HTTPException(status_code=500, detail=f"Error preparing item response: {e}") from e



# --- GET /items/ --- (List Items - LENGKAPI PARAMETER & DECORATOR)
@router.get(
    "/",
    response_model=List[Item.Response],
    dependencies=[Depends(require_staff_or_admin)] # <-- Tambahkan dependensi keamanan
)
async def read_items(
    # Parameter Query untuk pagination dan filtering
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = Query(None, description="Filter by item name (case-insensitive partial match)"),
    sku: Optional[str] = Query(None, description="Filter by exact SKU"),
    category_id: Optional[str] = Query(None, description="Filter by exact Category ID (ObjectId string)"),
    location_cabinet: Optional[str] = Query(None, description="Filter by exact cabinet name/number"),
    location_shelf: Optional[str] = Query(None, description="Filter by exact shelf name/number"),
    include_inactive: bool = Query(False, description="Set to true to include inactive items")
    # Tambahkan dependensi current_user jika diperlukan untuk logika (misal otorisasi include_inactive)
    # current_user: User = Depends(require_staff_or_admin) # Uncomment jika perlu user di sini
):
    """
    Retrieve a list of items with optional filtering and pagination.
    Shows active items by default.
    """
    query_filters = {}
    if not include_inactive: query_filters["is_active"] = True
    # ... (bangun query_filters dari parameter - sama seperti sebelumnya) ...
    if name: query_filters["name"] = {"$regex": name, "$options": "i"}
    if sku: query_filters["sku"] = sku
    if category_id:
        if not ObjectId.is_valid(category_id): raise HTTPException(status_code=400, detail="Invalid category_id format.")
        query_filters["category.$id"] = ObjectId(category_id)
    if location_cabinet: query_filters["location_cabinet"] = location_cabinet
    if location_shelf: query_filters["location_shelf"] = location_shelf

    try:
        items_docs: List[Item] = await Item.find(
                query_filters,
                skip=skip,
                limit=limit,
                fetch_links=True
            ).sort("+name").to_list()

        response_list: List[Item.Response] = []
        for item_doc in items_docs:
             try:
                  validated_item = validate_item_response(item_doc) # Gunakan helper di loop
                  response_list.append(validated_item)
             except (HTTPException, ValueError, ValidationError) as val_err:
                  item_id_str = str(item_doc.id) if item_doc.id else "N/A"
                  logger.error(f"Skipping item {item_id_str} in list due to response prep error: {val_err}")
                  continue
        return response_list
    except Exception as e:
        logger.error(f"Error retrieving items list: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while retrieving items.") from e


# --- DELETE /items/{item_id} --- (Delete Item - Tidak perlu diubah)
@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT, # Tetap 204 karena aksi berhasil
    dependencies=[Depends(require_staff_or_admin)]
)
async def delete_item(
    item_id: str = Path(..., description="The ID of the item to mark as inactive"),
    current_user: User = Depends(require_staff_or_admin)
):
    """
    Mark an item as inactive (soft delete). Requires Admin or Staff role.
    The item remains in the database but will be hidden from default views.
    """
    # Gunakan find_one langsung, BUKAN get_item_or_404 agar bisa menonaktifkan item yang mungkin sudah tidak aktif (idempotent)
    # atau jika ingin error jika sudah tidak aktif, gunakan get_item_or_404 tapi tangani errornya.
    # Mari kita buat idempotent: jika sudah nonaktif, tidak melakukan apa-apa.

    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid item ID format.")

    try:
        item_to_inactivate = await Item.find_one({"_id": ObjectId(item_id)})
    except Exception as e:
         logger.error(f"Error finding item for inactivation '{item_id}': {e}")
         raise HTTPException(status_code=500, detail="Error retrieving item before inactivation.")

    if not item_to_inactivate:
        # Jika tidak ditemukan sama sekali, tetap 404
        raise HTTPException(status_code=404, detail=f"Item with ID '{item_id}' not found.")

    # --- Logika Soft Delete ---
    if item_to_inactivate.is_active: # Hanya update jika saat ini aktif
        # --- TODO (Opsional tapi bagus): Check dependencies sebelum menonaktifkan ---
        # Misalnya, cek peminjaman aktif untuk item ini
        # if await Borrowing.find_one(Borrowing.item.id == item_to_inactivate.id, Borrowing.status == BorrowingStatus.BORROWED):
        #    raise HTTPException(status_code=400, detail=f"Cannot deactivate item '{item_to_inactivate.name}' as it has active borrowings.")
        # -----------------------------------------------------------------------

        try:
            item_to_inactivate.is_active = False
            item_to_inactivate.updated_at = datetime.now() # Update timestamp
            await item_to_inactivate.save() # Simpan perubahan
            logger.info(f"Item '{item_to_inactivate.name}' (ID: {item_id}) marked as inactive by user '{current_user.username}'.")
        except Exception as e:
            logger.error(f"Database error inactivating item '{item_id}': {e}")
            raise HTTPException(status_code=500, detail="Failed to mark item as inactive.")
    else:
        # Jika sudah tidak aktif, tidak perlu melakukan apa-apa (idempotent)
        logger.info(f"Item '{item_id}' is already inactive. No action taken.")

    # Return 204 No Content menandakan operasi (atau state akhir) berhasil
    return None