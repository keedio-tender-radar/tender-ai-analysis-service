FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app/vendor

# tender-contracts vendorizado en ./vendor (repo privado). Generar antes del deploy:
#   bash scripts/vendor-contracts.sh
COPY pyproject.toml .
RUN pip install --no-cache-dir \
      "pydantic>=2.6" "pydantic-settings>=2.5" "httpx>=0.27" \
      "fastapi>=0.115" "uvicorn[standard]>=0.32"

COPY . .

EXPOSE 8000

# Servicio HTTP con POST /run (lo dispara el scheduler). El job one-shot sigue disponible
# vía `python -m tender_ai_analysis.main`.
CMD ["uvicorn", "tender_ai_analysis.web:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
