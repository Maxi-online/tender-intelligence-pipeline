'Seldon API tab: up-to-date information on customers and winners (not participating in tenders)).'

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from utils import api_get, api_post, apply_theme, render_sidebar_nav, to_dataframe


def main() -> None:
    'Paint the Seldon API page.'
    st.set_page_config(page_title="TPIS | Seldon API", page_icon="📋", layout="wide")
    apply_theme()
    render_sidebar_nav("Seldon API")
    st.title('Seldon API module')
    st.caption(
        'Objective: To provide as up-to-date information as possible on customer and winner participants. '
        'Tenders as counterparty data source (INN, contacts)). First, download the data into the cache.'
    )

    mode = st.radio(
        'Mode',
        [
            'Upload Seldon data',
            'Winner on tender',
            'Buyers and contacts on INS',
            'Tender participants',
            'List of tenders',
            'I.D. Details',
        ],
        horizontal=True,
    )

    try:
        if mode == 'Upload Seldon data':
            st.subheader('Upload Seldon data')
            st.caption('GPT will select the filter and the period to the target. One click — Recommendation and Unload.')
            search_goal = st.text_input(
                'Search Purpose (may not change)',
                value='Buyers and winners in construction and capacitation, public procurement 44-FZ',
                label_visibility="collapsed",
            )
            if st.button('Start Synchronization'):
                with st.spinner('GPT selects settings, then unloads...'):
                    resp = api_post("/seldon/sync", payload={"search_goal": search_goal or 'Buyers and winners in construction, government procurement 44-FZ'})
                st.success(f"Ready: Established {resp.get('created', 0)}updated {resp.get('updated', 0)}total {resp.get('total', 0)}")
                st.json(resp)

        elif mode == 'List of tenders':
            st.subheader('Cache tender list')
            limit = st.number_input("limit", min_value=1, max_value=100, value=20)
            offset = st.number_input("offset", min_value=0, value=0)
            if st.button('Request our APl'):
                data = api_get(f"/seldon/tenders?limit={limit}&offset={offset}")
                if isinstance(data, list) and data:
                    df = to_dataframe(data)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info('There\'s no record in the cash. First, do "To load data from Seldon».')

        elif mode == 'I.D. Details':
            st.subheader('seldon_id tender details')
            tender_id = st.text_input("tender_id (seldon_id)", value="")
            if st.button('Request our APl') and tender_id:
                data = api_get(f"/seldon/tenders/{tender_id}")
                if isinstance(data, dict):
                    st.json(data)
                else:
                    st.warning('No tender found.')

        elif mode == 'Tender participants':
            st.subheader('Participants in procurement (applications, admissions) for ID')
            tender_id = st.text_input("tender_id", value="")
            if st.button('Request our APl') and tender_id:
                data = api_get(f"/seldon/tenders/{tender_id}/participants")
                if isinstance(data, list) and data:
                    df = to_dataframe(data)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info('Participants are not found or tender is missing in the cash.')

        elif mode == 'Winner on tender':
            st.subheader('Winner ( up-to-date performance data) for ID procurement')
            tender_id = st.text_input("tender_id", value="")
            if st.button('Request our APl') and tender_id:
                data = api_get(f"/seldon/tenders/{tender_id}/winner")
                if isinstance(data, dict):
                    st.json(data)
                else:
                    st.warning('No tender found.')

        elif mode == 'Buyers and contacts on INS':
            st.subheader('Buyers and INS contacts (relevant data)')
            inn = st.text_input('INN (or company_id)', value="")
            if st.button('Request our APl') and inn:
                data = api_get(f"/seldon/contacts?inn={inn}")
                if isinstance(data, list) and data:
                    df = to_dataframe(data)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("There's no contact on this I.N.A. in the cache.")
    except Exception as e:
        st.error(f"mistake: {e}")

    st.markdown("---")
    st.subheader('Source: Seldon Filters')
    if st.button('Get filter list'):
        try:
            filters = api_get("/seldon/filters")
            if isinstance(filters, list) and filters:
                df = to_dataframe(filters)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning('Could not obtain filters (check Seldon settings)).')
        except Exception as ex:
            st.error(str(ex))


if __name__ == "__main__":
    main()
