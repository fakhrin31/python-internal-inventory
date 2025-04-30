# app/models/user.py
from typing import Optional, List
from beanie import Document, Link
from pydantic import BaseModel, Field, EmailStr, field_validator
from pymongo import IndexModel, ASCENDING, DESCENDING # Import DESCENDING
from enum import Enum
from bson import ObjectId
from datetime import datetime

class UserRole(str, Enum):
    ADMIN = "admin"
    STAFF = "staff"
    USER = "user"

class User(Document):
    username: str
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    hashed_password: str
    disabled: bool = Field(default=False) # Gunakan ini (False=Aktif, True=Nonaktif)
    role: UserRole = Field(default=UserRole.USER)
    # Hapus is_active: bool = Field(default=True)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("username", ASCENDING)], name="username_unique_index", unique=True),
            IndexModel([("email", ASCENDING)], name="email_unique_index", unique=True, sparse=True),
            IndexModel([("role", ASCENDING)], name="role_index"),
            # Index untuk disabled status
            IndexModel([("disabled", ASCENDING)], name="user_disabled_index"),
            # Hapus index is_active: IndexModel([("is_active", ASCENDING)], name="user_is_active_index"),
            IndexModel([("created_at", ASCENDING)], name="user_created_at_index"),
            IndexModel([("updated_at", DESCENDING)], name="user_updated_at_index"), # Gunakan DESCENDING
        ]

    # --- Pydantic Schemas ---
    class Response(BaseModel):
        id: str = Field(..., alias="_id")
        username: str
        email: Optional[EmailStr] = None
        full_name: Optional[str] = None
        disabled: bool # Tetap tampilkan status disabled
        role: UserRole
        # Hapus is_active: bool
        created_at: datetime
        updated_at: datetime

        class Config:
            from_attributes = True
            populate_by_name = True
            arbitrary_types_allowed = True
            use_enum_values = True

    class Create(BaseModel):
        username: str
        email: Optional[EmailStr] = None
        full_name: Optional[str] = None
        password: str

    class AdminCreate(BaseModel):
        username: str
        email: Optional[EmailStr] = None
        full_name: Optional[str] = None
        password: str
        role: UserRole = UserRole.USER
        disabled: bool = False # Tetap gunakan disabled

    class AdminUpdate(BaseModel):
        email: Optional[EmailStr] = None
        full_name: Optional[str] = None
        password: Optional[str] = None
        role: Optional[UserRole] = None
        disabled: Optional[bool] = None # Tetap gunakan disabled
        # Hapus is_active: Optional[bool] = None