"""Страница источников и PDF (файл с латинским именем для сайдбара).

Автор: Maxi-online
"""

from __future__ import annotations

import streamlit as st

from utils import API_BASE, api_get, api_post, apply_theme, render_sidebar_nav, localize_dataframe, normalize_sources, to_dataframe


def main() -> None:
    """Отрисовать страницу источников и PDF."""
    st.set_page_config(page_title="TPIS | Источники и PDF", page_icon="🛰️", layout="wide")
    apply_theme()
    render_sidebar_nav("Источники и PDF")
    st.title("Источники данных")
    st.caption("Сайты, ленты новостей, статьи и загрузка PDF для извлечения проектов и тендеров.")

    with st.expander("➕ Добавить сайт или ленту вручную", expanded=False):
        name = st.text_input("Название (как будет отображаться)")
        url = st.text_input("Ссылка (URL)")
        kind = st.selectbox(
            "Тип источника",
            ["html", "rss", "sitemap", "api"],
            index=0,
            format_func=lambda v: {"html": "Обычная страница (HTML)", "rss": "Лента новостей (RSS)", "sitemap": "Карта сайта", "api": "API"}[v],
        )
        if st.button("Добавить источник"):
            if not url:
                st.error("Укажите URL источника.")
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
                st.success("Источник создан.")

    with st.expander("🔍 Найти сайты по слову", expanded=False):
        query = st.text_input("Введите слово или фразу (например: строительство)")
        if st.button("Искать"):
            if not query:
                st.error("Введите слово для поиска.")
            else:
                results = api_get("/sources/discover", params={"query": query})
                df_results = localize_dataframe(to_dataframe(results))
                st.dataframe(df_results, use_container_width=True, hide_index=True)
        st.caption(
            "Массовый автопоиск источников запускается на странице «Автоматизация» кнопкой «Запустить сбор»."
        )

    st.markdown("### Список источников")
    with st.spinner("Загрузка..."):
        sources = normalize_sources(api_get("/sources"))
    df = localize_dataframe(to_dataframe(sources))
    if df.empty:
        st.info("Пока нет добавленных источников.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### Новости и статьи из источников")
    with st.spinner("Загрузка статей..."):
        articles = api_get("/articles", params={"limit": 200})
    df_articles = to_dataframe(articles)
    if df_articles.empty:
        st.info("Статей пока нет.")
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
                "Ссылка": st.column_config.LinkColumn("Ссылка"),
            },
            hide_index=True,
        )

    st.markdown("### Загрузить PDF и извлечь проекты")
    st.markdown(
        "Загрузите PDF — система распознает текст и добавит найденные проекты и тендеры в общую таблицу."
    )
    uploaded_file = st.file_uploader("Выберите файл PDF", type=["pdf"])

    col1, col2 = st.columns(2)
    with col1:
        entity_type = st.selectbox(
            "Куда привязать результат",
            ["article", "project", "tender", "company"],
            format_func=lambda v: {
                "article": "Только сохранить как статью/источник",
                "project": "Привязать к проекту",
                "tender": "Привязать к тендеру",
                "company": "Привязать к компании",
            }[v],
        )
    with col2:
        entity_id = st.text_input("Номер проекта/тендера/компании (если привязываете)", placeholder="Оставьте пустым, если не нужно")

    if st.button("Загрузить и извлечь данные из PDF"):
        if not uploaded_file:
            st.error("Сначала выберите PDF файл.")
        else:
            import requests

            params = {
                "entity_type": entity_type,
                "entity_id": entity_id or "",
            }
            headers = {"Content-Type": "application/pdf"}
            with st.spinner("Отправка файла и распознавание..."):
                resp = requests.post(
                    f"{API_BASE}/documents/upload_pdf",
                    params=params,
                    data=uploaded_file.getvalue(),
                    headers=headers,
                    timeout=120,
                )
            if not resp.ok:
                st.error(f"Ошибка при загрузке: {resp.status_code} {resp.text}")
                return
            payload = resp.json()

            st.subheader("Результат")
            st.write(f"Режим: {payload.get('mode')}")
            article_id = payload.get("article_id")
            if article_id:
                st.write(f"Статья сохранена в базе (ID = {article_id})")

            projects = payload.get("projects_created") or []
            if not projects:
                st.info("В этом PDF проекты не найдены или уже были в базе.")
            else:
                st.markdown("#### Добавленные в базу проекты")
                for p in projects:
                    st.write(f"- [#{p.get('id')}] {p.get('name')}")


if __name__ == "__main__":
    main()
