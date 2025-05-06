# Gunakan image Python ringan
FROM python:3.10-slim

# Atur direktori kerja
WORKDIR /app

# Tambahkan PYTHONPATH agar folder /app dikenali sebagai package root
ENV PYTHONPATH=/app

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin semua file project
COPY app/ /app

# Jalankan uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
