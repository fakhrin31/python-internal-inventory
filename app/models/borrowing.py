# app/models/borrowing.py
from typing import Optional, Annotated, Any, List # Import List jika belum
from beanie import Document, Link, PydanticObjectId
from pydantic import BaseModel, Field, field_validator, ValidationInfo
from pymongo import IndexModel, ASCENDING, DESCENDING
from datetime import datetime, timezone

# Import related models and enums
# PENTING: Impor model dasar SEBELUM definisi skema Ref
from .item import Item
from .user import User
from ..const.enum import BorrowingStatus, ReturnCondition


# --- DEFINISIKAN SKEMA REFERENSI DULU ---
class ItemRefSimple(BaseModel):
    """Skema referensi singkat untuk Item."""
    # ID bisa string karena akan dikonversi sebelum validasi response
    id: str = Field(...)
    name: str
    sku: Optional[str] = None
    class Config: from_attributes=True; arbitrary_types_allowed=True

class UserRefSimple(BaseModel):
    """Skema referensi singkat untuk User."""
    id: str = Field(...)
    username: str
    class Config: from_attributes=True; arbitrary_types_allowed=True
# -----------------------------------------


class Borrowing(Document):
    item: Link[Item]
    borrower: Link[User]
    # --- TAMBAHKAN QUANTITY ---
    quantity: int = Field(..., gt=0, description="Number of units borrowed")
    # -------------------------
    borrowed_date: datetime
    due_date: datetime
    status: BorrowingStatus
    # ... (return details, notes, timestamps) ...
    returned_date: Optional[datetime] = None
    condition_on_return: Optional[ReturnCondition] = None
    # Tambahkan field untuk mencatat jumlah yg dikembalikan jika bisa parsial?
    # quantity_returned: Optional[int] = Field(None, ge=0) # <-- Pertimbangkan ini
    return_processor: Optional[Link[User]] = None
    return_notes: Optional[str] = None
    borrowing_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "borrowings"
        # ... (indexes) ... # Pertimbangkan index pada quantity jika perlu query

    # --- Pydantic Schemas ---
    class CreateBooking(BaseModel):
        item_id: str = Field(...)
        start_date: datetime = Field(...)
        end_date: datetime = Field(...)
        # --- TAMBAHKAN QUANTITY ---
        quantity: int = Field(..., gt=0, description="Number of units to borrow (must be > 0)")
        # -------------------------
        borrowing_notes: Optional[str] = None
        # ... (validator start/end date) ...

    class Return(BaseModel): # Skema untuk return
        condition_on_return: ReturnCondition
        # Tambahkan quantity jika mendukung pengembalian parsial
        # quantity_returned: int = Field(..., gt=0)
        return_notes: Optional[str] = None

    # --- Response Schema ---
    class Response(BaseModel):
        id: str = Field(...)
        item: ItemRefSimple
        borrower: UserRefSimple
        # --- TAMBAHKAN QUANTITY ---
        quantity: int
        # -------------------------
        borrowed_date: datetime
        due_date: datetime
        status: BorrowingStatus
        # ... (detail return, notes, timestamps) ...
        # quantity_returned: Optional[int] = None # Jika ada
        returned_date: Optional[datetime] = None
        condition_on_return: Optional[ReturnCondition] = None
        return_processor: Optional[UserRefSimple] = None
        return_notes: Optional[str] = None
        borrowing_notes: Optional[str] = None
        created_at: datetime
        updated_at: datetime
        class Config: from_attributes=True; arbitrary_types_allowed=True; use_enum_values = True

# Rebuild model
Borrowing.model_rebuild()