"""Automation management page (Latin name file for Sidebar)).

Author: Maxi-online
"""

from __future__ import annotations

import json

import streamlit as st

from utils import api_get, api_post, apply_theme, render_sidebar_nav, to_dataframe


def main() -> None:
    'Paint the automation page.'
    st.set_page_config(page_title='TPIS ♪ Automation', page_icon="⚙️", layout="wide")
    apply_theme()
    render_sidebar_nav('Automation')
    st.title('Auto-start data collection')
    st.caption('Start search for tenders and customization projects, view the latest result.')

    status = api_get("/automation/status")
    enabled = bool(status.get("enabled")) if isinstance(status, dict) else False
    last_run = status.get("last_run_at") if isinstance(status, dict) else None
    last_result = status.get("last_result") if isinstance(status, dict) else None

    def _num(value: object) -> int:
        if value is None:
            return 0
        if isinstance(value, bool):
            return int(value)
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    if isinstance(last_result, dict):
        summary_parts = []
        summary_parts.append(
            'New sites added: '
            f"{_num(last_result.get('sources_discovered'))} "
            f"(found) {_num(last_result.get('sources_found'))})"
        )
        leads_raw = last_result.get("perplexity_leads")
        leads = leads_raw if isinstance(leads_raw, dict) else {}
        summary_parts.append(
            'Projects and tenders: '
            f"projects {_num(leads.get('projects'))}, "
            f"Bids {_num(leads.get('tenders'))}, "
            f"Total {_num(leads.get('total_results'))}"
        )
        summary_parts.append(f"Sources processed: {_num(last_result.get('sources'))}")
        summary_parts.append(f"The projects are supplemented by contacts: {_num(last_result.get('projects_enriched'))}")
        summary_parts.append(f"Project duplicates are combined as follows: {_num(last_result.get('projects_deduped'))}")
        summary_parts.append(f"Company duplicates are combined as follows: {_num(last_result.get('companies_deduped'))}")
        summary_parts.append(f"Convergence of tenders with articles: {_num(last_result.get('matches'))}")
        last_result_summary = " | ".join(summary_parts) if summary_parts else 'No data'
    else:
        last_result_summary = last_result if last_result is not None else 'The cycle has not yet started'

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric('Time-bound automatic start-up', 'Entered' if enabled else 'Unplugged')
    with col2:
        st.metric('When was the last time they launched', last_run or "Haven't been launched yet.")
    with col3:
        st.metric('Outcome of the last launch', last_result_summary)

    st.markdown('** Details of last result**')
    leads_raw = last_result.get("perplexity_leads") if isinstance(last_result, dict) else {}
    leads = leads_raw if isinstance(leads_raw, dict) else {}
    if isinstance(last_result, dict):
        details_rows = [
            {'Parameter': 'New sites added to database', 'Value': str(_num(last_result.get("sources_discovered")))},
            {'Parameter': 'All sites found (search)', 'Value': str(_num(last_result.get("sources_found")))},
            {'Parameter': 'Search projects', 'Value': str(_num(leads.get("projects")))},
            {'Parameter': 'Tenders from the search', 'Value': str(_num(leads.get("tenders")))},
            {'Parameter': 'Results of the search for all', 'Value': str(_num(leads.get("total_results")))},
            {'Parameter': 'Sources processed (lents, pages)', 'Value': str(_num(last_result.get("sources")))},
            {'Parameter': 'Projects completed (comments, requisitioner)', 'Value': str(_num(last_result.get("projects_enriched")))},
            {'Parameter': 'Project duplicates combined', 'Value': str(_num(last_result.get("projects_deduped")))},
            {'Parameter': 'Company duplicates combined', 'Value': str(_num(last_result.get("companies_deduped")))},
            {'Parameter': 'Convergence of tenders with articles', 'Value': str(_num(last_result.get("matches")))},
        ]
        details_df = to_dataframe(details_rows).astype(str)
        st.dataframe(details_df, use_container_width=True, hide_index=True)
    else:
        st.info(
            'The collection hasn\'t started yet. Press "Stop Collection Now" or "Text Launch"», '
            "I'm here to fill out the table of results."
        )
        details_rows = [
            {'Parameter': 'New sites added to database', 'Value': "0"},
            {'Parameter': 'All sites found (search)', 'Value': "0"},
            {'Parameter': 'Search projects', 'Value': "0"},
            {'Parameter': 'Tenders from the search', 'Value': "0"},
            {'Parameter': 'Results of the search for all', 'Value': "0"},
            {'Parameter': 'Sources processed (lents, pages)', 'Value': "0"},
            {'Parameter': 'Projects completed (comments, requisitioner)', 'Value': "0"},
            {'Parameter': 'Project duplicates combined', 'Value': "0"},
            {'Parameter': 'Company duplicates combined', 'Value': "0"},
            {'Parameter': 'Convergence of tenders with articles', 'Value': "0"},
        ]
        details_df = to_dataframe(details_rows).astype(str)
        st.dataframe(details_df, use_container_width=True, hide_index=True)

    st.markdown('### Launching the collection')
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button('Start collection now'):
            api_post("/automation/start")
            st.success('Collection in line. The results will be available in a few minutes.')
    with c2:
        if st.button('Shut down on schedule'):
            api_post("/automation/stop")
            st.success('Auto-start off.')
    with c3:
        if st.button('Test launch (small requests)'):
            api_post("/automation/start_test")
            st.success('The test collection is in line.')

    st.markdown('### Dangerous actions')
    if st.button('Remove all projects from the base'):
        result = api_post("/projects/clear")
        deleted = result.get("deleted") if isinstance(result, dict) else None
        st.success(f"The projects have been deleted: {deleted if deleted is not None else 'Ready.'}.")


if __name__ == "__main__":
    main()
