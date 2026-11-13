"""Страница управления автоматизацией (файл с латинским именем для сайдбара).

Автор: Maxi-online
"""

from __future__ import annotations

import json

import streamlit as st

from utils import api_get, api_post, apply_theme, render_sidebar_nav, to_dataframe


def main() -> None:
    """Отрисовать страницу автоматизации."""
    st.set_page_config(page_title="TPIS | Автоматизация", page_icon="⚙️", layout="wide")
    apply_theme()
    render_sidebar_nav("Автоматизация")
    st.title("Автозапуск сбора данных")
    st.caption("Запуск поиска тендеров и проектов по настройкам, просмотр последнего результата.")

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
            "Новых сайтов добавлено: "
            f"{_num(last_result.get('sources_discovered'))} "
            f"(найдено {_num(last_result.get('sources_found'))})"
        )
        leads_raw = last_result.get("perplexity_leads")
        leads = leads_raw if isinstance(leads_raw, dict) else {}
        summary_parts.append(
            "Проектов и тендеров: "
            f"проекты {_num(leads.get('projects'))}, "
            f"тендеры {_num(leads.get('tenders'))}, "
            f"всего {_num(leads.get('total_results'))}"
        )
        summary_parts.append(f"Обработано источников: {_num(last_result.get('sources'))}")
        summary_parts.append(f"Проектов дозаполнено контактами: {_num(last_result.get('projects_enriched'))}")
        summary_parts.append(f"Дубликатов проектов объединено: {_num(last_result.get('projects_deduped'))}")
        summary_parts.append(f"Дубликатов компаний объединено: {_num(last_result.get('companies_deduped'))}")
        summary_parts.append(f"Совпадений тендеров со статьями: {_num(last_result.get('matches'))}")
        last_result_summary = " | ".join(summary_parts) if summary_parts else "нет данных"
    else:
        last_result_summary = last_result if last_result is not None else "цикл ещё не запускался"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Автозапуск по расписанию", "Включён" if enabled else "Выключен")
    with col2:
        st.metric("Когда последний раз запускали", last_run or "ещё не запускали")
    with col3:
        st.metric("Итог последнего запуска", last_result_summary)

    st.markdown("**Детали последнего результата**")
    leads_raw = last_result.get("perplexity_leads") if isinstance(last_result, dict) else {}
    leads = leads_raw if isinstance(leads_raw, dict) else {}
    if isinstance(last_result, dict):
        details_rows = [
            {"Параметр": "Новых сайтов добавлено в базу", "Значение": str(_num(last_result.get("sources_discovered")))},
            {"Параметр": "Сайтов найдено всего (поиск)", "Значение": str(_num(last_result.get("sources_found")))},
            {"Параметр": "Проектов из поиска", "Значение": str(_num(leads.get("projects")))},
            {"Параметр": "Тендеров из поиска", "Значение": str(_num(leads.get("tenders")))},
            {"Параметр": "Результатов поиска всего", "Значение": str(_num(leads.get("total_results")))},
            {"Параметр": "Источников обработано (ленты, страницы)", "Значение": str(_num(last_result.get("sources")))},
            {"Параметр": "Проектов дозаполнено (контакты, заказчик)", "Значение": str(_num(last_result.get("projects_enriched")))},
            {"Параметр": "Дубликатов проектов объединено", "Значение": str(_num(last_result.get("projects_deduped")))},
            {"Параметр": "Дубликатов компаний объединено", "Значение": str(_num(last_result.get("companies_deduped")))},
            {"Параметр": "Совпадений тендеров со статьями", "Значение": str(_num(last_result.get("matches")))},
        ]
        details_df = to_dataframe(details_rows).astype(str)
        st.dataframe(details_df, use_container_width=True, hide_index=True)
    else:
        st.info(
            "Сбор ещё не запускался. Нажмите «Запустить сбор сейчас» или «Тестовый запуск», "
            "чтобы заполнить таблицу результатами."
        )
        details_rows = [
            {"Параметр": "Новых сайтов добавлено в базу", "Значение": "0"},
            {"Параметр": "Сайтов найдено всего (поиск)", "Значение": "0"},
            {"Параметр": "Проектов из поиска", "Значение": "0"},
            {"Параметр": "Тендеров из поиска", "Значение": "0"},
            {"Параметр": "Результатов поиска всего", "Значение": "0"},
            {"Параметр": "Источников обработано (ленты, страницы)", "Значение": "0"},
            {"Параметр": "Проектов дозаполнено (контакты, заказчик)", "Значение": "0"},
            {"Параметр": "Дубликатов проектов объединено", "Значение": "0"},
            {"Параметр": "Дубликатов компаний объединено", "Значение": "0"},
            {"Параметр": "Совпадений тендеров со статьями", "Значение": "0"},
        ]
        details_df = to_dataframe(details_rows).astype(str)
        st.dataframe(details_df, use_container_width=True, hide_index=True)

    st.markdown("### Запуск сбора")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Запустить сбор сейчас"):
            api_post("/automation/start")
            st.success("Сбор поставлен в очередь. Результаты появятся через несколько минут.")
    with c2:
        if st.button("Выключить автозапуск по расписанию"):
            api_post("/automation/stop")
            st.success("Автозапуск отключён.")
    with c3:
        if st.button("Тестовый запуск (мало запросов)"):
            api_post("/automation/start_test")
            st.success("Тестовый сбор поставлен в очередь.")

    st.markdown("### Опасные действия")
    if st.button("Удалить все проекты из базы"):
        result = api_post("/projects/clear")
        deleted = result.get("deleted") if isinstance(result, dict) else None
        st.success(f"Проекты удалены: {deleted if deleted is not None else 'готово'}.")


if __name__ == "__main__":
    main()
