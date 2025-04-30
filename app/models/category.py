# app/models/category.py
from typing import Optional, Annotated
from beanie import Document
from pydantic import BaseModel, Field, field_validator
from pymongo import IndexModel, ASCENDING, DESCENDING # Import DESCENDING jika perlu
from bson import ObjectId
from datetime import datetime

class Category(Document):
    name: str
    # category_code akan dibuat otomatis, Tipe tetap str.
    # Tidak lagi di Field utama dengan constraint, karena di-set di endpoint.
    # Tetap butuh fieldnya di model Beanie. Buat opsional agar validasi awal tidak gagal.
    category_code: Optional[str] = None # Dibuat jadi Optional sementara, diisi sebelum insert
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Validator dihapus dari sini, karena tidak lagi input user

    class Settings:
        name = "categories"
        indexes = [
            IndexModel([("name", ASCENDING)], name="category_name_unique_index", unique=True),
            # Index unik untuk category_code (masih penting)
            IndexModel([("category_code", ASCENDING)], name="category_code_unique_index", unique=True, sparse=True), # sparse jika bisa None awal
            IndexModel([("created_at", ASCENDING)], name="category_created_at_index"),
            IndexModel([("updated_at", DESCENDING)], name="category_updated_at_index"), # Pakai DESCENDING
        ]

    # --- Pydantic Schemas ---
    class Create(BaseModel):
        """Skema untuk membuat kategori baru (tanpa kode)."""
        name: str = Field(..., min_length=1, max_length=100)
        # HAPUS category_code dari Create
        description: Optional[str] = None
        # Hapus validator category_code

    class Update(BaseModel):
        """Skema untuk memperbarui kategori (kode tidak bisa diubah)."""
        name: Optional[str] = Field(None, min_length=1, max_length=100)
        # HAPUS category_code dari Update
        description: Optional[str] = None
        # Hapus validator category_code

    class Response(BaseModel):
        """Skema untuk response API."""
        id: str = Field(..., alias="_id")
        name: str
        category_code: Optional[str] # Tampilkan kode yang sudah digenerate
        description: Optional[str] = None
        created_at: datetime
        updated_at: datetime
        class Config: from_attributes=True; populate_by_name=True; arbitrary_types_allowed=True