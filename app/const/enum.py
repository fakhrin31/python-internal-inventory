# app/models/enums.py
from enum import Enum

class BorrowingStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval" # <-- Status awal setelah booking user
    SCHEDULED = "scheduled"         # <-- Disetujui, menunggu aktivasi scheduler
    BORROWED = "borrowed"
    RETURNED = "returned"
    OVERDUE = "overdue"
    LOST = "lost"
    CANCELLED = "cancelled"           # <-- Gagal aktivasi oleh scheduler
    REJECTED = "rejected"             # <-- Ditolak oleh Admin/Staff

class ReturnCondition(str, Enum):
    # ... (sama) ...
    GOOD = "good"
    MINOR_DAMAGE = "minor_damage"
    MAJOR_DAMAGE = "major_damage"