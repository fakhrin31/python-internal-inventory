# Gunakan image Python yang ringan
FROM python:3.10-slim

# Atur direktori kerja di dalam container
WORKDIR /app

# Salin file requirements.txt dan install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin semua file dari folder app ke dalam container
COPY app/ /app

# Jalankan aplikasi menggunakan uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
