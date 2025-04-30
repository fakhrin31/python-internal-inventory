# create_admin.py
import asyncio
import os
import sys
from getpass import getpass # Untuk input password tersembunyi
from dotenv import load_dotenv

# Pastikan direktori 'app' ada di path agar impor berfungsi
project_root = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(project_root, 'app'))

# Import komponen yang diperlukan DARI DALAM 'app'
try:
    import motor.motor_asyncio
    from beanie import init_beanie
    from app.core.config import MONGODB_URL, DATABASE_NAME # Ambil dari config
    from app.models.user import User, UserRole           # Model dan Role Enum
    from app.core.security import get_password_hash      # Fungsi hashing
except ImportError as e:
    print(f"Error importing application modules: {e}")
    print("Pastikan Anda menjalankan skrip dari root direktori proyek dan venv aktif.")
    sys.exit(1)

async def create_initial_admin():
    """Skrip untuk membuat user admin awal."""
    print("--- Create Initial Admin User ---")

    # Muat variabel environment (terutama MONGODB_URL)
    load_dotenv(os.path.join(project_root, '.env'))

    db_url = MONGODB_URL
    db_name = DATABASE_NAME
    if not db_url or not db_name:
        print("Error: MONGODB_URL or DATABASE_NAME not found in environment variables/.env")
        return

    # Setup koneksi database dan Beanie (mirip init_db di app)
    try:
        client = motor.motor_asyncio.AsyncIOMotorClient(db_url)
        db = client[db_name]
        await init_beanie(database=db, document_models=[User])
        print(f"Connected to database: {db_name}")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return

    # Dapatkan input dari pengguna
    while True:
        username = input("Enter admin username: ").strip()
        if username:
            break
        print("Username cannot be empty.")

    # Cek apakah username sudah ada
    existing_user = await User.find_one(User.username == username)
    if existing_user:
        print(f"Error: Username '{username}' already exists.")
        client.close() # Tutup koneksi sebelum keluar
        return

    while True:
        password = getpass("Enter admin password: ")
        if password:
            password_confirm = getpass("Confirm admin password: ")
            if password == password_confirm:
                break
            else:
                print("Passwords do not match. Please try again.")
        else:
            print("Password cannot be empty.")

    email = input("Enter admin email (optional, press Enter to skip): ").strip() or None
    full_name = input("Enter admin full name (optional, press Enter to skip): ").strip() or None

    # Hash password
    hashed_password = get_password_hash(password)
    print("Password hashed successfully.")

    # Buat objek user admin
    admin_user = User(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=hashed_password,
        role=UserRole.ADMIN, # Tetapkan role ADMIN
        disabled=False
    )

    # Simpan ke database
    try:
        await admin_user.insert()
        print(f"Admin user '{username}' created successfully!")
    except Exception as e:
        print(f"Error saving admin user to database: {e}")

    # Tutup koneksi database
    client.close()
    print("Database connection closed.")


if __name__ == "__main__":
    print("Starting admin creation script...")
    # Jalankan fungsi async menggunakan asyncio.run()
    asyncio.run(create_initial_admin())
    print("Script finished.")