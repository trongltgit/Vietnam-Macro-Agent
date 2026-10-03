FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p \
    data/raw/nhnn \
    data/raw/nso \
    data/raw/companies \
    data/raw/other \
    data/processed/macro \
    data/processed/exchange_rate \
    data/processed/trade \
    data/excel_phase1

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV APP_ENV=production

EXPOSE 8000

# Shell form so $PORT from Render is expanded
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
