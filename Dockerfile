FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app/vendor

# tender-contracts vendorizado en ./vendor (repo privado). Generar antes del deploy:
#   bash scripts/vendor-contracts.sh
COPY pyproject.toml .
RUN pip install --no-cache-dir \
      "pydantic>=2.6" "pydantic-settings>=2.5" "httpx>=0.27"

COPY . .

# Job de análisis (one-shot). En infra se programa por cron/scheduler.
CMD ["python", "-m", "tender_ai_analysis.main"]
