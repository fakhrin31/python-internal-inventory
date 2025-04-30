# app/api/v1/api.py
from fastapi import APIRouter

# Import semua router endpoints
from app.api.v1.endpoints import auth, users, categories, items, borrowings, reports # <-- Tambahkan import

api_router_v1 = APIRouter(prefix="/api/v1")

# Include endpoint routers
api_router_v1.include_router(auth.router, prefix="/auth")
api_router_v1.include_router(users.router, prefix="/users")
api_router_v1.include_router(categories.router, prefix="/categories")
api_router_v1.include_router(items.router, prefix="/items")
# api_router_v1.include_router(transactions.router, prefix="/transactions")
api_router_v1.include_router(reports.router)
api_router_v1.include_router(borrowings.router, prefix="/borrowings")