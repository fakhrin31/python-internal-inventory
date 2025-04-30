# app/db/database.py
import motor.motor_asyncio
from beanie import init_beanie
# Import variabel konfigurasi spesifik yang dibutuhkan
from app.core.config import MONGODB_URL, DATABASE_NAME
from app.models.user import User # Import model Beanie Anda di sini
from app.models.category import Category
from app.models.item import Item
# from app.models.transaction import StockTransaction
from app.models.borrowing import Borrowing
from app.models.counter import SequenceCounter
import logging

logger = logging.getLogger(__name__)

async def init_db():
    """Inisialisasi koneksi database dan Beanie."""
    logger.info(f"Connecting to MongoDB...") # Detail URL sudah dicatat oleh config.py
    client = motor.motor_asyncio.AsyncIOMotorClient(
        MONGODB_URL, # Gunakan variabel yang diimpor
        # Tambahkan opsi lain jika perlu (misal: uuidRepresentation="standard")
    )

    # Dapatkan database object
    database = client[DATABASE_NAME] # Gunakan variabel yang diimpor
    logger.info(f"Using database: {DATABASE_NAME}")

    # Inisialisasi Beanie dengan database dan model dokumen
    await init_beanie(
        database=database,
        document_models=[
            User,
            Category,
            Item,
            # StockTransaction,
            Borrowing,
            SequenceCounter
        ]
    )
    logger.info("Beanie initialization complete for all models.")