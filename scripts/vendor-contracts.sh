#!/usr/bin/env bash
# Vendoriza los paquetes hermanos a ./vendor para el build de Docker:
#  - tender_contracts (repo privado)
#  - tender_ingestion (la ingesta corre fusionada en este servicio vía POST /run-ingestion)
# Ejecutar antes de `compute deploy`. vendor/ está gitignored.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTRACTS="$HERE/../tender-shared-contracts/python/tender_contracts"
INGESTION="$HERE/../tender-ingestion-service/src/tender_ingestion"
[ -d "$CONTRACTS" ] || { echo "No encuentro $CONTRACTS" >&2; exit 1; }
[ -d "$INGESTION" ] || { echo "No encuentro $INGESTION" >&2; exit 1; }
rm -rf "$HERE/vendor"; mkdir -p "$HERE/vendor"
cp -r "$CONTRACTS" "$HERE/vendor/tender_contracts"
cp -r "$INGESTION" "$HERE/vendor/tender_ingestion"
echo "Vendorizado: tender_contracts + tender_ingestion en $HERE/vendor"
