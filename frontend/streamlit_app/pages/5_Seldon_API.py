"""Вкладка модуля Seldon API: актуальная информация о заказчиках и победителях (не участие в тендерах)."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from utils import api_get, api_post, apply_theme, render_sidebar_nav, to_dataframe


def main() -> None:
    """Отрисовать страницу Seldon API."""
    st.set_page_config(page_title="TPIS | Seldon API", page_icon="📋", layout="wide")
    apply_theme()
    render_sidebar_nav("Seldon API")
    st.title("Модуль Seldon API")
    st.caption(
        "Цель: максимально свежая информация об участниках — заказчиках и победителях. "
        "Тендеры как источник данных о контрагентах (ИНН, контакты). Сначала загрузите данные в кэш."
    )

    mode = st.radio(
        "Режим",
        [
            "Загрузить данные из Seldon",
            "Победитель по тендеру",
            "Заказчики и контакты по ИНН",
            "Участники по тендеру",
            "Список тендеров",
            "Детали по ID",
        ],
        horizontal=True,
    )

    try:
        if mode == "Загрузить данные из Seldon":
            st.subheader("Загрузить данные из Seldon")
            st.caption("GPT сам подберёт фильтр и период под цель. Один клик — рекомендация и выгрузка.")
            search_goal = st.text_input(
                "Цель поиска (можно не менять)",
                value="Заказчики и победители по строительству и капремонту, госзакупки 44-ФЗ",
                label_visibility="collapsed",
            )
            if st.button("Запустить синхронизацию"):
                with st.spinner("GPT подбирает настройки, затем выгрузка..."):
                    resp = api_post("/seldon/sync", payload={"search_goal": search_goal or "Заказчики и победители по строительству, госзакупки 44-ФЗ"})
                st.success(f"Готово: создано {resp.get('created', 0)}, обновлено {resp.get('updated', 0)}, всего {resp.get('total', 0)}")
                st.json(resp)

        elif mode == "Список тендеров":
            st.subheader("Список тендеров из кэша")
            limit = st.number_input("limit", min_value=1, max_value=100, value=20)
            offset = st.number_input("offset", min_value=0, value=0)
            if st.button("Запросить наш API"):
                data = api_get(f"/seldon/tenders?limit={limit}&offset={offset}")
                if isinstance(data, list) and data:
                    df = to_dataframe(data)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("В кэше нет записей. Сначала выполните «Загрузить данные из Seldon».")

        elif mode == "Детали по ID":
            st.subheader("Детали тендера по seldon_id")
            tender_id = st.text_input("tender_id (seldon_id)", value="")
            if st.button("Запросить наш API") and tender_id:
                data = api_get(f"/seldon/tenders/{tender_id}")
                if isinstance(data, dict):
                    st.json(data)
                else:
                    st.warning("Тендер не найден.")

        elif mode == "Участники по тендеру":
            st.subheader("Участники закупки (заявки, допуск) по ID")
            tender_id = st.text_input("tender_id", value="")
            if st.button("Запросить наш API") and tender_id:
                data = api_get(f"/seldon/tenders/{tender_id}/participants")
                if isinstance(data, list) and data:
                    df = to_dataframe(data)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("Участники не найдены или тендер отсутствует в кэше.")

        elif mode == "Победитель по тендеру":
            st.subheader("Победитель (актуальные данные об исполнителе) по ID закупки")
            tender_id = st.text_input("tender_id", value="")
            if st.button("Запросить наш API") and tender_id:
                data = api_get(f"/seldon/tenders/{tender_id}/winner")
                if isinstance(data, dict):
                    st.json(data)
                else:
                    st.warning("Тендер не найден.")

        elif mode == "Заказчики и контакты по ИНН":
            st.subheader("Заказчики и контакты по ИНН (актуальные данные)")
            inn = st.text_input("ИНН (или company_id)", value="")
            if st.button("Запросить наш API") and inn:
                data = api_get(f"/seldon/contacts?inn={inn}")
                if isinstance(data, list) and data:
                    df = to_dataframe(data)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("Контакты по этому ИНН не найдены в кэше.")
    except Exception as e:
        st.error(f"Ошибка: {e}")

    st.markdown("---")
    st.subheader("Справочник: фильтры Seldon")
    if st.button("Получить список фильтров"):
        try:
            filters = api_get("/seldon/filters")
            if isinstance(filters, list) and filters:
                df = to_dataframe(filters)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Не удалось получить фильтры (проверьте настройки Seldon).")
        except Exception as ex:
            st.error(str(ex))


if __name__ == "__main__":
    main()
