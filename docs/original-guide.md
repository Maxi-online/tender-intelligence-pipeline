# Tender & Project Intelligence System (TPIS)

## Engineering review

System of collection and normalization of tender and project data: API, rows, documentation, LLM-tracking, corporate enrichment and frontend. Sources and integration configurations are separated from the application pipline.

### Code navigation

- [backend/app/services/pipeline.py](../backend/app/services/pipeline.py)
- [backend/app/services/openai_client.py](../backend/app/services/openai_client.py)
- [backend/app/core/config.py](../backend/app/core/config.py)
- [config/settings.example.json](../config/settings.example.json)
- [docker-compose.yml](../docker-compose.yml)

### Reproduction and evaluation

Repeatable example: authorized documents → structured records with origin → duplicates → reimport. Check extraction F1 and duplicate precision/recall on an independent mark; separate check resume/idempotency. External source response and LLM generation do not guarantee the reliability of the record without reference to the source document.


Author: Maxi-online

TPIS – system for automatic collection, normalization and intellectual analysis of data on construction projects and tender. Realizes the cycle: source search, media/portals parsing, LLM-extraction and classification, semantic search (Perplexity + Claude), deduplication, API, export and web interface.

## Main opportunities
- Media/journal data collection (RSS/HTML/Sitemap) + auto-detection of new sources via SerpAPI.
- LLM – Russian core (Claude): the essence, dates, amounts, contacts, roles.
- Semantic search (Perplexity + Claude) with ranking of results.
- Deduction of projects/companies in the BD, a single table of report.
- Export CSV/XLSX/Parquet and PDF/Word file.
- Web-interface on Streetlit (Russian localization UI)).

## Structure
- `Backend/' – FastAPI, Celery Tasks, Parser, NLP, Matching, Export.
- `frontend/` — Streamlit UI.
- `config/` is a key words dictionary and source list.

## Quick start (local)
1. Copy `.env.example` in `.env` and complete the parameters.
2. Set backend relationships: `pip install -r backend/requirements.txt`
3. Initialization of BD: `python -m app.db.init_db`
4. LaunchAPI: `uvicorn app.main:app --reload --app-dir backend --host 0.0.0.0 --port 8001`
5. Launch Frontend: `cd background &&pip install -r requirements.txt && streamlit run streamlit_app/Chief.py`

## Docker Start
1. Copy `.env.example` in `.env` and complete the parameters.
2. Launch: `docker compose up --build`
3. API: `http://localhost:8001/api`
4. Frontend: `http://localhost:8501`

## Basic environmental parameters (.env)
- `DATABASE_URL` is a link to PostgreSQL.
- `SELDON_BASE_URL`, `SELDON_API_KEY` — Access to Justice in Environmental MattersSeldon API (if available).
- `DISCOVERY_SEARCH_URL`, `ZDISCOVERY_API_KEY' — Search for Sources (SerpAPI)).
  - Example: `https://serpapi.com/search.json?engine=google_news&q={query}&hl=ru&gl=ru&api_key={api_key}`
- `HTTP_PROXY_URL`, `USER_AGENT`, `REQUEST_DELAY_MIN/MAX` — anti‑blocking.
- `PERPLEXITY_API_KEY`, `PERPLEXITY_MODEL` — Key and ModelPerplexity.
- `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` — Key and ModelClaude (Anthropic).
- `DADATA_API_KEY`, `DADATA_SECRET_KEY`, `DADATA_MCP_URL` — Access to Justice in Environmental MattersDadata andMCP.
- `EXPORT_DIR` is a shipping catalogue.
- `MATCHING_THRESHOLD`, `MATCHING_MIN_THRESHOLD` — Comparison thresholds.
- `SOURCES_CONFIG_PATH`, `ZKEYWORDS_CONFIG_PATH' — Paths to YAML Confiscations.

## Automation
- `Celery Beat` runs the update four times a day.
- A separate auto-detection cycle shall be started on schedule.

## Key API Endpoints
- `GET /api/reports/projects` is a single project table.
- `GET /api/export/projects/excel' is a model-based offloading of Excel.
- `GET /api/search/semantic` is a semantic search.
- `GET /api/sources` is a source list.
- `POST /api/sources/bootstrap' is a download of YAML sources.
- `GET /api/automation/status` is a state of automation.
- `POST /api/automation/start` is a manual cycle launch.
- `POST /api/automation/enable` / `POST /api/automation/stop' - Activate/off cycle.

## Limitations
- Seldon API is offline without a real key and access.
- The quality of filling depends on the source.

## Licensing
Commercial licence. All rights protected.

## Private configuration

Provider keys, tokens, passwords, proxy and personal parameters are set through variable environments. `.env.example` contains names without values. `.env` filled and local settings deleted from Git. Do not transmit secrets by command arguments and do not publish real magazines, downloads, certificates or user documents.

To run, export the required variables to the process environment or fill the ignored local `.env` if the entrypoint used is downloading it. The content of `.env` does not in itself become an environment of arbitrary Python command. For Docker Compose, the values of `.env` are transferred to customized services.

JSON/YAML- facilities use `${NAME}` links; configuration loaders allow them through the environment. For numerical values, ${NAME:int}`. Lack of mandatory value causes an error with the name of the variable, without its content. Safe `*.example.json` / `*.example.yaml` save configuration structure.

The names of the private parameters are given in [.env.example](../.env.example). Old values are only retained in the protected local storage facility of the owner; it is not part of the published project. Once the keys are rotated, use new values.

Checking the source and configuration formats does not replace the launch of the infrastructure and model evaluation. Privacy changes do not confirm the quality of AI, the performance of external APIs, or the willingness of the entire system to operate.
