# Tender & Project Intelligence System (TPIS)

## Инженерный обзор

Система сбора и нормализации тендерных и проектных данных: API, очереди, разбор документов, LLM-извлечение, обогащение компаний и frontend. Конфигурации источников и интеграций отделены от прикладного пайплайна.

### Навигация по коду

- [backend/app/services/pipeline.py](backend/app/services/pipeline.py)
- [backend/app/services/openai_client.py](backend/app/services/openai_client.py)
- [backend/app/core/config.py](backend/app/core/config.py)
- [config/settings.example.json](config/settings.example.json)
- [docker-compose.yml](docker-compose.yml)

### Воспроизведение и оценка

Воспроизводимый пример: разрешённые документы → структурированные записи с происхождением → дубликаты → повторный импорт. Проверяйте extraction F1 и duplicate precision/recall на независимой разметке; отдельно проверяйте resume/idempotency. Ответ внешнего источника и генерация LLM не гарантируют достоверность записи без ссылки на исходный документ.


Автор: Maxi-online

TPIS — система для автоматического сбора, нормализации и интеллектуального анализа данных по строительным проектам и тендерам. Реализует цикл: автопоиск источников, парсинг СМИ/порталов, LLM‑извлечение сущностей и классификация, семантический поиск (Perplexity + Claude), дедупликация, API, экспорт и веб‑интерфейс.

## Основные возможности
- Автосбор данных из СМИ/журналов (RSS/HTML/Sitemap) + автообнаружение новых источников через SerpAPI.
- LLM‑ядро на русском языке (Claude): сущности, даты, суммы, контакты, роли.
- Семантический поиск (Perplexity + Claude) с ранжированием результатов.
- Дедупликация проектов/компаний в БД, единая таблица отчета.
- Экспорт CSV/XLSX/Parquet и досье PDF/Word.
- Веб‑интерфейс на Streamlit (русская локализация UI).

## Структура
- `backend/` — FastAPI, задачи Celery, парсеры, NLP, matching, экспорт.
- `frontend/` — Streamlit UI.
- `config/` — словари ключевых слов и список источников.

## Быстрый старт (локально)
1. Скопируйте `.env.example` в `.env` и заполните параметры.
2. Установите зависимости backend: `pip install -r backend/requirements.txt`
3. Инициализация БД: `python -m app.db.init_db`
4. Запуск API: `uvicorn app.main:app --reload --app-dir backend --host 0.0.0.0 --port 8001`
5. Запуск Frontend: `cd frontend && pip install -r requirements.txt && streamlit run streamlit_app/Главная.py`

## Запуск в Docker
1. Скопируйте `.env.example` в `.env` и заполните параметры.
2. Запуск: `docker compose up --build`
3. API: `http://localhost:8001/api`
4. Frontend: `http://localhost:8501`

## Основные параметры окружения (.env)
- `DATABASE_URL` — строка подключения к PostgreSQL.
- `SELDON_BASE_URL`, `SELDON_API_KEY` — доступ к Seldon API (если доступен).
- `DISCOVERY_SEARCH_URL`, `DISCOVERY_API_KEY` — поиск источников (SerpAPI).
  - Пример: `https://serpapi.com/search.json?engine=google_news&q={query}&hl=ru&gl=ru&api_key={api_key}`
- `HTTP_PROXY_URL`, `USER_AGENT`, `REQUEST_DELAY_MIN/MAX` — anti‑blocking.
- `PERPLEXITY_API_KEY`, `PERPLEXITY_MODEL` — ключ и модель Perplexity.
- `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` — ключ и модель Claude (Anthropic).
- `DADATA_API_KEY`, `DADATA_SECRET_KEY`, `DADATA_MCP_URL` — доступ к Dadata и MCP.
- `EXPORT_DIR` — каталог выгрузок.
- `MATCHING_THRESHOLD`, `MATCHING_MIN_THRESHOLD` — пороги сопоставления.
- `SOURCES_CONFIG_PATH`, `KEYWORDS_CONFIG_PATH` — пути к YAML конфигам.

## Автоматизация
- `Celery Beat` запускает обновление 4 раза в день.
- Отдельный цикл автообнаружения источников запускается по расписанию.

## Ключевые API эндпоинты
- `GET /api/reports/projects` — единая таблица проектов.
- `GET /api/export/projects/excel` — выгрузка Excel по шаблону.
- `GET /api/search/semantic` — семантический поиск.
- `GET /api/sources` — список источников.
- `POST /api/sources/bootstrap` — загрузка источников из YAML.
- `GET /api/automation/status` — состояние автоматизации.
- `POST /api/automation/start` — ручной запуск цикла.
- `POST /api/automation/enable` / `POST /api/automation/stop` — включить/выключить цикл.

## Ограничения
- Seldon API отключен без реального ключа и доступа.
- Качество заполнения зависит от исходных источников.

## Лицензия
Коммерческая лицензия. Все права защищены.

## Приватная конфигурация

Ключи провайдеров, токены, пароли, прокси и персональные параметры задаются через переменные окружения. `.env.example` содержит имена без значений. Заполненный `.env` и локальные настройки исключены из Git. Не передавайте секреты аргументами команд и не публикуйте реальные журналы, выгрузки, сертификаты или пользовательские документы.

Для запуска экспортируйте нужные переменные в окружение процесса либо заполните игнорируемый локальный `.env`, если используемый entrypoint его загружает. Содержимое `.env` само по себе не становится окружением произвольной Python-команды. Для Docker Compose значения из `.env` передаются в настроенные сервисы.

JSON/YAML-настройки используют ссылки `${NAME}`; конфигурационные загрузчики разрешают их через окружение. Для числовых значений предусмотрен `${NAME:int}`. Отсутствующее обязательное значение вызывает ошибку с именем переменной, без её содержимого. Безопасные `*.example.json` / `*.example.yaml` сохраняют структуру настроек.

Имена приватных параметров приведены в [.env.example](.env.example). Старые значения сохранены только в защищённом локальном хранилище владельца; оно не входит в публикуемый проект. После ротации ключей используйте новые значения.

Проверка исходников и формата настроек не заменяет запуск инфраструктуры и оценку модели. Изменения приватности не подтверждают качество AI, работоспособность внешних API или готовность всей системы к эксплуатации.
