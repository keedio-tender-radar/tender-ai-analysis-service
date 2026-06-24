#!/usr/bin/env bash
# Copia el paquete tender_contracts (repo hermano) a ./vendor para el build de Docker.
# tender-shared-contracts es privado y no se instala desde git en el build remoto.
# Ejecutar antes de `compute deploy`. vendor/ está gitignored.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$HERE/../tender-shared-contracts/python/tender_contracts"
[ -d "$SRC" ] || { echo "No encuentro $SRC" >&2; exit 1; }
rm -rf "$HERE/vendor"; mkdir -p "$HERE/vendor"
cp -r "$SRC" "$HERE/vendor/tender_contracts"
echo "Vendorizado en $HERE/vendor/tender_contracts"
