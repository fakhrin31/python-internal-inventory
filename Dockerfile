FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin folder app ke dalam /app/app agar struktur tetap
COPY app /app/app

# Set PYTHONPATH ke /app
ENV PYTHONPATH=/app

# Jalankan aplikasi
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
