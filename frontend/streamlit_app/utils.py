"""Утилиты для Streamlit фронтенда TPIS.

Автор: Maxi-online
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

import httpx
import pandas as pd
import streamlit as st


def _default_api_base() -> str:
    """Базовый URL API: в Docker — backend:8001, локально — localhost:8001."""
    base = os.getenv("TPIS_API_BASE", "").strip()
    if base:
        base = base.rstrip("/")
        return f"{base}/api" if not base.endswith("/api") else base
    # В контейнере фронтенд обращается к backend по имени сервиса
    if os.path.exists("/.dockerenv") or os.getenv("RUNNING_IN_DOCKER"):
        return "http://backend:8001/api"
    return "http://localhost:8001/api"


API_BASE = _default_api_base()
PUBLIC_API_BASE = os.getenv("TPIS_PUBLIC_API_BASE", "").strip()
if not PUBLIC_API_BASE:
    if "backend:8001" in API_BASE:
        PUBLIC_API_BASE = "http://localhost:8001/api"
    else:
        PUBLIC_API_BASE = API_BASE


def get_public_api_base() -> str:
    """Получить публичный URL API для ссылок в браузере.

    :return: Базовый URL API.
    """

    return PUBLIC_API_BASE


def _normalize_value(value: Any) -> str:
    """Нормализовать значение для безопасного отображения в UI.

    :param value: Произвольное значение.
    :return: Строковое представление значения.
    """

    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def normalize_tenders(rows: list[dict]) -> list[dict]:
    """Нормализовать список тендеров.

    :param rows: Список словарей тендеров.
    :return: Нормализованный список.
    """

    normalized = []
    for row in rows:
        normalized.append(
            {
                "tender_id": _normalize_value(row.get("tender_id")),
                "title": _normalize_value(row.get("title")),
                "region": _normalize_value(row.get("region")),
                "budget": _normalize_value(row.get("budget")),
                "currency": _normalize_value(row.get("currency")),
                "status": _normalize_value(row.get("status")),
                "winner": _normalize_value(row.get("winner")),
                "participants": _normalize_value(row.get("participants")),
                "contacts": _normalize_value(row.get("contacts")),
                "source_url": _normalize_value(row.get("source_url")),
                "stage": _normalize_value(row.get("stage")),
                "start_date": _normalize_value(row.get("start_date")),
                "end_date": _normalize_value(row.get("end_date")),
            }
        )
    return normalized


def normalize_projects(rows: list[dict]) -> list[dict]:
    """Нормализовать список проектов.

    :param rows: Список словарей проектов.
    :return: Нормализованный список.
    """

    normalized = []
    for row in rows:
        normalized.append(
            {
                "id": _normalize_value(row.get("id")),
                "name": _normalize_value(row.get("name")),
                "region": _normalize_value(row.get("region")),
                "stage": _normalize_value(row.get("stage")),
                "budget": _normalize_value(row.get("budget")),
                "start_date": _normalize_value(row.get("start_date")),
                "end_date": _normalize_value(row.get("end_date")),
            }
        )
    return normalized


def normalize_sources(rows: list[dict]) -> list[dict]:
    """Нормализовать список источников.

    :param rows: Список словарей источников.
    :return: Нормализованный список.
    """

    normalized = []
    for row in rows:
        normalized.append(
            {
                "id": _normalize_value(row.get("id")),
                "name": _normalize_value(row.get("name")),
                "url": _normalize_value(row.get("url")),
                "kind": _normalize_value(row.get("kind")),
                "status": _normalize_value(row.get("status")),
            }
        )
    return normalized


def to_dataframe(rows: list[dict]) -> pd.DataFrame:
    """Преобразовать список словарей в DataFrame.

    :param rows: Список словарей.
    :return: DataFrame для отображения.
    """

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def localize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Переименовать колонки таблицы на русский язык.

    :param df: DataFrame с исходными колонками.
    :return: DataFrame с локализованными колонками.
    """

    mapping = {
        "id": "ID",
        "tender_id": "ID тендера",
        "title": "Название",
        "name": "Название",
        "region": "Регион",
        "budget": "Бюджет",
        "currency": "Валюта",
        "status": "Статус",
        "winner": "Победитель",
        "participants": "Участники",
        "contacts": "Контакты",
        "source_url": "Ссылка",
        "source": "Источник",
        "stage": "Стадия",
        "start_date": "Дата начала",
        "end_date": "Дата окончания",
        "url": "Ссылка",
        "published_at": "Дата публикации",
        "label": "Метка",
        "quality_flag": "Флаг качества",
        "kind": "Тип",
        "type": "Тип",
        "score": "Сходство",
        "field": "Поле",
        "seldon": "Seldon",
        "media": "СМИ",
        "confidence_score": "Уверенность",
        "approved": "Подтверждено",
        "reviewer": "Оператор",
        "reviewed_at": "Дата проверки",
    }
    rename_map = {col: mapping[col] for col in df.columns if col in mapping}
    if not rename_map:
        return df
    return df.rename(columns=rename_map)


def api_get(path: str, params: dict | None = None) -> Any:
    """Выполнить GET запрос к API."""
    url = f"{API_BASE}{path}"
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def api_post(path: str, payload: dict | None = None, *, method: str = "POST") -> Any:
    """Выполнить запрос к API (POST/PUT/DELETE)."""
    url = f"{API_BASE}{path}"
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        response = client.request(method.upper(), url, json=payload)
        response.raise_for_status()
        return response.json()


# Соответствие русских подписей сайдбара и путей к страницам (латинские имена файлов)
_SIDEBAR_PAGES = [
    ("Главная", "Главная.py"),
    ("Настройки поиска", "pages/2_Search.py"),
    ("Источники и PDF", "pages/3_Sources.py"),
    ("Автоматизация", "pages/4_Automation.py"),
    ("Seldon API", "pages/5_Seldon_API.py"),
]


def render_sidebar_nav(current_label: str) -> None:
    """Показать в сайдбаре навигацию с русскими подписями и переключить страницу при выборе.

    :param current_label: Подпись текущей страницы (одна из: Главная, Настройки поиска, Источники и PDF, Автоматизация).
    :return: None.
    """
    labels = [label for label, _ in _SIDEBAR_PAGES]
    try:
        idx = next(i for i, (label, _) in enumerate(_SIDEBAR_PAGES) if label == current_label)
    except StopIteration:
        idx = 0
    selected = st.sidebar.radio("Раздел", labels, index=idx, label_visibility="collapsed")
    if selected != current_label:
        path = next((path for label, path in _SIDEBAR_PAGES if label == selected), None)
        if path:
            st.switch_page(path)


def apply_theme() -> None:
    """Применить базовую тему и стилизацию Streamlit.

    :return: None. Добавляет CSS и оформление.
    """
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
        .metric-card { padding: 1rem; border-radius: 12px; background: #0F172A; color: #F8FAFC; }
        .metric-card h3 { margin: 0; font-size: 0.9rem; color: #CBD5F5; }
        .metric-card p { margin: 0; font-size: 1.4rem; font-weight: 700; }
        .section-title { font-weight: 700; font-size: 1.1rem; margin-top: 1rem; }
        /* Скрыть стандартный список страниц Streamlit — навигация через render_sidebar_nav с русскими подписями */
        section[data-testid="stSidebarNav"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )

