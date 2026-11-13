"""Настройки приложения TPIS.

Автор: Maxi-online
"""

from __future__ import annotations
import os

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Модель настроек, загружаемых из окружения.

    Атрибуты:
        app_name: Название приложения.
        api_prefix: Префикс всех API-эндпоинтов.
        log_level: Уровень логирования.
        database_url: DSN для подключения к PostgreSQL.
        celery_broker_url: URL брокера Celery.
        celery_result_backend: Backend для результатов Celery.
        update_cycles_per_day: Количество циклов обновления в сутки.
        ingest_loop_interval_seconds: Пауза между проходами постоянного парсинга (сек).
        ingest_recheck_after_seconds: Считать источник «необработанным» и парсить снова, если не проверяли столько секунд (0 = только никогда не проверенные).
        seldon_base_url: Базовый URL Seldon Tenders API (https://apitorgi.myseldon.com).
        seldon_api_key: Токен Seldon (если задан, Login не вызывается).
        seldon_login: Логин для User/Login (если нужна авторизация по паролю).
        seldon_password: Пароль для User/Login.
        seldon_basis_url: Базовый URL Seldon Basis API (опционально, для контактов по ИНН).
        seldon_validation_enabled: Включить проверку выгрузки через LLM (строительная тематика, мусор).
        discovery_search_url: URL поиска источников (шаблон с {query}).
        discovery_api_key: Ключ для сервиса поиска источников.
        export_dir: Каталог для выгрузок.
        http_proxy_url: Прокси URL для обхода блокировок.
        user_agent: User-Agent для запросов к источникам.
        request_delay_min: Минимальная задержка между запросами.
        request_delay_max: Максимальная задержка между запросами.
        matching_threshold: Порог уверенности для автоматической связки.
        matching_min_threshold: Минимальный порог для постановки в очередь.
        sources_config_path: Путь к конфигу источников.
        keywords_config_path: Путь к конфигу ключевых слов.
        perplexity_api_key: Ключ доступа к Perplexity API.
        perplexity_base_url: Базовый URL Perplexity.
        perplexity_model: Модель Perplexity для поиска.
        anthropic_api_key: Ключ доступа к Anthropic Claude.
        anthropic_base_url: Базовый URL Anthropic.
        anthropic_model: Модель Claude для ранжирования.
        openrouter_api_key: Ключ доступа к OpenRouter.
        openrouter_base_url: Базовый URL OpenRouter.
        openrouter_model: Модель Claude через OpenRouter.
        openrouter_app_url: URL приложения для OpenRouter (опционально).
        openrouter_app_name: Название приложения для OpenRouter (опционально).
        openai_settings_path: Путь к settings.json для OpenAI.
        openai_model: Модель OpenAI для fallback.
        dadata_api_key: Ключ доступа к Dadata.
        dadata_secret_key: Секретный ключ Dadata.
        dadata_mcp_url: URL MCP-сервера Dadata.
        rusprofile_base_url: Базовый URL Rusprofile (если используется API).
    """

    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"], env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Tender Intelligence Backend"
    api_prefix: str = "/api"
    log_level: str = "INFO"

    database_url: str
    celery_broker_url: str
    celery_result_backend: str = "rpc://"

    update_cycles_per_day: int = 4
    ingest_loop_interval_seconds: float = 300.0
    ingest_recheck_after_seconds: float = 21600.0
    seldon_base_url: str = ""
    seldon_api_key: str | None = None
    seldon_login: str | None = None
    seldon_password: str | None = None
    seldon_basis_url: str = ""
    seldon_validation_enabled: bool = False
    discovery_search_url: str | None = None
    discovery_api_key: str | None = None
    export_dir: str = "exports"
    http_proxy_url: str | None = None
    user_agent: str = "TenderIntelligenceBot/1.0"
    request_delay_min: float = 0.5
    request_delay_max: float = 2.0
    matching_threshold: float = 0.75
    matching_min_threshold: float = 0.3
    sources_config_path: str = "config/sources.yaml"
    keywords_config_path: str = "config/keywords.yaml"

    # Внешние LLM/поисковые сервисы
    perplexity_api_key: str | None = None
    perplexity_base_url: str = "https://api.perplexity.ai"
    perplexity_model: str = "sonar-small-online"

    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str | None = None
    openrouter_app_url: str | None = None
    openrouter_app_name: str | None = None
    openai_settings_path: str = "config/settings.json"
    openai_model: str = "gpt-5-nano"

    # Dadata / Rusprofile
    dadata_api_key: str | None = None
    dadata_secret_key: str | None = None
    dadata_mcp_url: str = "https://mcp.dadata.ru/mcp"
    rusprofile_base_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Вернуть кэшированный экземпляр настроек приложения.

    :return: Конфигурация приложения, загруженная из окружения и .env.
    """

    return Settings()
