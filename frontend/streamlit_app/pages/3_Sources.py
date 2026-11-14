"""Source page and PDF (Latin name file for Sidebar)).

Author: Maxi-online
"""

from __future__ import annotations

import streamlit as st

from utils import API_BASE, api_get, api_post, apply_theme, render_sidebar_nav, localize_dataframe, normalize_sources, to_dataframe


def main() -> None:
    'Draw the source page and PDF.'
    st.set_page_config(page_title='TPIS * Sources and PDF', page_icon="🛰️", layout="wide")
    apply_theme()
    render_sidebar_nav('Sources and PDF')
    st.title('Data sources')
    st.caption('Sites, news bands, articles and PDF download for drawing projects and tender.')

    with st.expander('➕ Add website or tape manually', expanded=False):
        name = st.text_input('Name (how to be displayed)')
        url = st.text_input('Reference (URL)')
        kind = st.selectbox(
            'Source type',
            ["html", "rss", "sitemap", "api"],
            index=0,
            format_func=lambda v: {"html": 'Regular Page (HTML)', "rss": 'Newscast (RSS)', "sitemap": 'Website map', "api": "API"}[v],
        )
        if st.button('Add Source'):
            if not url:
                st.error("Please specify the source's URL.")
            else:
                api_post(
                    "/sources",
                    {
                        "name": name or url,
                        "url": url,
                        "kind": kind,
                        "status": "active",
                        "auto_discovered": False,
                    },
                )
                st.success('The source is created.')

    with st.expander('🔍 Find sites by word', expanded=False):
        query = st.text_input('Enter a word or phrase (e.g.: construction)')
        if st.button('Search'):
            if not query:
                st.error('Enter word for search.')
            else:
                results = api_get("/sources/discover", params={"query": query})
                df_results = localize_dataframe(to_dataframe(results))
                st.dataframe(df_results, use_container_width=True, hide_index=True)
        st.caption(
            'The mass search for sources is started on the Automation page with the button "Stop collection"».'
        )

    st.markdown('### List of sources')
    with st.spinner('Loading...'):
        sources = normalize_sources(api_get("/sources"))
    df = localize_dataframe(to_dataframe(sources))
    if df.empty:
        st.info('There are no added sources yet.')
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown('## News and articles from sources')
    with st.spinner('Loading articles...'):
        articles = api_get("/articles", params={"limit": 200})
    df_articles = to_dataframe(articles)
    if df_articles.empty:
        st.info('No statues yet.')
    else:
        df_view = df_articles[
            [
                "id",
                "source",
                "title",
                "url",
                "published_at",
                "label",
                "quality_flag",
            ]
        ]
        df_view = localize_dataframe(df_view)
        st.dataframe(
            df_view,
            use_container_width=True,
            column_config={
                'Link': st.column_config.LinkColumn('Link'),
            },
            hide_index=True,
        )

    st.markdown('### Download PDF and extract projects')
    st.markdown(
        'Load the PDF -- the system recognizes the text and adds the found projects and tenders to the general table.'
    )
    uploaded_file = st.file_uploader('Select PDF file', type=["pdf"])

    col1, col2 = st.columns(2)
    with col1:
        entity_type = st.selectbox(
            'Where to tie the result',
            ["article", "project", "tender", "company"],
            format_func=lambda v: {
                "article": 'Save as article/source',
                "project": 'Link to project',
                "tender": 'Tie to tender',
                "company": 'Tie to company',
            }[v],
        )
    with col2:
        entity_id = st.text_input('Project number/Tender/companie (if tied)', placeholder="Leave it empty if you don't need it.")

    if st.button('Download and extract data from PDF'):
        if not uploaded_file:
            st.error('Select PDF file first.')
        else:
            import requests

            params = {
                "entity_type": entity_type,
                "entity_id": entity_id or "",
            }
            headers = {"Content-Type": "application/pdf"}
            with st.spinner('Sending file and recognition...'):
                resp = requests.post(
                    f"{API_BASE}/documents/upload_pdf",
                    params=params,
                    data=uploaded_file.getvalue(),
                    headers=headers,
                    timeout=120,
                )
            if not resp.ok:
                st.error(f"Error in charging: {resp.status_code} {resp.text}")
                return
            payload = resp.json()

            st.subheader('Result')
            st.write(f"Mode: {payload.get('mode')}")
            article_id = payload.get("article_id")
            if article_id:
                st.write(f"Article retained in base (ID = {article_id})")

            projects = payload.get("projects_created") or []
            if not projects:
                st.info('In this PDF, no projects were found or were already in the database.')
            else:
                st.markdown('#### Added projects to the database')
                for p in projects:
                    st.write(f"- [#{p.get('id')}] {p.get('name')}")


if __name__ == "__main__":
    main()
