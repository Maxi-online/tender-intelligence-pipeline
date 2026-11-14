"""The main page of the Treamlit Frontend TPIS.

Author: Maxi-online
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
    """Show KPI card.

    :param number: KPI title.
    :param value: KPI value.
    :return: None. Card rendezvous.
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
    """Draw key indicators.

    :param tender_count: Number of tenders.
    :param project_count: Number of projects.
    :param source_count: Number of sources.
    :return: None. KPI Renderite.
    """

    col1, col2, col3 = st.columns(3)
    with col1:
        _kpi_card('Tenders', str(tender_count))
    with col2:
        _kpi_card('Projects', str(project_count))
    with col3:
        _kpi_card('Sources', str(source_count))


def _chart_tenders_by_region(df: pd.DataFrame) -> None:
    """Draw a tender schedule by region.

    :param df: DataFrame tender.
    :return: None. Redenetizes the graph.
    """

    if df.empty or "region" not in df.columns:
        st.info('No data are available for the calendar by region.')
        return
    series = df["region"].value_counts().head(10).reset_index()
    series.columns = ["region", "count"]
    fig = px.bar(series, x="region", y="count", title='Tenders by region (top-10)')
    st.plotly_chart(fig, use_container_width=True)


def _chart_projects_by_stage(df: pd.DataFrame) -> None:
    """Draw a schedule of projects by stage.

    :param df: DataFrame projects.
    :return: None. Redenetizes the graph.
    """

    if df.empty or "stage" not in df.columns:
        st.info("There's no data for the stage graph.")
        return
    series = df["stage"].value_counts().reset_index()
    series.columns = ["stage", "count"]
    fig = px.pie(series, names="stage", values="count", title='Phase projects')
    st.plotly_chart(fig, use_container_width=True)


def main() -> None:
    """Start the main page of Streetlit.

    :return: None. Rendezvous the interface.
    """

    st.set_page_config(
        page_title="TPIS — Tender & Project Intelligence System",
        page_icon="📊",
        layout="wide",
    )
    apply_theme()
    render_sidebar_nav('Home')
    st.title('Projects and tenders')
    st.caption('Summary table: projects, tenders, requisitioners, contractors and contacts.')
    st.markdown(f"** Update date:** {datetime.now().strftime('%d.%m.%Y')}")

    with st.spinner('Loading data...'):
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
        combined_rows.append({'Type': 'Draft', **row})
    for tender in tenders:
        combined_rows.append(
            {
                'Type': 'Tender',
                'Industry': "",
                'Customer': "",
                'Customer phone': "",
                'Customer email': "",
                'Investor': "",
                'Investor phone': "",
                'Investor email': "",
                'Contractor': "",
                'Contractor phone': "",
                'Contractor email': "",
                'Project name': tender.get("title") or "",
                'Project description': "",
                'Source': tender.get("source_url") or "",
                'Region': tender.get("region") or "",
                'Total investment, RUB': tender.get("budget") or "",
                'Estimated geosynthetic materials, RUB': "",
                'Implementation period': tender.get("end_date") or "",
                'Current project stage': tender.get("status") or "",
            }
        )

    df = localize_dataframe(to_dataframe(combined_rows))
    # Add the "Investment Sum, Rub" to the number before display to avoid the Arrow error
    if not df.empty and 'Total investment, RUB' in df.columns:
        df['Total investment, RUB'] = (
            pd.to_numeric(df['Total investment, RUB'], errors="coerce").fillna(0)
        )
    if df.empty:
        st.info('No project data yet.')
    else:
        with st.expander('Table Filters', expanded=True):
            search_text = st.text_input('Search by name, customer, region, etc.')
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                region_values = ['All']
                if 'Region' in df.columns:
                    region_values += sorted(
                        {str(v) for v in df['Region'].dropna().unique() if str(v).strip()}
                    )
                selected_region = st.selectbox('Region', region_values)
            with col2:
                stage_values = ['All']
                if 'Current project stage' in df.columns:
                    stage_values += sorted(
                        {
                            str(v)
                            for v in df['Current project stage'].dropna().unique()
                            if str(v).strip()
                        }
                    )
                selected_stage = st.selectbox('Stage', stage_values)
            with col3:
                budget_min = st.number_input('Budget from', min_value=0.0, step=100000.0)
            with col4:
                budget_max = st.number_input('Budget before', min_value=0.0, step=100000.0)

            only_full = st.checkbox('Show only completed projects', value=False)

        if search_text:
            mask = df.apply(
                lambda row: any(search_text.lower() in str(v).lower() for v in row.values),
                axis=1,
            )
            df = df[mask]
        if selected_region != 'All' and 'Region' in df.columns:
            df = df[df['Region'].astype(str) == selected_region]
        if selected_stage != 'All' and 'Current project stage' in df.columns:
            df = df[df['Current project stage'].astype(str) == selected_stage]
        if 'Total investment, RUB' in df.columns:
            budget_series = df['Total investment, RUB']
            if budget_series.dtype == object:
                budget_series = pd.to_numeric(budget_series, errors="coerce").fillna(0)
            if budget_min > 0:
                df = df[budget_series >= budget_min]
            if budget_max > 0:
                df = df[budget_series <= budget_max]
        if only_full:
            required_cols = [
                'Project name',
                'Region',
                'Total investment, RUB',
                'Current project stage',
            ]
            role_cols = ['Customer', 'Investor', 'Contractor']
            contact_cols = [
                'Customer phone',
                'Customer email',
                'Investor phone',
                'Investor email',
                'Contractor phone',
                'Contractor email',
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

    st.markdown("<div class='section-title'> Loading</div>", unsafe_allow_html=True)
    public_api_base = get_public_api_base()
    st.link_button('download projects at Excel', f"{public_api_base}/export/projects/excel")
    st.link_button('download tenders (CSV)', f"{public_api_base}/export/tenders?format=csv")


if __name__ == "__main__":
    main()
