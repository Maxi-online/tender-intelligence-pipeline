"""Search configuration page (Latin name file for Sidebar)).

Author: Maxi-online
"""

from __future__ import annotations

import streamlit as st

from utils import api_get, api_post, apply_theme, render_sidebar_nav, localize_dataframe, to_dataframe


def main() -> None:
    'Draw a search configuration page.'
    st.set_page_config(page_title='TPIS ♪ Search Settings Original: ENGLISH', page_icon="🔎", layout="wide")
    apply_theme()
    render_sidebar_nav('Search settings')
    st.title('Search settings')
    st.caption('Set the topics on which to seek tenders and projects, and how many results per launch.')

    st.markdown("---")
    st.markdown("### What we're looking for: themes and key words")
    st.markdown(
        'The system is searching for the ** key words** (e.g.: construction, reconstruction, chaperone)). '
        'You can choose a ready set or create your own.'
    )

    keyword_sets = api_get("/keyword-sets")
    if not isinstance(keyword_sets, list):
        keyword_sets = []

    if not keyword_sets:
        st.info("There's not a single set of key words yet. Create a new one below.")
        selected_set_id = None
        selected_set = None
    else:
        options = {f"{item.get('name')} (#{item.get('id')})": item for item in keyword_sets}
        label = st.selectbox(
            'Select a set of key words',
            list(options.keys()),
            key="kw_select",
        )
        selected_set = options.get(label)
        selected_set_id = selected_set.get("id") if selected_set else None

    with st.expander('➕ Create a new set of key words', expanded=False):
        st.markdown('Name and list words or short sentences (one per line)).')
        new_name = st.text_input('Set Name', placeholder='For example: Construction tenders', key="new_kw_set_name")
        new_desc = st.text_area(
            'Description (optional)',
            placeholder='In short, what is this set for?',
            key="new_kw_set_desc",
        )
        new_keywords_raw = st.text_area(
            'Keywords or phrases, one per line',
            placeholder="строительство\nреконструкция\nкапитальный ремонт\nкапремонт",
            key="new_kw_set_keywords",
        )
        new_author = st.text_input('Who created (optional)', key="new_kw_set_author")
        if st.button('Create Set'):
            if not new_name:
                st.error('Please specify the name of the kit.')
            else:
                keywords_payload = []
                for line in new_keywords_raw.splitlines():
                    text = line.strip()
                    if not text:
                        continue
                    keywords_payload.append({"text": text, "weight": 1.0})
                api_post(
                    "/keyword-sets",
                    {
                        "name": new_name,
                        "description": new_desc or None,
                        "created_by": new_author or None,
                        "keywords": keywords_payload,
                    },
                )
                st.success('Set created. Update the page (F5) to see it on the list.')

    if selected_set:
        st.markdown('#### Edit the selected set')
        edit_name = st.text_input(
            'Set Name',
            value=selected_set.get("name") or "",
            key="edit_kw_set_name",
        )
        edit_desc = st.text_area(
            'Description',
            value=selected_set.get("description") or "",
            key="edit_kw_set_desc",
        )
        edit_author = st.text_input(
            'Who created',
            value=selected_set.get("created_by") or "",
            key="edit_kw_set_author",
        )
        existing_keywords = selected_set.get("keywords") or []
        keywords_text = "\n".join(
            [str(item.get("text")) for item in existing_keywords if item.get("text")]
        )
        edit_keywords_raw = st.text_area(
            'Keywords or phrases, one per line',
            value=keywords_text,
            key="edit_kw_set_keywords",
        )

        col_update, col_delete = st.columns([1, 1])
        with col_update:
            if st.button('Save Changes'):
                if not edit_name:
                    st.error("The name of the kit can't be empty.")
                else:
                    keywords_payload = []
                    for line in edit_keywords_raw.splitlines():
                        text = line.strip()
                        if not text:
                            continue
                        keywords_payload.append({"text": text, "weight": 1.0})
                    api_post(
                        f"/keyword-sets/{selected_set_id}",
                        {
                            "name": edit_name,
                            "description": edit_desc or None,
                            "created_by": edit_author or None,
                            "keywords": keywords_payload,
                        },
                        method="PUT",
                    )
                    st.success('The changes are retained.')
                    st.rerun()
        with col_delete:
            if st.button('Remove This Set'):
                api_post(f"/keyword-sets/{selected_set_id}", {}, method="DELETE")
                st.success("The kit's been removed.")
                st.rerun()

    st.markdown("---")
    st.markdown("### How much we're looking for for one launch #")
    st.markdown(
        'These settings are active when the collection is automatically started (page "Automatization"»). '
        'The higher the value, the more results, but the longer the job.'
    )

    settings = api_get("/search/settings")
    perplexity_limit_sources = int(settings.get("perplexity_limit_sources", 1000))
    perplexity_limit_leads = int(settings.get("perplexity_limit_leads", 1000))
    perplexity_query_limit = int(settings.get("perplexity_query_limit", 10))

    new_query_limit = st.slider(
        'How many different topics to check in one cycle (keywords))',
        min_value=1,
        max_value=50,
        value=perplexity_query_limit,
        step=1,
        help='For each topic, the system makes a separate search request. More than that, coverage is greater.',
    )
    new_sources_limit = st.slider(
        'Maximum new source sites per cycle',
        min_value=50,
        max_value=2000,
        value=perplexity_limit_sources,
        step=50,
        help='How many new sites (Lent, portals) are added to the base for one launch.',
    )
    new_leads_limit = st.slider(
        'Maximum projects and tenders per cycle',
        min_value=50,
        max_value=2000,
        value=perplexity_limit_leads,
        step=50,
        help='How many projects and tenders to download from identified sources per launch.',
    )
    if st.button('Save Settings'):
        api_post(
            "/search/settings",
            {
                "perplexity_query_limit": int(new_query_limit),
                "perplexity_limit_sources": int(new_sources_limit),
                "perplexity_limit_leads": int(new_leads_limit),
            },
            method="PUT",
        )
        st.success('Substrates retained. They will be used for the next start of the collection.')

    st.markdown("---")


if __name__ == "__main__":
    main()
