FROM python:3.12-slim

# ffmpeg/ffprobe are needed by the worker to validate and split audio.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts

# One image, two services: SERVICE_ROLE=worker runs the job loop, anything else the API.
CMD ["sh", "-c", "if [ \"$SERVICE_ROLE\" = worker ]; then exec python -m app.worker; else exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}; fi"]
