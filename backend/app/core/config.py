"""TPIS application settings.

Author: Maxi-online
"""

from __future__ import annotations
import os

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """A model of settings downloaded from the environment.

    Attributes:
        app_name: Name of application.
        api_prefix: Prefix of all API-endpoints.
        log_level: Logistical level.
        database_url: DSN to connect to PostgreSQL.
        celery_broker_url: URL Celery broker.
        celery_result_backend: Backend for Celery results.
        update_cycles_per_day: Number of updating cycles per day.
        ingest_loop_interval_seconds: Pause between Permanent Parsing Passages (sec)).
        ingest_recheck_after_seconds: Consider the source “unprocessed” and break again if you have not checked so many seconds (0 = only never checked).
        seldon_base_url: Basic URL Seldon Tenders API (https://apitorgi.myseldon.com)).
        seldon_api_key: Seldon Token (if checked, Login is not called).
        seldon_login: Login for User/Login (if password authorization is needed)).
        seldon_password: The password for User/Login.
        seldon_basis_url: Basic URL Seldon Base API (optimal, for INS contact)).
        seldon_validation_enabled: Insert a check of discharge through LLM (construction subject, garbage)).
        discovery_search_url: URL Source Search (Sable from {query)}).
        discovery_api_key: The key for the source search service.
        export_dir: Unload Catalogue.
        http_proxy_url: Proxie URL to bypass blocks.
        user_agent: User-Agent for source requests.
        request_delay_min: Minimum delay between requests.
        request_delay_max: Maximum delay between requests.
        matching_threshold: Confidence threshold for automatic ligament.
        matching_min_threshold: Minimum threshold for placing in line.
        sources_config_path: Path to source confiscation.
        keywords_config_path: Path to the confiscation of key words.
        perplexity_api_key: The access key to Perplexity API.
        perplexity_base_url: Basic URL Perplexity.
        perplexity_model: Perplexity model for search.
        anthropic_api_key: Key to Anthropic Claude.
        anthropic_base_url: Basic URL Anthropic.
        anthropic_model: Claude's ranking model.
        openrouter_api_key: OpenRouter access key.
        openrouter_base_url: Basic URL OpenRouter.
        openrouter_model: Claude model via OpenRouter.
        openrouter_app_url: URL application for OpenRouter).
        openrouter_app_name: OpenRouter application name).
        openai_settings_path: Path to settings.json for OpenAI.
        openai_model: OpenAI model for Fallback.
        dadata_api_key: The key to Dadata's access.
        dadata_secret_key: Dadata's secret key.
        dadata_mcp_url: URL MCP server of Dadata.
        rusprofile_base_url: Basic URL Rusprofile (if API is used)).
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

    # External LLM/search services
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
    """Return a cached copy of the application settings.

    :return: Application configuration loaded from environment and .env.
    """

    return Settings()
