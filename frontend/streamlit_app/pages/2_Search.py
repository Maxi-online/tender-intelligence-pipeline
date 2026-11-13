"""Страница настроек поиска (файл с латинским именем для сайдбара).

Автор: Maxi-online
"""

from __future__ import annotations

import streamlit as st

from utils import api_get, api_post, apply_theme, render_sidebar_nav, localize_dataframe, to_dataframe


def main() -> None:
    """Отрисовать страницу настроек поиска."""
    st.set_page_config(page_title="TPIS | Настройки поиска", page_icon="🔎", layout="wide")
    apply_theme()
    render_sidebar_nav("Настройки поиска")
    st.title("Настройки поиска")
    st.caption("Настройте, по каким темам искать тендеры и проекты, и сколько результатов получать за один запуск.")

    st.markdown("---")
    st.markdown("### Что ищем: темы и ключевые слова")
    st.markdown(
        "Система ищет по **ключевым словам** (например: строительство, реконструкция, капремонт). "
        "Вы можете выбрать готовый набор или создать свой."
    )

    keyword_sets = api_get("/keyword-sets")
    if not isinstance(keyword_sets, list):
        keyword_sets = []

    if not keyword_sets:
        st.info("Пока нет ни одного набора ключевых слов. Создайте новый ниже.")
        selected_set_id = None
        selected_set = None
    else:
        options = {f"{item.get('name')} (#{item.get('id')})": item for item in keyword_sets}
        label = st.selectbox(
            "Выберите набор ключевых слов",
            list(options.keys()),
            key="kw_select",
        )
        selected_set = options.get(label)
        selected_set_id = selected_set.get("id") if selected_set else None

    with st.expander("➕ Создать новый набор ключевых слов", expanded=False):
        st.markdown("Задайте название и перечислите слова или короткие фразы (по одному на строку).")
        new_name = st.text_input("Название набора", placeholder="Например: Строительные тендеры", key="new_kw_set_name")
        new_desc = st.text_area(
            "Описание (необязательно)",
            placeholder="Кратко, для чего этот набор.",
            key="new_kw_set_desc",
        )
        new_keywords_raw = st.text_area(
            "Ключевые слова или фразы — по одному на строку",
            placeholder="строительство\nреконструкция\nкапитальный ремонт\nкапремонт",
            key="new_kw_set_keywords",
        )
        new_author = st.text_input("Кто создал (необязательно)", key="new_kw_set_author")
        if st.button("Создать набор"):
            if not new_name:
                st.error("Укажите название набора.")
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
                st.success("Набор создан. Обновите страницу (F5), чтобы увидеть его в списке.")

    if selected_set:
        st.markdown("#### Редактировать выбранный набор")
        edit_name = st.text_input(
            "Название набора",
            value=selected_set.get("name") or "",
            key="edit_kw_set_name",
        )
        edit_desc = st.text_area(
            "Описание",
            value=selected_set.get("description") or "",
            key="edit_kw_set_desc",
        )
        edit_author = st.text_input(
            "Кто создал",
            value=selected_set.get("created_by") or "",
            key="edit_kw_set_author",
        )
        existing_keywords = selected_set.get("keywords") or []
        keywords_text = "\n".join(
            [str(item.get("text")) for item in existing_keywords if item.get("text")]
        )
        edit_keywords_raw = st.text_area(
            "Ключевые слова или фразы — по одному на строку",
            value=keywords_text,
            key="edit_kw_set_keywords",
        )

        col_update, col_delete = st.columns([1, 1])
        with col_update:
            if st.button("Сохранить изменения"):
                if not edit_name:
                    st.error("Название набора не может быть пустым.")
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
                    st.success("Изменения сохранены.")
                    st.rerun()
        with col_delete:
            if st.button("Удалить этот набор"):
                api_post(f"/keyword-sets/{selected_set_id}", {}, method="DELETE")
                st.success("Набор удалён.")
                st.rerun()

    st.markdown("---")
    st.markdown("### Сколько ищем за один запуск")
    st.markdown(
        "Эти настройки действуют при автоматическом запуске сбора (страница «Автоматизация»). "
        "Чем выше значения — тем больше результатов, но дольше работа."
    )

    settings = api_get("/search/settings")
    perplexity_limit_sources = int(settings.get("perplexity_limit_sources", 1000))
    perplexity_limit_leads = int(settings.get("perplexity_limit_leads", 1000))
    perplexity_query_limit = int(settings.get("perplexity_query_limit", 10))

    new_query_limit = st.slider(
        "Сколько разных тем проверять за один цикл (по ключевым словам)",
        min_value=1,
        max_value=50,
        value=perplexity_query_limit,
        step=1,
        help="По каждой теме система делает отдельный поисковый запрос. Больше тем — шире охват.",
    )
    new_sources_limit = st.slider(
        "Максимум новых сайтов-источников за один цикл",
        min_value=50,
        max_value=2000,
        value=perplexity_limit_sources,
        step=50,
        help="Сколько новых сайтов (лент, порталов) добавлять в базу за один запуск.",
    )
    new_leads_limit = st.slider(
        "Максимум проектов и тендеров за один цикл",
        min_value=50,
        max_value=2000,
        value=perplexity_limit_leads,
        step=50,
        help="Сколько проектов и тендеров загружать из найденных источников за один запуск.",
    )
    if st.button("Сохранить настройки"):
        api_post(
            "/search/settings",
            {
                "perplexity_query_limit": int(new_query_limit),
                "perplexity_limit_sources": int(new_sources_limit),
                "perplexity_limit_leads": int(new_leads_limit),
            },
            method="PUT",
        )
        st.success("Настройки сохранены. Они будут использоваться при следующем запуске сбора.")

    st.markdown("---")


if __name__ == "__main__":
    main()
