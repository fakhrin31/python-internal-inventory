# app/core/utils.py
import logging
from beanie.odm.operators.update.general import Inc
from app.models.counter import SequenceCounter
from pymongo import ReturnDocument # Import ReturnDocument

logger = logging.getLogger(__name__)

async def get_next_sequence_value(sequence_name: str) -> int:
    """
    Gets the next value for a named sequence, incrementing it atomically.
    Uses _id field of SequenceCounter as the sequence name. (Revised for robustness)
    """
    logger.debug(f"Attempting to get next sequence value for: {sequence_name}")
    collection = SequenceCounter.get_motor_collection() # Dapatkan koleksi motor

    try:
        # Gunakan find_one_and_update dari Motor langsung untuk kontrol lebih
        updated_doc = await collection.find_one_and_update(
            {"_id": sequence_name}, # Filter berdasarkan _id (nama sequence)
            {"$inc": {"value": 1}}, # Increment field 'value'
            upsert=True,            # Buat jika tidak ada
            return_document=ReturnDocument.AFTER # Kembalikan dokumen SETELAH update
        )

        if updated_doc and 'value' in updated_doc:
            next_value = updated_doc['value']
            logger.debug(f"Next sequence value for '{sequence_name}': {next_value}")
            return next_value
        else:
            # Jika upsert pertama kali atau ada masalah, coba baca lagi (seharusnya tidak perlu)
            logger.warning(f"find_one_and_update didn't return expected document for '{sequence_name}'. Attempting find_one.")
            counter_doc = await SequenceCounter.find_one(SequenceCounter.id == sequence_name)
            if counter_doc and hasattr(counter_doc, 'value'):
                logger.debug(f"Fallback find_one successful for '{sequence_name}': {counter_doc.value}")
                return counter_doc.value
            else:
                 # Jika find_one juga gagal, ada masalah serius
                 logger.error(f"CRITICAL: Failed to get or create sequence counter '{sequence_name}' after upsert/find.")
                 raise Exception(f"Failed to get or create sequence counter: {sequence_name}")

    except Exception as e:
        logger.error(f"Error in get_next_sequence_value for '{sequence_name}': {e}", exc_info=True)
        # Re-raise agar bisa ditangkap oleh pemanggil (endpoint)
        raise Exception(f"Database error accessing sequence counter '{sequence_name}'") from e