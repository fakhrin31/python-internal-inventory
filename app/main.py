# app/main.py
from fastapi import FastAPI, HTTPException
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from contextlib import asynccontextmanager
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler # Import scheduler
from apscheduler.triggers.interval import IntervalTrigger   # Import trigger
import pytz

from app.db.database import init_db
from app.api.v1.api import api_router_v1
# Import job function
from app.scheduler.jobs import activate_pending_bookings
from app.core.config import MONGODB_URL

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