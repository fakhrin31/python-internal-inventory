# app/core/availability.py
import logging
from datetime import datetime, timezone # Import timezone
from bson import ObjectId
from typing import Optional

from app.models.item import Item
from app.models.borrowing import Borrowing, BorrowingStatus

logger = logging.getLogger(__name__)

async def check_item_availability(
    item_id_str: str,
    requested_start_date: datetime,
    requested_end_date: datetime,
    requested_quantity: int, # Pastikan parameter ini ada
    session = None,
    exclude_borrowing_id: Optional[ObjectId] = None
) -> bool:
    """
    Checks if the requested_quantity of the item is available throughout
    the entire requested period [requested_start_date, requested_end_date).
    Considers item's current stock and SUM of quantities from overlapping bookings/loans.
    """
    # Pastikan tanggal aware UTC untuk perbandingan
    if requested_start_date.tzinfo is None: requested_start_date = requested_start_date.replace(tzinfo=timezone.utc)
    if requested_end_date.tzinfo is None: requested_end_date = requested_end_date.replace(tzinfo=timezone.utc)

    logger.debug(f"Checking availability for {requested_quantity} units of item {item_id_str} from {requested_start_date} to {requested_end_date}")
    if not ObjectId.is_valid(item_id_str): return False
    item_id = ObjectId(item_id_str)
    if requested_quantity <= 0: return False

    try:
        # 1. Get Item & Stok Awal
        item = await Item.find_one({"_id": item_id, "is_active": True}, session=session)
        if not item: return False
        current_available_stock = item.current_stock
        logger.debug(f"Item {item_id_str}: Current available stock = {current_available_stock}")

        # Cek awal jika stok fisik saja sudah tidak cukup
        if current_available_stock < requested_quantity:
             logger.info(f"Item {item_id_str} unavailable: Stock ({current_available_stock}) < requested ({requested_quantity}).")
             return False

        # 2. Hitung TOTAL QUANTITY yang sudah terikat pada periode overlap
        conflict_query = {
            "item.$id": item_id,
            "status": {"$in": [
                BorrowingStatus.BORROWED.value, BorrowingStatus.OVERDUE.value, BorrowingStatus.SCHEDULED.value
            ]},
            "due_date": {"$gt": requested_start_date},
            "borrowed_date": {"$lt": requested_end_date}
        }
        if exclude_borrowing_id:
            conflict_query["_id"] = {"$ne": exclude_borrowing_id}

        # --- PERUBAHAN LOGIKA: Gunakan Agregasi untuk SUM quantity ---
        pipeline = [
            {"$match": conflict_query},
            {"$group": {
                "_id": "$item.$id", # Group berdasarkan item (meski hanya ada 1 item di query ini)
                "total_committed_quantity": {"$sum": "$quantity"} # Jumlahkan field quantity
            }}
        ]
        aggregation_result = await Borrowing.get_motor_collection().aggregate(pipeline, session=session).to_list()

        total_quantity_on_loan_or_booked = 0
        if aggregation_result: # Jika ada hasil agregasi (ada konflik)
            total_quantity_on_loan_or_booked = aggregation_result[0].get("total_committed_quantity", 0)
        # -----------------------------------------------------------

        logger.debug(f"Item {item_id_str}: Total quantity already committed during overlap = {total_quantity_on_loan_or_booked}")

        # 3. Ketersediaan: Apakah (Stok Fisik - Total yg Sudah Terikat) >= Jumlah yg Diminta?
        effective_available = current_available_stock - total_quantity_on_loan_or_booked
        is_available = effective_available >= requested_quantity # <-- Perbandingan kunci

        logger.info(f"Availability check for {requested_quantity} units of item {item_id_str} "
                    f"[{requested_start_date}-{requested_end_date}]: "
                    f"Stock={current_available_stock}, CommittedQty={total_quantity_on_loan_or_booked}, "
                    f"EffectiveAvailable={effective_available}, SufficientForRequest={is_available}")
        return is_available

    except Exception as e:
        logger.error(f"Error during availability check for item {item_id_str}: {e}", exc_info=True)
        return False