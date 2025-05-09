🚀 FastAPI Backend Inventory Application

This backend system provides a comprehensive API for managing an inventory of items, including category and stock control, borrowing, and scheduling. Built with Python using the **FastAPI** framework and **MongoDB**, it’s designed for performance, modularity, and scalability. 

🔑 Core Features

### 1. User Management & Authentication
- Register new users.
- Secure login using JWT (JSON Web Token).
- Role-Based Access Control (RBAC): `ADMIN`, `STAFF`, `USER`.
- Full user CRUD operations (admin-only).
- Enable or disable user accounts (admin-only).

### 2. Item Category Management
- CRUD operations for item categories (admin/staff).
- Unique code generation for each category.
- Prevent deletion of categories currently linked to items.

### 3. Inventory (Item) Management
- CRUD operations for inventory items (admin/staff).
- Automatically generated SKUs based on category and UUID.
- Item fields: name, description, category, price, stock, location (cabinet & shelf), image.
- Soft-delete functionality (mark items as inactive).

### 4. Borrowing & Scheduling
- Users can book items for a future date.
- Admin/staff can approve or reject bookings.
- Approved bookings (`SCHEDULED`) can be activated on pickup.
- Automatic availability checks against stock and overlapping schedules.
- Stock is decreased when a booking is activated into a borrowing.

### 5. Item Return Handling
- Admin/staff process returns.
- Condition tracking: `GOOD`, `MINOR_DAMAGE`, `MAJOR_DAMAGE`.
- Stock auto-increases if returned in `GOOD` condition.

### 6. Reporting
- Active borrowing reports (including overdue items).
- Overdue borrowing summary.
- Borrowing history (per item and user).
- Most frequently borrowed items.
- Condition summary report on item returns.

### 7. Additional Backend Features
- Centralized logging using **Loguru**.
- Unified error handling with standard JSON responses.
- CORS support for frontend integration.
- GZip compression for faster responses.
- Rate limiting to prevent abuse.
- MongoDB transactions for atomic operations (e.g., borrowing activation, returns).

---

## 🧱 Technology Stack

- **Language:** Python 3.10+
- **Framework:** FastAPI
- **Database:** MongoDB
- **ODM:** Beanie
- **Async Mongo Driver:** Motor
- **Data Validation:** Pydantic
- **Auth:** JWT via python-jose & passlib
- **Logging:** Loguru
- **Rate Limiting:** SlowAPI
- **Env Management:** python-dotenv
- **Scheduler (optional):** APScheduler


## 📂Structure Project
```
/ (Project Root)
└── app
    ├── __init__.py
    ├── api
    │   ├── __init__.py
    │   └── v1
    │       ├── __init__.py
    │       ├── api.py
    │       └── endpoints
    │           ├── __init__.py
    │           ├── auth.py
    │           ├── borrowings.py
    │           ├── categories.py
    │           ├── items.py
    │           ├── reports.py
    │           └── users.py
    ├── core
    │   ├── __init__.py
    │   ├── availability.py
    │   ├── config.py
    │   ├── rate_limiter.py
    │   ├── security.py
    │   └── utils.py
    ├── db
    │   ├── __init__.py
    │   └── database.py
    ├── dto
    │   ├── __init__.py
    │   └── token.py
    ├── middleware
    │   ├── __init__.py
    │   ├── authentication.py
    │   └── logging.py
    ├── models
    │   ├── __init__.py
    │   ├── borrowing.py
    │   ├── category.py
    │   ├── counter.py
    │   ├── item.py
    │   └── user.py
    ├── scheduler
    │   ├── __init__.py
    │   └── jobs.py
    ├── variables
    │   ├── __init__.py
    │   └── enums.py
    └── main.py
├── .env
├── .gitignore
├── README.md
├── requirements.txt
```

## ⚙️ Environment Setup
1. **Clone the Repository:**
```bash
git clone <https://github.com/fakhrin31/python-internal-inventory.git>
cd inventory-app

2.  **Create and Activate a Virtual Environment:**
    ```bash
    python -m venv .venv
    # Windows
    .\.venv\Scripts\activate
    # Linux/macOS
    source .venv/bin/activate
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set Up MongoDB Database:**
    *   Ensure you have a running MongoDB server.
    *   For transaction features (`/activate`, `/return`), MongoDB **must be configured as a Replica Set**.
5.  **Create `.env` File:**
    *   Copy `.env.example` (if provided) to `.env` or create a new `.env` file in the project root.
    *   Fill in the required environment variables:
        ```dotenv
        # Example .env content
        SECRET_KEY="replace_with_a_very_strong_random_secret_key_at_least_32_hex_chars"
        ALGORITHM="HS256"
        ACCESS_TOKEN_EXPIRE_MINUTES=30

        # Adjust to your MongoDB configuration
        MONGODB_URL="mongodb://localhost:27017/inventory_db?replicaSet=rs0"
        DATABASE_NAME="inventory" # Can also be inferred from MONGODB_URL

        LOG_LEVEL="INFO" # Can be DEBUG, INFO, WARNING, ERROR, CRITICAL
        # LOG_FILE_PATH="logs/app.log" # Optional log file path
        # LOG_ROTATION="10 MB"
        # LOG_RETENTION="3 days"

        # Optional: If using Redis for Rate Limiter
        # REDIS_URL="redis://localhost:6379/0"
        ```
    *   **IMPORTANT:** Generate a strong, random `SECRET_KEY` (e.g., using `openssl rand -hex 32`).

6.  **(Optional) Create Initial Admin User:**
    *   If you have a script like `create_admin.py` or `manage.py create-admin`, run it to create the first admin user to log in and use admin-only endpoints.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

