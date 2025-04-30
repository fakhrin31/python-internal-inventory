# app/models/counter.py
from beanie import Document, Indexed

class SequenceCounter(Document):
    """Holds the next value for a named sequence."""
    # Gunakan _id sebagai nama sequence agar unik secara default oleh MongoDB
    # name: Indexed(str, unique=True) # Tidak perlu jika pakai _id
    value: int = 0 # Nilai counter saat ini / terakhir

    class Settings:
        name = "sequence_counters"
        # Jika menggunakan _id sebagai nama sequence:
        use_state_management = True # Membantu Beanie menangani update pada _id