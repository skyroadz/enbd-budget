FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/app/
COPY parsers/ /app/parsers/
COPY rules.yaml /app/rules.yaml
COPY tools /app/tools

ENV DATA_DIR=/data
ENV STATEMENTS_DIR=/data/statements
ENV DB_PATH=/data/state.db
ENV RULES_PATH=/app/rules.yaml

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]