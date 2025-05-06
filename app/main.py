# app/main.py
import logging
from fastapi import FastAPI, Request, status as fastapi_status, HTTPException
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager

# Import Middleware & Konfigurasi
from app.core.config import setup_logging # Setup Loguru
from loguru import logger                          # Gunakan Loguru
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.authentication import AuthMiddleware
from app.core.rate_limiter import get_rate_limiter, rate_limit_exception_handler
from slowapi.errors import RateLimitExceeded

# Import komponen aplikasi lain
from app.db.database import init_db, MONGODB_URL
from app.api.v1.api import api_router_v1
from apscheduler.schedulers.asyncio import AsyncIOScheduler # Uncomment jika pakai scheduler
from app.scheduler.jobs import activate_pending_bookings # Uncomment jika pakai scheduler
from apscheduler.triggers.interval import IntervalTrigger   # Import trigger

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

#  --- Scheduler Instance ---
SCHEDULER_TIMEZONE = 'Asia/Jakarta'
scheduler = AsyncIOScheduler(timezone=SCHEDULER_TIMEZONE) # Gunakan UTC atau timezone server Anda

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup...")
    await init_db()
    logger.info("Database initialized.")

    # (Jalankan startup job jika ada)
    # await run_startup_booking_activation()

    logger.info("Adding scheduler jobs...")
    scheduler.add_job(
        activate_pending_bookings,
        trigger=IntervalTrigger(minutes=15), # Trigger tetap berdasarkan interval
        id="activate_bookings_job",
        name="Activate Scheduled Bookings",
        replace_existing=True,
        misfire_grace_time=60*15 # Contoh: Toleransi 15 menit jika terlewat
    )
    scheduler.start()
    logger.info(f"Scheduler started with timezone: {scheduler.timezone}") # Log timezone
    yield
    logger.info("Application shutdown...")
    if scheduler.running: scheduler.shutdown()

# Buat instance FastAPI dengan lifespan manager
app = FastAPI(
    title="Inventory API",
    # ... deskripsi, version ...
    lifespan=lifespan # Gunakan lifespan manager
)
# --- KONFIGURASI MIDDLEWARE ---

# 1. Error Handling (Tambahkan handler RateLimitExceeded)
app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)
@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    logger.error(f"Validation Error: {exc.errors()}", exc_info=False)
    return JSONResponse(
        status_code=fastapi_status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation Error", "errors": exc.errors()},
    )
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(f"HTTP Exception: Status={exc.status_code}, Detail={exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=getattr(exc, "headers", None))
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception: {exc}", exc_info=True)
    return JSONResponse(status_code=fastapi_status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "An internal server error occurred."})

# 3. Request Logging Middleware
app.add_middleware(RequestLoggingMiddleware)

# 4. Authentication Middleware
app.add_middleware(AuthMiddleware)

# 5. Rate Limiter State (untuk decorator @limiter.limit)
app.state.limiter = get_rate_limiter()

# 6. GZip Middleware
app.add_middleware(GZipMiddleware, minimum_size=500)

# --- END MIDDLEWARE ---



# Include router API
app.include_router(api_router_v1)

# Root endpoint
@app.get("/")
async def read_root():
    return {"message": "Welcome!"}

# Create a MongoDB client
client = MongoClient(MONGODB_URL)

@app.get("/ping-mongodb")
async def ping_mongodb():
    try:
        # The 'ismaster' command is a cheap way to check the connection
        client.admin.command('ping')
        return {"status": "success", "message": "MongoDB connection is healthy."}
    except ConnectionFailure:
        raise HTTPException(status_code=503, detail="MongoDB connection failed.")