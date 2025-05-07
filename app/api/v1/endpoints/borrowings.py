# app/api/v1/endpoints/borrowings.py
from typing import List, Optional, Tuple # Import Tuple
from fastapi import APIRouter, Depends, HTTPException, status, Path, Body, Query, Request
from bson import ObjectId
from loguru import logger
from datetime import datetime, timezone
from pymongo import DESCENDING, ReadPreference, ReturnDocument # Import ReadPreference, ReturnDocument
from bson.dbref import DBRef

# Import security dependencies
from app.core.security import require_staff_or_admin, require_role, User, UserRole, get_current_active_user

# Import models and schemas
from app.models.borrowing import Borrowing, BorrowingStatus, ReturnCondition
from app.models.item import Item
from app.models.user import User as UserModel

# Import Pydantic ValidationError dan Link Beanie
from pydantic import ValidationError
from beanie import Link

# Import helper availability
from app.core.availability import check_item_availability
from app.api.v1.endpoints.items import get_item_or_404

# Import Rate Limiter
from app.core.rate_limiter import limiter

# Import Motor Client untuk akses langsung jika diperlukan
import motor.motor_asyncio

router = APIRouter(
    prefix="/borrowings",
    tags=["Borrowings & Bookings"]
)

# --- Helper validasi response borrowing ---
def validate_borrowing_response(borrow_doc: Borrowing) -> Borrowing.Response:
    borrow_id_log = str(getattr(borrow_doc, 'id', 'N/A'))
    logger.info(f"===> ENTERING validate_borrowing_response for {borrow_id_log}")
    if not borrow_doc:
         logger.error(f"[{borrow_id_log}] ERROR: Received None borrow_doc!")
         raise ValueError("Invalid borrowing document provided")

    try:
        # LANGKAH 1: Coba dump dulu
        logger.debug(f"[{borrow_id_log}] Attempting model_dump...")
        borrow_data = borrow_doc.model_dump(mode='json', by_alias=True)
        logger.info(f"[{borrow_id_log}] Successfully dumped data: {borrow_data}") # Ganti ke INFO agar pasti terlihat

        # LANGKAH 2: Validasi Manual Data Penting (Sebelum Pydantic)
        logger.debug(f"[{borrow_id_log}] Performing manual data checks...")
        # Cek ID Utama
        main_id = borrow_data.get('id')
        if not main_id or not isinstance(main_id, str):
             # Coba konversi fallback
             _id_obj = borrow_data.get('_id')
             if _id_obj and isinstance(_id_obj, (ObjectId, str)):
                  borrow_data['id'] = str(_id_obj)
                  logger.debug(f"[{borrow_id_log}] Manually converted main _id to id.")
             else:
                  raise ValueError("Missing or invalid main 'id' string after dump/fallback.")

        # Cek Item
        item_data = borrow_data.get('item')
        if not isinstance(item_data, dict): raise ValueError(f"Nested 'item' is not a dict: {type(item_data)}")
        item_id = item_data.get('id')
        if not item_id or not isinstance(item_id, str): raise ValueError("Missing or invalid nested item 'id' string")
        item_name = item_data.get('name')
        if not item_name or not isinstance(item_name, str): raise ValueError("Missing or invalid nested item 'name' string")
        logger.debug(f"[{borrow_id_log}] Manual check passed for nested item: id={item_id}, name={item_name}")

        # Cek Borrower
        borrower_data = borrow_data.get('borrower')
        if not isinstance(borrower_data, dict): raise ValueError(f"Nested 'borrower' is not a dict: {type(borrower_data)}")
        borrower_id = borrower_data.get('id')
        if not borrower_id or not isinstance(borrower_id, str): raise ValueError("Missing or invalid nested borrower 'id' string")
        borrower_username = borrower_data.get('username')
        if not borrower_username or not isinstance(borrower_username, str): raise ValueError("Missing or invalid nested borrower 'username' string")
        logger.debug(f"[{borrow_id_log}] Manual check passed for nested borrower: id={borrower_id}, username={borrower_username}")

        # Cek field wajib lainnya (contoh: quantity, status, dates)
        if not isinstance(borrow_data.get('quantity'), int) or borrow_data['quantity'] <= 0: raise ValueError("Missing or invalid 'quantity'")
        if not isinstance(borrow_data.get('status'), str) or borrow_data['status'] not in BorrowingStatus._value2member_map_: raise ValueError("Missing or invalid 'status'")
        if not isinstance(borrow_data.get('borrowed_date'), str): raise ValueError("Missing or invalid 'borrowed_date' (expected string from dump)") # Dump mode='json' -> string
        if not isinstance(borrow_data.get('due_date'), str): raise ValueError("Missing or invalid 'due_date'")
        if not isinstance(borrow_data.get('created_at'), str): raise ValueError("Missing or invalid 'created_at'")
        if not isinstance(borrow_data.get('updated_at'), str): raise ValueError("Missing or invalid 'updated_at'")
        logger.debug(f"[{borrow_id_log}] Manual check passed for other required fields.")

        # LANGKAH 3: Validasi Utama Pydantic
        logger.info(f"[{borrow_id_log}] Attempting final Pydantic validation...") # Ganti ke INFO
        validated_borrowing = Borrowing.Response.model_validate(borrow_data)
        logger.info(f"[{borrow_id_log}] Final Pydantic validation successful.") # Ganti ke INFO
        return validated_borrowing

    # ... (except blocks seperti sebelumnya, tangkap ValueError juga) ...
    except ValidationError as ve: # ... log ... ; 
        raise HTTPException(status_code=500, detail=...) from ve
    except ValueError as val_err: # Tangkap ValueError dari pengecekan manual
         logger.error(f"[{borrow_id_log}] Manual data validation failed: {val_err}", exc_info=True)
         raise HTTPException(status_code=500, detail=f"Invalid data encountered preparing response: {val_err}") from val_err
    except Exception as e: # ... log ... ; 
        raise HTTPException(status_code=500, detail=...) from e


# --- Helper untuk get booking PENDING ---
async def get_pending_booking_or_404(borrowing_id: str, session = None) -> Borrowing:
    if not ObjectId.is_valid(borrowing_id): raise HTTPException(status_code=400, detail="Invalid borrowing ID format.")
    booking = await Borrowing.find_one(
        {"_id": ObjectId(borrowing_id), "status": BorrowingStatus.PENDING_APPROVAL.value},
        session=session
    )
    if not booking:
        existing = await Borrowing.find_one({"_id": ObjectId(borrowing_id)}, session=session, projection={"status": 1})
        detail = "Booking request not found with pending status."
        if existing and "status" in existing: detail = f"Booking found but status is '{existing.status}', expected '{BorrowingStatus.PENDING_APPROVAL.value}'."
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return booking

# --- Helper untuk get booking SCHEDULED - Kembalikan Tuple ---
async def get_scheduled_booking_or_404(borrowing_id_str: str, session = None) -> Tuple[Borrowing, ObjectId]:
    if not ObjectId.is_valid(borrowing_id_str): raise HTTPException(status_code=400, detail="Invalid borrowing ID format.")
    borrowing_oid = ObjectId(borrowing_id_str)
    collection = Borrowing.get_motor_collection()
    raw_booking_data = await collection.find_one(
        {"_id": borrowing_oid, "status": BorrowingStatus.SCHEDULED.value}, session=session
    )
    if not raw_booking_data: raise HTTPException(status_code=404, detail="Scheduled booking not found.")

    item_ref = raw_booking_data.get("item"); item_id_obj: Optional[ObjectId] = None
    if isinstance(item_ref, DBRef): item_id_obj = item_ref.id
    elif isinstance(item_ref, dict) and isinstance(item_ref.get('$id'), ObjectId): item_id_obj = item_ref.get('$id')
    elif isinstance(item_ref, ObjectId): item_id_obj = item_ref
    if not item_id_obj: raise HTTPException(status_code=500, detail="Internal error: Corrupted item reference.")

    try: booking_obj = Borrowing.model_validate(raw_booking_data)
    except Exception as parse_error: raise HTTPException(status_code=500, detail="Internal error: Failed to process booking data.") from parse_error
    return booking_obj, item_id_obj

# --- Helper untuk get Borrowing yang BISA Dikembalikan ---
async def get_returnable_booking_or_404(borrowing_id_str: str, session=None) -> Tuple[Borrowing, ObjectId]:
    if not ObjectId.is_valid(borrowing_id_str): raise HTTPException(status_code=400, detail="Invalid borrowing ID format.")
    borrowing_oid = ObjectId(borrowing_id_str)
    collection = Borrowing.get_motor_collection()
    raw_booking_data = await collection.find_one(
        {"_id": borrowing_oid, "status": {"$in": [BorrowingStatus.BORROWED.value, BorrowingStatus.OVERDUE.value]}},
        session=session
    )
    if not raw_booking_data: raise HTTPException(status_code=404, detail="Borrowing record not found or not eligible for return.")

    item_ref = raw_booking_data.get("item"); item_id_obj: Optional[ObjectId] = None
    if isinstance(item_ref, DBRef): item_id_obj = item_ref.id
    elif isinstance(item_ref, dict) and isinstance(item_ref.get('$id'), ObjectId): item_id_obj = item_ref.get('$id')
    elif isinstance(item_ref, ObjectId): item_id_obj = item_ref
    if not item_id_obj: raise HTTPException(status_code=500, detail="Internal error: Corrupted item reference.")

    try: borrowing_obj = Borrowing.model_validate(raw_booking_data)
    except Exception as parse_error: raise HTTPException(status_code=500, detail="Internal error: Failed to process borrowing data.") from parse_error
    return borrowing_obj, item_id_obj


# --- Endpoint POST /schedule (lengkap) ---
@router.post(
    "/schedule",
    response_model=Borrowing.Response,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.USER))]
)
@limiter.limit("10/hour")
async def schedule_borrowing(
    request: Request,
    booking_request: Borrowing.CreateBooking = Body(...),
    current_user: User = Depends(require_role(UserRole.USER))
):
    """Allows a user to submit a booking request for a future period (status: PENDING_APPROVAL)."""
    logger.info(f"User '{current_user.username}' submitting booking for item '{booking_request.item_id}'.")
    start_date = booking_request.start_date
    end_date = booking_request.end_date
    now_utc = datetime.now(timezone.utc)
    if start_date.tzinfo is None: start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None: end_date = end_date.replace(tzinfo=timezone.utc)
    if start_date <= now_utc: raise HTTPException(status_code=400, detail="Booking start date must be in the future.")
    if end_date <= start_date: raise HTTPException(status_code=400, detail="Booking end date must be after start date.")

    item = await get_item_or_404(booking_request.item_id) # Fungsi get_item_or_404 perlu diimpor/didefinisikan

    is_initially_available = await check_item_availability(
        booking_request.item_id, start_date, end_date, booking_request.quantity
    )
    if not is_initially_available: raise HTTPException(status_code=409, detail=f"Item '{item.name}' not available.")

    borrowing_obj = Borrowing(
        item=item, borrower=current_user, quantity=booking_request.quantity,
        borrowed_date=start_date, due_date=end_date, status=BorrowingStatus.PENDING_APPROVAL,
        borrowing_notes=booking_request.borrowing_notes, created_at=now_utc, updated_at=now_utc
    )
    try: await borrowing_obj.insert()
    except Exception as e: raise HTTPException(status_code=500, detail="Failed to submit booking.") from e

    try:
        # --- LANGKAH 1: Fetch Ulang TANPA Links dari Primary ---
        logger.info(f"Attempting to re-fetch booking {borrowing_obj.id} (NO links) from PRIMARY...")
        created_booking_no_links = await Borrowing.find_one(
            {"_id": borrowing_obj.id},
            fetch_links=False, # <-- Tanpa fetch links awal
        )
        if not created_booking_no_links:
             logger.error(f"CRITICAL: Failed to re-fetch booking {borrowing_obj.id} (NO links) from PRIMARY after insert.")
             raise HTTPException(status_code=500, detail="Failed to retrieve created booking confirmation.")
        logger.info(f"Re-fetch (NO links) successful for {borrowing_obj.id}.")

        # --- LANGKAH 2: Fetch Links Secara Manual ---
        logger.info(f"Attempting to fetch links manually for {borrowing_obj.id}...")
        # Gunakan method .fetch_all_links() pada objek Beanie
        await created_booking_no_links.fetch_all_links()
        logger.info(f"Manual fetch_all_links completed for {borrowing_obj.id}.")
        # Sekarang created_booking_no_links seharusnya punya data link yang ter-resolve
        created_booking_with_links = created_booking_no_links # Ganti nama variabel agar jelas

        # --- LANGKAH 3: Validasi Response (Gunakan objek yang sudah di-fetch linksnya) ---
        logger.info(f"Proceeding to validate response for {created_booking_with_links.id}")
        return validate_borrowing_response(created_booking_with_links) # Panggil helper

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error during response preparation for new booking {borrowing_obj.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error preparing booking confirmation response.") from e


# --- Endpoint PATCH /approve (lengkap) ---
@router.patch(
    "/{borrowing_id}/approve", 
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_staff_or_admin)]
)
@limiter.limit("60/minute")
async def approve_booking(
    request: Request, 
    borrowing_id: str = Path(...), 
    current_user: User = Depends(require_staff_or_admin)
):
    """Approves a PENDING_APPROVAL booking, changing status to SCHEDULED."""
    logger.info(f"Admin/Staff '{current_user.username}' approving booking '{borrowing_id}'.")
    booking_to_approve = await get_pending_booking_or_404(borrowing_id)
    update_data = {"status": BorrowingStatus.SCHEDULED, "updated_at": datetime.now(timezone.utc)}
    try: await booking_to_approve.update({"$set": update_data})
    except Exception as e: raise HTTPException(status_code=500, detail="Failed to approve booking.") from e
    return {"message": "Booking approved successfully", "borrowing_id": borrowing_id, "new_status": BorrowingStatus.SCHEDULED.value}


# --- Endpoint PATCH /reject (lengkap) ---
@router.patch(
    "/{borrowing_id}/reject", 
    status_code=status.HTTP_200_OK, 
    dependencies=[Depends(require_staff_or_admin)]
)
@limiter.limit("60/minute")
async def reject_booking(
    request: Request,
    borrowing_id: str = Path(...), 
    current_user: User = Depends(require_staff_or_admin)
):
    """Rejects a PENDING_APPROVAL booking, changing status to REJECTED."""
    logger.info(f"Admin/Staff '{current_user.username}' rejecting booking '{borrowing_id}'.")
    booking_to_reject = await get_pending_booking_or_404(borrowing_id)
    update_data = {"status": BorrowingStatus.REJECTED, "updated_at": datetime.now(timezone.utc)}
    try: await booking_to_reject.update({"$set": update_data})
    except Exception as e: raise HTTPException(status_code=500, detail="Failed to reject booking.") from e
    return {"message": "Booking rejected successfully", "borrowing_id": borrowing_id, "new_status": BorrowingStatus.REJECTED.value}


# --- Endpoint GET / (lengkap) ---
@router.get(
    "/", 
    response_model=List[Borrowing.Response]
)
@limiter.limit("120/minute")
async def read_borrowings(
    request: Request,
    skip: int = 0, limit: int = 25, status: Optional[List[BorrowingStatus]] = Query(None),
    item_id: Optional[str] = Query(None), user_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user)
):
    query_filters = {}
    if current_user.role == UserRole.USER:
        query_filters["borrower.$id"] = current_user.id
        if user_id and str(user_id) != str(current_user.id): raise HTTPException(status_code=403, detail="Users can only view their own borrowings.")
        if item_id:
            if not ObjectId.is_valid(item_id): raise HTTPException(status_code=400, detail="Invalid item_id format.")
            query_filters["item.$id"] = ObjectId(item_id)
    elif current_user.role in [UserRole.ADMIN, UserRole.STAFF]:
        if item_id:
             if not ObjectId.is_valid(item_id): raise HTTPException(status_code=400, detail="Invalid item_id format.")
             query_filters["item.$id"] = ObjectId(item_id)
        if user_id:
             if not ObjectId.is_valid(user_id): raise HTTPException(status_code=400, detail="Invalid user_id format.")
             query_filters["borrower.$id"] = ObjectId(user_id)
    else: raise HTTPException(status_code=403, detail="Access denied.")
    if status: query_filters["status"] = {"$in": [s.value for s in status]}

    try:
        borrowings_docs: List[Borrowing] = await Borrowing.find(
            query_filters, skip=skip, limit=limit, fetch_links=True,
            sort=[("borrowed_date", DESCENDING)]
        ).to_list()
        response_list: List[Borrowing.Response] = []
        for borrow_doc in borrowings_docs:
             try: response_list.append(validate_borrowing_response(borrow_doc))
             except Exception as val_err: logger.error(f"Skipping borrowing {borrow_doc.id} in list: {val_err}"); continue
        return response_list
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error retrieving borrowings.") from e


# --- Endpoint POST /{borrowing_id}/activate (LENGKAP & BENAR) ---
@router.post(
    "/{borrowing_id}/activate",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_staff_or_admin)]
)
async def activate_scheduled_borrowing(
    borrowing_id: str = Path(...),
    current_user: User = Depends(require_staff_or_admin)
):
    now_utc = datetime.now(timezone.utc)
    motor_client = Borrowing.get_motor_collection().database.client

    async with await motor_client.start_session() as session:
        async with session.start_transaction():
            logger.info(f"Starting transaction for ACTIVATING booking '{borrowing_id}'...")
            try:
                booking_to_activate, item_id_obj = await get_scheduled_booking_or_404(borrowing_id, session=session)
                item_id_str = str(item_id_obj)
                item_name_for_log = f"Item({item_id_str})"
                due_date = booking_to_activate.due_date
                if due_date.tzinfo is None: due_date = due_date.replace(tzinfo=timezone.utc)
                booking_quantity = booking_to_activate.quantity or 1
                if booking_quantity <=0: raise ValueError("Invalid quantity")

                is_still_available = await check_item_availability(
                    item_id_str, now_utc, due_date, requested_quantity=booking_quantity,
                    session=session, exclude_borrowing_id=booking_to_activate.id
                )
                if not is_still_available:
                    temp_item = await Item.find_one({"_id": item_id_obj}, projection={"name": 1}, session=session)
                    item_name_for_log = temp_item.name if temp_item and temp_item.name else item_id_str
                    raise HTTPException(status_code=409, detail=f"Item '{item_name_for_log}' is no longer available.")

                item_in_txn = await Item.find_one({"_id": item_id_obj, "is_active": True}, session=session)
                if item_in_txn and item_in_txn.name: item_name_for_log = item_in_txn.name
                if not item_in_txn or item_in_txn.current_stock < booking_quantity:
                     raise HTTPException(status_code=409, detail="Stock inconsistency or item not found.")

                await Item.get_motor_collection().update_one(
                    {"_id": item_id_obj}, {"$inc": {"current_stock": -booking_quantity}}, session=session
                )
                await Item.get_motor_collection().update_one(
                     {"_id": item_id_obj}, {"$set": {"updated_at": now_utc}}, session=session
                )
                new_stock_level = item_in_txn.current_stock - booking_quantity
                logger.info(f"Item '{item_name_for_log}' stock decremented by {booking_quantity} to {new_stock_level}.")

                update_borrow_payload = {
                    "status": BorrowingStatus.BORROWED, "borrowed_date": now_utc, "updated_at": now_utc
                }
                await booking_to_activate.update({"$set": update_borrow_payload}, session=session)
                logger.info(f"Booking '{borrowing_id}' status updated to BORROWED by '{current_user.username}'.")

            except HTTPException as http_exc: raise http_exc
            except ValueError as val_err: raise HTTPException(status_code=400, detail=f"Invalid data: {val_err}") from val_err
            except Exception as e: raise HTTPException(status_code=500, detail="Internal error.") from e

    logger.info(f"Activation transaction presumably committed for {borrowing_id}. Fetching final state...")
    try:
        # Fetch ulang TANPA links dulu
        logger.debug(f"[{borrowing_id}] Fetching main document post-activation...")
        final_borrowing_state_no_links = await Borrowing.find_one(
            {"_id": ObjectId(borrowing_id)},
            fetch_links=False
        )
        if not final_borrowing_state_no_links:
            # Ini seharusnya tidak terjadi jika transaksi commit
            logger.error(f"CRITICAL: Failed to re-fetch borrowing {borrowing_id} after commit.")
            raise HTTPException(status_code=500, detail="Could not retrieve borrowing status after activation.")

        # Fetch links manual
        logger.debug(f"[{borrowing_id}] Fetching links manually...")
        await final_borrowing_state_no_links.fetch_all_links()
        final_borrowing_state_with_links = final_borrowing_state_no_links
        logger.debug(f"[{borrowing_id}] Links fetched. Proceeding to validation.")

        # Validasi response menggunakan helper
        return validate_borrowing_response(final_borrowing_state_with_links)

    # --- Blok EXCEPT untuk fetch ulang dan validasi ---
    except HTTPException as http_exc:
        # Tangkap ulang HTTPException dari validate_borrowing_response atau dari cek not found
        logger.error(f"HTTPException during response preparation for {borrowing_id}: {http_exc.detail}")
        raise http_exc
    except ValueError as val_err: # Tangkap ValueError dari helper validasi
        logger.error(f"ValueError during response preparation for {borrowing_id}: {val_err}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Data error preparing response: {val_err}") from val_err
    except Exception as e: # Tangkap error tak terduga lainnya
        logger.error(f"Unexpected error during response preparation for {borrowing_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error preparing activation data for response.") from e


# --- Endpoint POST /{borrowing_id}/return (LENGKAP & BENAR) ---
@router.post(
    "/{borrowing_id}/return",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_staff_or_admin)]
)
async def process_item_return(
    borrowing_id: str = Path(...),
    return_data: Borrowing.Return = Body(...),
    current_user: User = Depends(require_staff_or_admin)
):
    now_utc = datetime.now(timezone.utc)
    motor_client = Borrowing.get_motor_collection().database.client

    async with await motor_client.start_session() as session:
        async with session.start_transaction():
            logger.info(f"Starting return transaction for borrowing '{borrowing_id}'...")
            try:
                borrowing_to_return, item_id_obj = await get_returnable_booking_or_404(borrowing_id, session=session)
                item_quantity_returned = borrowing_to_return.quantity or 1
                if item_quantity_returned <=0 : raise ValueError("Invalid quantity")

                borrowing_update_payload = {
                    "status": BorrowingStatus.RETURNED, "returned_date": now_utc,
                    "condition_on_return": return_data.condition_on_return,
                    "return_notes": return_data.return_notes,
                    "return_processor": current_user.to_ref(), "updated_at": now_utc
                }
                await borrowing_to_return.update({"$set": borrowing_update_payload}, session=session)
                logger.info(f"Borrowing '{borrowing_id}' status updated to RETURNED.")

                if return_data.condition_on_return == ReturnCondition.GOOD:
                    item_update_result = await Item.get_motor_collection().update_one(
                        {"_id": item_id_obj, "is_active": True},
                        {"$inc": {"current_stock": item_quantity_returned}}, session=session
                    )
                    await Item.get_motor_collection().update_one(
                         {"_id": item_id_obj}, {"$set": {"updated_at": now_utc}}, session=session
                    )
                    if item_update_result.matched_count == 0:
                        raise HTTPException(status_code=404, detail="Associated item not found or inactive.")
                    logger.info(f"Item stock for {item_id_obj} incremented by {item_quantity_returned}.")
                else:
                    logger.info(f"Item stock NOT incremented for {borrowing_id} due to condition.")

            except HTTPException as http_exc: raise http_exc
            except ValueError as val_err: raise HTTPException(status_code=400, detail=f"Invalid data: {val_err}") from val_err
            except Exception as e: raise HTTPException(status_code=500, detail="Internal error.") from e

    logger.info(f"Return transaction committed for {borrowing_id}.")
    # Kembalikan pesan sukses sederhana
    return {"message": "Item returned successfully", "borrowing_id": borrowing_id, "new_status": BorrowingStatus.RETURNED.value}


# --- Endpoint GET /{borrowing_id} (LENGKAP) ---
@router.get(
    "/{borrowing_id}",
    response_model=Borrowing.Response, # <-- Mengembalikan detail
    summary="Get Borrowing/Booking Details"
    # Dependensi keamanan (get_current_active_user & cek role/ownership) ada di dalam
)
@limiter.limit("120/minute")
async def read_borrowing(
    request: Request, # Untuk limiter
    borrowing_id: str = Path(...),
    current_user: User = Depends(get_current_active_user)
):
    """Retrieve details of a specific borrowing. Users can only see their own unless Admin/Staff."""
    if not ObjectId.is_valid(borrowing_id): raise HTTPException(status_code=400, detail="Invalid ID format.")
    borrowing = await Borrowing.find_one({"_id": ObjectId(borrowing_id)}, fetch_links=True)
    if not borrowing: raise HTTPException(status_code=404, detail="Record not found.")
    # --- (Logika otorisasi: user lihat miliknya, admin/staff lihat semua - sama) ---
    if current_user.role == UserRole.USER and borrowing.borrower.id != current_user.id:
         raise HTTPException(status_code=403, detail="Forbidden to view this record.")
    return validate_borrowing_response(borrowing)