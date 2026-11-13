# Tender Pipeline Backend

FastAPI/Celery backend for multi-source ingestion, document parsing, extraction, normalization, matching, persistence and export. Service responsibilities and the evaluation boundary are documented in the [root README](../README.md).

Create a backend-specific virtual environment and install `requirements.txt`. Configure database, queue and provider/source access through the root examples and ignored local environment. The root Compose file defines the backend service and exposes host port 8001.

Pure utilities in `app/services/normalize.py` and `matching.py` are exercised by the root offline suite without database or provider access. A passed utility test does not establish full queued-ingestion behavior, extraction accuracy or provider availability. Use synthetic records and an isolated database for integration work.

See `app/main.py` for API registration, `app/services/pipeline.py` for orchestration and the root runtime guide for source-specific dependencies and configuration.
