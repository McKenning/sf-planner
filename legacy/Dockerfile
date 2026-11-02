FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy the rest
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Create data directory
RUN mkdir -p /app/data

WORKDIR /app/backend
EXPOSE 8000

# Use uvicorn directly so we can tune workers
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
