FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UPLOAD_ROOT=/data/uploads

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        tzdata \
        tesseract-ocr \
        tesseract-ocr-chi-sim \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app ./app
COPY init_db.py ./init_db.py
COPY migrate_account_deletion.py ./migrate_account_deletion.py
COPY migrate_account_recovery.py ./migrate_account_recovery.py
COPY docker-entrypoint.sh /usr/local/bin/kai-api-entrypoint

RUN chmod 0755 /usr/local/bin/kai-api-entrypoint \
    && mkdir -p /data/uploads/avatars /data/uploads/id_cards

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/kai-api-entrypoint"]
