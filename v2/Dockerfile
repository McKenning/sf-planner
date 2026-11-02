FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app/ /app/app/
COPY core/ /app/core/
COPY static/ /app/static/
COPY templates/ /app/templates/
COPY migrations/ /app/migrations/
COPY tools/ /app/tools/
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
