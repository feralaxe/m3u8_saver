FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    TEMP_DIR=/tmp/m3u8-saver

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates pciutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

RUN mkdir -p /app/data /tmp/m3u8-saver
VOLUME ["/app/data"]

CMD ["python", "-m", "m3u8_saver"]
