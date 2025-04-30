# app/models/item.py
from typing import Optional
from beanie import Document, Link, PydanticObjectId
from pydantic import BaseModel, Field, HttpUrl
from pymongo import IndexModel, ASCENDING # Pastikan ASCENDING diimport
from datetime import datetime
from bson import ObjectId

from .category import Category

class Item(Document):
    """Model Dokumen Beanie untuk Barang Inventaris."""
    name: str = Field(..., max_length=200)
    sku: Optional[str] = None
    description: Optional[str] = None
    category: Link[Category]
    current_stock: int = Field(default=0, ge=0)
    price: Optional[float] = Field(None, ge=0)
    image_url: Optional[HttpUrl] = None
    location_cabinet: Optional[str] = Field(None, max_length=100, description="Nama/Nomor Lemari")
    location_shelf: Optional[str] = Field(None, max_length=100, description="Nomor/Label Rak")
    location_notes: Optional[str] = None

    # --- Tambahkan field is_active ---
    is_active: bool = Field(default=True, description="Status aktif item (True=aktif, False=dihapus/tidak aktif)")

    # --- Timestamps ---
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "items"
        indexes = [
            IndexModel([("name", ASCENDING)], name="item_name_index"),
            IndexModel([("sku", ASCENDING)], name="item_sku_unique_index", unique=True, sparse=True),
            IndexModel([("category.$id", ASCENDING)], name="item_category_index"),
            IndexModel([("current_stock", ASCENDING)], name="item_stock_index"),
            IndexModel([("location_cabinet", ASCENDING)], name="item_location_cabinet_index", sparse=True),
            IndexModel([("location_shelf", ASCENDING)], name="item_location_shelf_index", sparse=True),
            # --- Tambahkan Index untuk is_active ---
            IndexModel([("is_active", ASCENDING)], name="item_is_active_index"),
        ]

    # --- Pydantic Schemas for API ---
    # (Skema Create, Update, Response tidak perlu diubah secara struktur,
    #  tapi Response akan otomatis menyertakan is_active jika ada di model)
    class Create(BaseModel):
        name: str = Field(..., min_length=1, max_length=200)
        description: Optional[str] = None
        category_id: str = Field(..., description="String ObjectId of the category")
        initial_stock: int = Field(default=0, ge=0)
        price: Optional[float] = Field(None, ge=0)
        image_url: Optional[HttpUrl] = None
        location_cabinet: Optional[str] = Field(None, max_length=100)
        location_shelf: Optional[str] = Field(None, max_length=100)
        location_notes: Optional[str] = None
        # is_active tidak perlu di Create, defaultnya True

    class Update(BaseModel):
        name: Optional[str] = Field(None, min_length=1, max_length=200)
        description: Optional[str] = None
        category_id: Optional[str] = Field(None, description="String ObjectId of the new category")
        price: Optional[float] = Field(None, ge=0)
        image_url: Optional[HttpUrl] = None
        location_cabinet: Optional[str] = Field(None, max_length=100)
        location_shelf: Optional[str] = Field(None, max_length=100)
        location_notes: Optional[str] = None
        # Tambahkan is_active ke Update jika ingin mengaktifkan kembali item
        is_active: Optional[bool] = None

    class Response(BaseModel):
        id: str = Field(..., alias="_id")
        name: str
        sku: Optional[str] = None
        description: Optional[str] = None
        category: Category.Response
        current_stock: int
        price: Optional[float] = None
        image_url: Optional[HttpUrl] = None
        location_cabinet: Optional[str] = None
        location_shelf: Optional[str] = None
        location_notes: Optional[str] = None
        is_active: bool # Sertakan status aktif di response
        created_at: datetime
        updated_at: datetime

        class Config:
            from_attributes = True
            populate_by_name = True
            arbitrary_types_allowed = True