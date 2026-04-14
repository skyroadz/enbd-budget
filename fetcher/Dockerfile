FROM python:3.12.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libqpdf-dev \
    cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fetch.py .

CMD printenv > /etc/environment && \
    echo "${CRON_SCHEDULE:-0 10 * * *} root . /etc/environment && /usr/local/bin/python3 /app/fetch.py >> /var/log/fetcher.log 2>&1" \
    > /etc/cron.d/fetcher && \
    chmod 0644 /etc/cron.d/fetcher; \
    cron -f