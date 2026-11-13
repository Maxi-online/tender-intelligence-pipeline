"""Главная страница Streamlit фронтенда TPIS.

Автор: Maxi-online
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import (
    api_get,
    apply_theme,
    get_public_api_base,
    localize_dataframe,
    normalize_projects,
    normalize_sources,
    normalize_tenders,
    render_sidebar_nav,
    to_dataframe,
)


def _kpi_card(title: str, value: str) -> None:
    """Показать KPI карточку.

    :param title: Заголовок KPI.
    :param value: Значение KPI.
    :return: None. Рендерит карточку.
    """

    st.markdown(
        f"""
        <div class="metric-card">
            <h3>{title}</h3>
            <p>{value}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_kpis(tender_count: int, project_count: int, source_count: int) -> None:
    """Отрисовать ключевые показатели.

    :param tender_count: Количество тендеров.
    :param project_count: Количество проектов.
    :param source_count: Количество источников.
    :return: None. Рендерит KPI.
    """

    col1, col2, col3 = st.columns(3)
    with col1:
        _kpi_card("Тендеров", str(tender_count))
    with col2:
        _kpi_card("Проектов", str(project_count))
    with col3:
        _kpi_card("Источников", str(source_count))


def _chart_tenders_by_region(df: pd.DataFrame) -> None:
    """Построить график тендеров по регионам.

    :param df: DataFrame тендеров.
    :return: None. Рендерит график.
    """

    if df.empty or "region" not in df.columns:
        st.info("Нет данных для графика по регионам.")
        return
    series = df["region"].value_counts().head(10).reset_index()
    series.columns = ["region", "count"]
    fig = px.bar(series, x="region", y="count", title="Тендеры по регионам (топ-10)")
    st.plotly_chart(fig, use_container_width=True)


def _chart_projects_by_stage(df: pd.DataFrame) -> None:
    """Построить график проектов по стадиям.

    :param df: DataFrame проектов.
    :return: None. Рендерит график.
    """

    if df.empty or "stage" not in df.columns:
        st.info("Нет данных для графика по стадиям.")
        return
    series = df["stage"].value_counts().reset_index()
    series.columns = ["stage", "count"]
    fig = px.pie(series, names="stage", values="count", title="Проекты по стадиям")
    st.plotly_chart(fig, use_container_width=True)


def main() -> None:
    """Запустить главную страницу Streamlit.

    :return: None. Рендерит интерфейс.
    """

    st.set_page_config(
        page_title="TPIS — Tender & Project Intelligence System",
        page_icon="📊",
        layout="wide",
    )
    apply_theme()
    render_sidebar_nav("Главная")
    st.title("Проекты и тендеры")
    st.caption("Сводная таблица: проекты, тендеры, заказчики, подрядчики и контакты.")
    st.markdown(f"**Дата обновления:** {datetime.now().strftime('%d.%m.%Y')}")

    with st.spinner("Загрузка данных..."):
        report_rows = api_get("/reports/projects")
        tenders = normalize_tenders(api_get("/tenders", params={"limit": 500}))
        projects = normalize_projects(api_get("/projects", params={"limit": 500}))
        sources = normalize_sources(api_get("/sources", params={"limit": 500}))
        project_count = api_get("/projects/count")
        source_count = api_get("/sources/count")

    _render_kpis(
        len(tenders),
        int(project_count.get("count", len(projects))) if isinstance(project_count, dict) else len(projects),
        int(source_count.get("count", len(sources))) if isinstance(source_count, dict) else len(sources),
    )

    combined_rows: list[dict] = []
    for row in report_rows:
        combined_rows.append({"Тип": "Проект", **row})
    for tender in tenders:
        combined_rows.append(
            {
                "Тип": "Тендер",
                "Отрасль": "",
                "Заказчик": "",
                "Телефон заказчика": "",
                "Email заказчика": "",
                "Инвестор": "",
                "Телефон инвестора": "",
                "Email инвестора": "",
                "Подрядчик": "",
                "Телефон подрядчика": "",
                "Email подрядчика": "",
                "Наименование проекта": tender.get("title") or "",
                "Описание проекта": "",
                "Источник": tender.get("source_url") or "",
                "Регион": tender.get("region") or "",
                "Сумма инвестиций общая, руб": tender.get("budget") or "",
                "Объем геосинтетических материалов в смете, руб": "",
                "Срок реализации": tender.get("end_date") or "",
                "Текущая стадия проекта": tender.get("status") or "",
            }
        )

    df = localize_dataframe(to_dataframe(combined_rows))
    # Привести «Сумма инвестиций общая, руб» к числу до отображения, чтобы избежать ошибки Arrow
    if not df.empty and "Сумма инвестиций общая, руб" in df.columns:
        df["Сумма инвестиций общая, руб"] = (
            pd.to_numeric(df["Сумма инвестиций общая, руб"], errors="coerce").fillna(0)
        )
    if df.empty:
        st.info("Данных по проектам пока нет.")
    else:
        with st.expander("Фильтры таблицы", expanded=True):
            search_text = st.text_input("Поиск по названию, заказчику, региону и т.д.")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                region_values = ["Все"]
                if "Регион" in df.columns:
                    region_values += sorted(
                        {str(v) for v in df["Регион"].dropna().unique() if str(v).strip()}
                    )
                selected_region = st.selectbox("Регион", region_values)
            with col2:
                stage_values = ["Все"]
                if "Текущая стадия проекта" in df.columns:
                    stage_values += sorted(
                        {
                            str(v)
                            for v in df["Текущая стадия проекта"].dropna().unique()
                            if str(v).strip()
                        }
                    )
                selected_stage = st.selectbox("Стадия", stage_values)
            with col3:
                budget_min = st.number_input("Бюджет от", min_value=0.0, step=100000.0)
            with col4:
                budget_max = st.number_input("Бюджет до", min_value=0.0, step=100000.0)

            only_full = st.checkbox("Показывать только заполненные проекты", value=False)

        if search_text:
            mask = df.apply(
                lambda row: any(search_text.lower() in str(v).lower() for v in row.values),
                axis=1,
            )
            df = df[mask]
        if selected_region != "Все" and "Регион" in df.columns:
            df = df[df["Регион"].astype(str) == selected_region]
        if selected_stage != "Все" and "Текущая стадия проекта" in df.columns:
            df = df[df["Текущая стадия проекта"].astype(str) == selected_stage]
        if "Сумма инвестиций общая, руб" in df.columns:
            budget_series = df["Сумма инвестиций общая, руб"]
            if budget_series.dtype == object:
                budget_series = pd.to_numeric(budget_series, errors="coerce").fillna(0)
            if budget_min > 0:
                df = df[budget_series >= budget_min]
            if budget_max > 0:
                df = df[budget_series <= budget_max]
        if only_full:
            required_cols = [
                "Наименование проекта",
                "Регион",
                "Сумма инвестиций общая, руб",
                "Текущая стадия проекта",
            ]
            role_cols = ["Заказчик", "Инвестор", "Подрядчик"]
            contact_cols = [
                "Телефон заказчика",
                "Email заказчика",
                "Телефон инвестора",
                "Email инвестора",
                "Телефон подрядчика",
                "Email подрядчика",
            ]

            def _is_empty(value: object) -> bool:
                if value is None:
                    return True
                text = str(value).strip()
                if not text:
                    return True
                lowered = text.lower()
                return lowered in {"none", "nan", "null"}

            def _is_full_row(row: pd.Series) -> bool:
                for col in required_cols:
                    if col in row and _is_empty(row[col]):
                        return False
                has_role = any(
                    col in row and not _is_empty(row[col]) for col in role_cols
                )
                has_contact = any(
                    col in row and not _is_empty(row[col]) for col in contact_cols
                )
                return has_role and has_contact

            df = df[df.apply(_is_full_row, axis=1)]

        st.dataframe(df, use_container_width=True, hide_index=True, height=650)

    st.markdown("<div class='section-title'>Выгрузка</div>", unsafe_allow_html=True)
    public_api_base = get_public_api_base()
    st.link_button("Скачать проекты в Excel", f"{public_api_base}/export/projects/excel")
    st.link_button("Скачать тендеры (CSV)", f"{public_api_base}/export/tenders?format=csv")


if __name__ == "__main__":
    main()
