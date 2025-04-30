# app/scheduler/jobs.py
import logging
from datetime import datetime, timezone
from beanie import init_beanie, Link # Import init_beanie
from bson import ObjectId

# Import model dan enum
from app.models.borrowing import Borrowing, BorrowingStatus
from app.models.item import Item
# Hapus StockTransaction jika tidak dipakai
from app.models.user import User

# Import helper availability
from app.core.availability import check_item_availability

# Import koneksi DB
from app.core.config import MONGODB_URL, DATABASE_NAME
import motor.motor_asyncio

logger = logging.getLogger("scheduler_jobs")

async def activate_pending_bookings():
    now_utc = datetime.now(timezone.utc)
    logger.info(f"Running activate_pending_bookings job at {now_utc}")
    client = None; processed=0; activated=0; failed=0; errors=0
    try:
        # ... (koneksi db, init beanie) ...
        client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]
        await init_beanie(...)

        # ... (Query scheduled_bookings) ...
        scheduled_bookings = await Borrowing.find(...).to_list()
        processed = len(scheduled_bookings)
        logger.info(f"Found {processed} SCHEDULED bookings ready for activation.")

        for booking in scheduled_bookings:
            # ... (validasi link item/borrower, get data booking) ...
            booking_id = booking.id
            item_link = booking.item
            if not (item_link and item_link.ref and item_link.ref.id): continue # Skip
            item_id_str = str(item_link.ref.id)
            item_name = item_link.ref.name or item_id_str
            due_date = booking.due_date
            if due_date.tzinfo is None: due_date = due_date.replace(tzinfo=timezone.utc)
            booking_quantity = booking.quantity or 1
            if booking_quantity <= 0: continue # Skip

            logger.info(f"Processing activation for booking {booking_id} (Item: {item_name}, Qty: {booking_quantity})")

            async with await client.start_session() as session:
                async with session.start_transaction():
                    activation_successful_in_db = False
                    activation_failed_due_to_unavailability = False
                    try:
                        # 1. Final Check Availability (OK)
                        is_still_available = await check_item_availability(
                            item_id_str, now_utc, due_date,
                            requested_quantity=booking_quantity,
                            session=session, exclude_borrowing_id=booking_id
                        )

                        if not is_still_available:
                            # ... (Log, ubah status CANCELLED, save, tandai failed) ...
                            logger.warning(...)
                            booking.status = BorrowingStatus.CANCELLED; booking.updated_at = now_utc; await booking.save(session=session)
                            activation_failed_due_to_unavailability = True

                        else: # Jika tersedia, lanjutkan aktivasi
                            # --- DEKLARASI item_in_txn SETELAH FIND ---
                            # 2. Fetch Item di dalam transaksi
                            item_in_txn = await Item.find_one(
                                {"_id": ObjectId(item_id_str), "is_active": True},
                                session=session
                            )
                            # -----------------------------------------

                            if not item_in_txn or item_in_txn.current_stock < booking_quantity:
                                 # ... (Log error, ubah status CANCELLED, save, tandai failed) ...
                                 logger.error(f"Activation failed for booking '{booking_id}': Item consistency error...")
                                 booking.status = BorrowingStatus.CANCELLED; booking.updated_at = now_utc; await booking.save(session=session)
                                 activation_failed_due_to_unavailability = True # Anggap gagal karena availability/consistency

                            else: # Jika item OK dan stok cukup
                                # 3. Update Item Stock
                                item_in_txn.current_stock -= booking_quantity # <-- Gunakan item_in_txn
                                item_in_txn.updated_at = now_utc
                                await item_in_txn.save(session=session) # <-- Gunakan item_in_txn

                                # 4. Update Borrowing Status
                                booking.status = BorrowingStatus.BORROWED
                                booking.updated_at = now_utc
                                await booking.save(session=session)

                                # 5. HAPUS Log StockTransaction

                                activation_successful_in_db = True # Tandai sukses DB

                    except Exception as job_exc:
                        logger.error(f"Error during activation transaction for booking {booking_id}.", exc_info=True)
                        errors += 1
                        # Jangan re-raise agar loop bisa lanjut, error sudah dicatat

                # --- End Transaction --- (Update counter)
                if activation_successful_in_db: activated += 1
                elif activation_failed_due_to_unavailability: failed += 1
                # Jika error di except, error_count sudah bertambah

    # ... (except outer, finally close client, logging summary) ...
    finally:
        if client: client.close(); logger.info("DB Connection closed for job.")
    logger.info(f"Job finished. Processed: {processed}, Activated: {activated}, Failed/Cancelled: {failed}, Errors: {errors}")