FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libqpdf-dev \
    cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fetch.py .

# Run daily at 10am
RUN echo "0 10 * * * /usr/local/bin/python3 /app/fetch.py >> /var/log/fetcher.log 2>&1" | crontab -

CMD ["cron", "-f"]
