# tender-ai-analysis-service

> 🧠 Análisis IA + **scoring Go/No-Go** de **Keedio Tender Radar**. Lee licitaciones pendientes
> de `tender-api`, las analiza (resumen, requisitos, riesgos) y publica su score.

En el MVP-1 el scoring va **embebido** aquí (se separará a `tender-scoring-service` cuando las
reglas crezcan). El análisis IA es robusto: usa LLM si hay, y si no, cae a rule-based.

## Flujo

```
GET /api/tenders?status=discovered
        ↓
analyze(tender)        ← LLM (OpenRouter, con fallback rule-based)
        ↓
score(tender, análisis, perfil Keedio)   ← 9 dimensiones, reglas duras, recomendación
        ↓
PUT /api/tenders/{id}/score
```

## Componentes

- `analysis.py` — `analyze()` produce resumen, requisitos, riesgos y *hints*. Con LLM enriquece;
  sin key/factory cae a rule-based. Las hints (solvencia/partner/riesgo/incompatibilidad) afinan
  el scoring, pero **el scoring funciona con o sin LLM**.
- `scoring.py` — scorer **determinista** de las 9 dimensiones (máximos 30/15/15/10/10/5/5/5/5 =
  100). Reglas duras: CPV excluido → NO-GO; partner → PARTNER; plazo < mínimo → REVISAR. Devuelve
  desglose, recomendación y factores explicativos. `total == suma(breakdown)`.
- `llm.py` — cliente OpenRouter (cadena de modelos, `make_client`/`client_factory` mockeable).
- `profile.py` — perfil Keedio (CPV/keywords/umbrales) desde settings.
- `api_client.py` — leer pendientes + `put_score`. `job.py` orquesta; una licitación con error no
  tumba el lote.

## Ejecutar

```bash
python -m venv .venv && . .venv/Scripts/activate    # Linux/mac: source .venv/bin/activate
pip install -e ../tender-shared-contracts
pip install pydantic pydantic-settings httpx pytest ruff

python -m tender_ai_analysis.main     # analiza y puntúa las pendientes
pytest -q                             # 14 tests (scoring + análisis + llm + job)
ruff check src tests
```

## Notas

- Modelos `:free` de OpenRouter suelen dar **429**; en prod se cae a rule-based (esperado). El
  valor está en el **scoring determinista**, no en depender de un proveedor.
- El score se versiona (`SCORE_MODEL_VERSION`); pesos/umbrales son configurables por entorno.
- Prompts en `prompts/` (resumen ejecutivo, Go/No-Go).
