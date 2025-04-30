# app/models/report.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
# Import Enum jika perlu untuk skema report, misal ReturnCondition
from app.models.enum import ReturnCondition

# --- Skema Lama (jika ada) ---
class StockMovementItemSummary(BaseModel):
    item_id: str
    item_name: str
    item_sku: Optional[str] = None
    total_in: int = Field(default=0)
    total_out: int = Field(default=0)

class StockMovementReport(BaseModel):
    start_date: datetime
    end_date: datetime
    items_summary: List[StockMovementItemSummary] = Field(default_factory=list)
    overall_total_in: int = Field(default=0)
    overall_total_out: int = Field(default=0)

# --- Skema Baru untuk Laporan Peminjaman ---

class TopBorrowedItem(BaseModel):
    """Item dalam laporan barang sering dipinjam."""
    item_id: str
    item_name: Optional[str] = "Item Not Found" # Default jika lookup gagal
    item_sku: Optional[str] = None
    borrow_count: int

class TopBorrowedItemsReport(BaseModel):
    """Response untuk laporan barang sering dipinjam."""
    start_date: Optional[datetime] = None # Tanggal bisa opsional untuk top N all-time
    end_date: Optional[datetime] = None
    limit: int
    top_items: List[TopBorrowedItem]

class ReturnConditionSummary(BaseModel):
    """Ringkasan jumlah per kondisi pengembalian."""
    condition: ReturnCondition # Gunakan Enum
    count: int

class ReturnConditionReport(BaseModel):
    """Response untuk laporan kondisi pengembalian."""
    start_date: datetime
    end_date: datetime
    condition_summary: List[ReturnConditionSummary]