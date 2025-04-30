# app/api/v1/endpoints/reports.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from bson import ObjectId
import logging
from datetime import datetime, timezone, time # Import time

# Import security dependencies
from app.core.security import require_staff_or_admin, User

# Import models and schemas
from app.models.borrowing import Borrowing, BorrowingStatus # Import model utama & status enum
from app.models.borrowing import Borrowing # Re-import untuk akses skema nested jika perlu
from app.models.item import Item # Untuk lookup di agregasi
from app.models.enum import ReturnCondition # Untuk laporan kondisi
from app.models.report import ( # Import skema laporan
    TopBorrowedItem, TopBorrowedItemsReport,
    ReturnConditionSummary, ReturnConditionReport
)
# Import helper validasi response borrowing (jika diperlukan)
from app.api.v1.endpoints.borrowings import validate_borrowing_response

# Import DESCENDING jika belum
from pymongo import DESCENDING, ASCENDING

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
    dependencies=[Depends(require_staff_or_admin)] # Semua report butuh akses Staff/Admin
)

# --- 1. Laporan Peminjaman Aktif (Termasuk Overdue) ---
@router.get(
    "/active-borrowings",
    response_model=List[Borrowing.Response], # Kembalikan list detail borrowing
    summary="Get Active and Overdue Borrowings"
)
async def get_active_borrowings(
    skip: int = 0,
    limit: int = 50,
    # Bisa tambah filter lain jika perlu (user, item)
):
    """Retrieve a list of all currently active (borrowed) and overdue borrowings."""
    try:
        active_borrowings_docs = await Borrowing.find(
            {"status": {"$in": [BorrowingStatus.BORROWED.value, BorrowingStatus.OVERDUE.value]}},
            skip=skip,
            limit=limit,
            fetch_links=True,
            sort=[("due_date", ASCENDING)] # Urutkan berdasarkan yg paling dekat jatuh tempo
        ).to_list()

        # Gunakan helper validasi response
        response_list: List[Borrowing.Response] = []
        for doc in active_borrowings_docs:
             try: response_list.append(validate_borrowing_response(doc))
             except Exception as val_err: logger.error(f"Skipping borrowing {doc.id} in active list: {val_err}"); continue
        return response_list

    except Exception as e:
        logger.error(f"Error retrieving active borrowings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving active borrowings.")

# --- 2. Laporan Peminjaman Overdue ---
@router.get(
    "/overdue-borrowings",
    response_model=List[Borrowing.Response],
    summary="Get Overdue Borrowings"
)
async def get_overdue_borrowings(
    skip: int = 0,
    limit: int = 50,
):
    """
    Retrieve a list of borrowings that are past their due date but not yet returned.
    Checks status explicitly OR based on due_date. Using status is generally safer.
    """
    now_utc = datetime.now(timezone.utc)
    try:
        # Opsi 1: Berdasarkan status 'overdue' (jika ada proses yg update status ini)
        # query = {"status": BorrowingStatus.OVERDUE.value}

        # Opsi 2: Berdasarkan status 'borrowed' DAN due_date sudah lewat (lebih dinamis)
        query = {
            "status": BorrowingStatus.BORROWED.value,
            "due_date": {"$lt": now_utc}
        }

        overdue_docs = await Borrowing.find(
            query,
            skip=skip,
            limit=limit,
            fetch_links=True,
            sort=[("due_date", ASCENDING)] # Urutkan yg paling lama telat dulu
        ).to_list()

        response_list: List[Borrowing.Response] = []
        for doc in overdue_docs:
             try: response_list.append(validate_borrowing_response(doc))
             except Exception as val_err: logger.error(f"Skipping borrowing {doc.id} in overdue list: {val_err}"); continue
        return response_list

    except Exception as e:
        logger.error(f"Error retrieving overdue borrowings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving overdue borrowings.")


# --- 3. Laporan Riwayat Peminjaman per Item ---
@router.get(
    "/item-borrowing-history",
    response_model=List[Borrowing.Response],
    summary="Get Borrowing History for a Specific Item"
)
async def get_item_borrowing_history(
    item_id: str = Query(..., description="The ObjectId string of the item"),
    skip: int = 0,
    limit: int = 50,
    # Bisa tambah filter status atau tanggal jika perlu
):
    """Retrieve the full borrowing history for a specific item."""
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid item_id format.")
    item_oid = ObjectId(item_id)

    try:
        history_docs = await Borrowing.find(
            {"item.$id": item_oid},
            skip=skip,
            limit=limit,
            fetch_links=True,
            sort=[("borrowed_date", DESCENDING)] # Riwayat terbaru dulu
        ).to_list()

        response_list: List[Borrowing.Response] = []
        for doc in history_docs:
             try: response_list.append(validate_borrowing_response(doc))
             except Exception as val_err: logger.error(f"Skipping borrowing {doc.id} in item history: {val_err}"); continue
        return response_list

    except Exception as e:
        logger.error(f"Error retrieving borrowing history for item {item_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving item borrowing history.")


# --- 4. Laporan Riwayat Peminjaman per User ---
@router.get(
    "/user-borrowing-history",
    response_model=List[Borrowing.Response],
    summary="Get Borrowing History for a Specific User"
)
async def get_user_borrowing_history(
    user_id: str = Query(..., description="The ObjectId string of the user"),
    skip: int = 0,
    limit: int = 50,
    # Bisa tambah filter status atau tanggal jika perlu
):
    """Retrieve the full borrowing history for a specific user."""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user_id format.")
    user_oid = ObjectId(user_id)

    try:
        history_docs = await Borrowing.find(
            {"borrower.$id": user_oid},
            skip=skip,
            limit=limit,
            fetch_links=True,
            sort=[("borrowed_date", DESCENDING)]
        ).to_list()

        response_list: List[Borrowing.Response] = []
        for doc in history_docs:
             try: response_list.append(validate_borrowing_response(doc))
             except Exception as val_err: logger.error(f"Skipping borrowing {doc.id} in user history: {val_err}"); continue
        return response_list

    except Exception as e:
        logger.error(f"Error retrieving borrowing history for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving user borrowing history.")


# --- 5. Laporan Barang Sering Dipinjam (Top Items) ---
@router.get(
    "/top-borrowed-items",
    response_model=TopBorrowedItemsReport,
    summary="Get Top N Most Borrowed Items"
)
async def get_top_borrowed_items(
    limit: int = Query(10, ge=1, le=100, description="Number of top items to return"),
    start_date: Optional[datetime] = Query(None, description="Start date/time (ISO Format) for filtering period (optional)"),
    end_date: Optional[datetime] = Query(None, description="End date/time (ISO Format) for filtering period (optional)")
):
    """
    Retrieves the top N most frequently borrowed items within an optional date range.
    Counts based on borrowing records with status BORROWED, OVERDUE, RETURNED, or LOST.
    """
    # --- Bangun Pipeline Agregasi ---
    pipeline = []

    # Tahap $match (Filter Tanggal & Status Relevan)
    match_criteria = {
        # Status yang menandakan peminjaman benar-benar terjadi/dimulai
        "status": {"$in": [
            BorrowingStatus.BORROWED.value,
            BorrowingStatus.OVERDUE.value,
            BorrowingStatus.RETURNED.value,
            BorrowingStatus.LOST.value
            # Tidak termasuk SCHEDULED, CANCELLED, REJECTED, PENDING
        ]}
    }
    date_filter = {}
    if start_date: date_filter["$gte"] = start_date
    if end_date: date_filter["$lt"] = end_date
    if date_filter:
        # Filter berdasarkan tanggal peminjaman dimulai (atau tanggal dibuat?)
        match_criteria["borrowed_date"] = date_filter
        # Atau bisa juga filter berdasarkan created_at jika lebih relevan
        # match_criteria["created_at"] = date_filter
    pipeline.append({"$match": match_criteria})

    # Tahap $group (Hitung jumlah peminjaman per item)
    pipeline.append({
        "$group": {
            "_id": "$item.$id", # Group by item ID
            "borrow_count": {"$sum": 1} # Hitung jumlah dokumen per item
            # Jika ingin hitung per unit: "$sum": "$quantity"
        }
    })

    # Tahap $sort (Urutkan berdasarkan jumlah terbanyak)
    pipeline.append({"$sort": {"borrow_count": -1}}) # -1 untuk DESCENDING

    # Tahap $limit (Ambil N teratas)
    pipeline.append({"$limit": limit})

    # Tahap $lookup (Gabungkan dengan 'items' untuk detail)
    pipeline.append({
        "$lookup": {
            "from": Item.Settings.name,
            "localField": "_id",
            "foreignField": "_id",
            "as": "item_details"
        }
    })

    # Tahap $unwind atau $addFields (Ekstrak detail item)
    pipeline.append({
         "$unwind": {
             "path": "$item_details",
             "preserveNullAndEmptyArrays": True # Jaga jika item dihapus
         }
     })

    # Tahap $project (Format output akhir)
    pipeline.append({
        "$project": {
            "_id": 0,
            "item_id": {"$toString": "$_id"},
            "item_name": "$item_details.name", # Mungkin perlu handle jika item_details null
            "item_sku": "$item_details.sku",
            "borrow_count": "$borrow_count"
        }
    })

    # --- Eksekusi Agregasi ---
    try:
        collection = Borrowing.get_motor_collection()
        aggregation_result = await collection.aggregate(pipeline).to_list()
        logger.info(f"Top borrowed items report generated ({limit} items). Date range: {start_date}-{end_date}")

        # Validasi hasil dengan Pydantic (per item)
        top_items_list: List[TopBorrowedItem] = []
        for item_dict in aggregation_result:
             # Handle jika item dihapus (item_details akan null/kosong)
             if item_dict.get("item_name") is None:
                  item_dict["item_name"] = f"Deleted Item ({item_dict.get('item_id', 'N/A')})"
                  item_dict["item_sku"] = None

             try:
                 top_item = TopBorrowedItem.model_validate(item_dict)
                 top_items_list.append(top_item)
             except Exception as val_err:
                  logger.error(f"Skipping item in top borrowed report due to validation error: {val_err}. Data: {item_dict}")
                  continue

        report = TopBorrowedItemsReport(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            top_items=top_items_list
        )
        return report

    except Exception as e:
        logger.error(f"Database aggregation error for top borrowed items report: {e}\nPipeline: {pipeline}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating top borrowed items report.")


# --- 6. Laporan Kondisi Barang Saat Pengembalian ---
@router.get(
    "/return-conditions",
    response_model=ReturnConditionReport,
    summary="Get Summary of Return Conditions"
)
async def get_return_condition_report(
    start_date: datetime = Query(..., description="Start date/time (ISO Format) of the period (based on returned_date)"),
    end_date: datetime = Query(..., description="End date/time (ISO Format) of the period (based on returned_date)")
):
    """
    Generates a summary report of item conditions upon return within a specified date range.
    """
    if start_date >= end_date:
        raise HTTPException(status_code=400, detail="End date must be after start date.")

    # --- Bangun Pipeline Agregasi ---
    pipeline = []

    # Tahap $match (Filter berdasarkan status RETURNED dan rentang returned_date)
    pipeline.append({
        "$match": {
            "status": BorrowingStatus.RETURNED.value,
            "returned_date": {
                "$gte": start_date,
                "$lt": end_date
            },
            # Pastikan kondisi ada (opsional tapi bagus)
            "condition_on_return": {"$exists": True, "$ne": None}
        }
    })

    # Tahap $group (Kelompokkan berdasarkan kondisi dan hitung)
    pipeline.append({
        "$group": {
            "_id": "$condition_on_return", # Group berdasarkan nilai field condition_on_return
            "count": {"$sum": 1} # Hitung jumlah dokumen per kondisi
        }
    })

    # Tahap $project (Format ulang agar sesuai skema Pydantic)
    pipeline.append({
        "$project": {
            "_id": 0, # Hapus _id dari group stage
            "condition": "$_id", # Ganti nama _id menjadi condition
            "count": "$count"
        }
    })

    # Tahap $sort (Opsional, urutkan berdasarkan kondisi)
    pipeline.append({"$sort": {"condition": 1}})

     # --- Eksekusi Agregasi ---
    try:
        collection = Borrowing.get_motor_collection()
        aggregation_result = await collection.aggregate(pipeline).to_list()
        logger.info(f"Return condition report generated for {start_date} to {end_date}.")

        # Validasi hasil dengan Pydantic
        condition_summary_list: List[ReturnConditionSummary] = []
        for cond_dict in aggregation_result:
            try:
                # Pydantic akan otomatis validasi Enum jika tipe 'condition' benar
                summary_item = ReturnConditionSummary.model_validate(cond_dict)
                condition_summary_list.append(summary_item)
            except Exception as val_err:
                logger.error(f"Skipping condition summary due to validation error: {val_err}. Data: {cond_dict}")
                continue

        report = ReturnConditionReport(
            start_date=start_date,
            end_date=end_date,
            condition_summary=condition_summary_list
        )
        return report

    except Exception as e:
        logger.error(f"Database aggregation error for return condition report: {e}\nPipeline: {pipeline}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating return condition report.")