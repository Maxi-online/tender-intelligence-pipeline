"""Utilities for Treamlit Frontend TPIS.

Author: Maxi-online
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
    '== sync, corrected by elderman == @elder_man.'
    base = os.getenv("TPIS_API_BASE", "").strip()
    if base:
        base = base.rstrip("/")
        return f"{base}/api" if not base.endswith("/api") else base
    # In the container, the frontand calls backend by the name of the service
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
    """Get a public URL API for links in the browser.

    :return: Core URL API.
    """

    return PUBLIC_API_BASE


def _normalize_value(value: Any) -> str:
    """Normalize value for safe display in UI.

    :param value: Arbitrary value.
    :return: Static value presentation.
    """

    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def normalize_tenders(rows: list[dict]) -> list[dict]:
    """Normalize the tender list.

    :param rows: List of tender dictionary.
    :return: Normalized list.
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
    """Normalize the project list.

    :param rows: List of project dictionaries.
    :return: Normalized list.
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
    """Normalize the source list.

    :param rows: List of dictionaries of sources.
    :return: Normalized list.
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
    """Transform the list of dictionaries into DataFrame.

    :param rows: List of dictionaries.
    :return: DataFrame for display.
    """

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def localize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Rename the table columns as Russian.

    :param df: DataFrame with reference columns.
    :return: DataFrame with localized columns.
    """

    mapping = {
        "id": "ID",
        "tender_id": 'Tender ID',
        "title": 'Name',
        "name": 'Name',
        "region": 'Region',
        "budget": 'Budget',
        "currency": 'Currency',
        "status": 'Status',
        "winner": 'Winner',
        "participants": 'Participants',
        "contacts": 'Contacts',
        "source_url": 'Link',
        "source": 'Source',
        "stage": 'Stage',
        "start_date": 'Start date',
        "end_date": 'End date',
        "url": 'Link',
        "published_at": 'Publication date',
        "label": 'Label',
        "quality_flag": 'Quality flag',
        "kind": 'Type',
        "type": 'Type',
        "score": 'Similarity',
        "field": 'Field',
        "seldon": "Seldon",
        "media": 'Media',
        "confidence_score": 'Confidence',
        "approved": 'Confirmed',
        "reviewer": 'Operator',
        "reviewed_at": 'Review date',
    }
    rename_map = {col: mapping[col] for col in df.columns if col in mapping}
    if not rename_map:
        return df
    return df.rename(columns=rename_map)


def api_get(path: str, params: dict | None = None) -> Any:
    'Implement GET request to API.'
    url = f"{API_BASE}{path}"
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def api_post(path: str, payload: dict | None = None, *, method: str = "POST") -> Any:
    'Do a request for API (POST/PUT/DELETE).'
    url = f"{API_BASE}{path}"
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        response = client.request(method.upper(), url, json=payload)
        response.raise_for_status()
        return response.json()


# Conformity of Russian signatures of Sidebar and page routes (Latin file names))
_SIDEBAR_PAGES = [
    ('Home', 'Main.py'),
    ('Search settings', "pages/2_Search.py"),
    ('Sources and PDF', "pages/3_Sources.py"),
    ('Automation', "pages/4_Automation.py"),
    ("Seldon API", "pages/5_Seldon_API.py"),
]


def render_sidebar_nav(current_label: str) -> None:
    """Show navigation with Russian signatures in the Sidebar and switch the page to select.

    :param current_label: Signature of the current page (one of: Main, Search Settings, Sources and PDF, Automation).
    :return: None.
    """
    labels = [label for label, _ in _SIDEBAR_PAGES]
    try:
        idx = next(i for i, (label, _) in enumerate(_SIDEBAR_PAGES) if label == current_label)
    except StopIteration:
        idx = 0
    selected = st.sidebar.radio('Section', labels, index=idx, label_visibility="collapsed")
    if selected != current_label:
        path = next((path for label, path in _SIDEBAR_PAGES if label == selected), None)
        if path:
            st.switch_page(path)


def apply_theme() -> None:
    """Apply the basic theme and Streamlit style.

    :return: None. Adds CSS and configuration.
    """
    st.markdown(
        '\n        <style>\n        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }\n        .metric-card { padding: 1rem; border-radius: 12px; background: #0F172A; color: #F8FAFC; }\n        .metric-card h3 { margin: 0; font-size: 0.9rem; color: #CBD5F5; }\n        .metric-card p { margin: 0; font-size: 1.4rem; font-weight: 700; }\n        .section-title { font-weight: 700; font-size: 1.1rem; margin-top: 1rem; }\n        /* Hide Streamlit\'s standard list of pages — navigation via render_sidebar_nav with Russian signatures */\n        section[data-testid="stSidebarNav"] { display: none; }\n        </style>\n        ',
        unsafe_allow_html=True,
    )

