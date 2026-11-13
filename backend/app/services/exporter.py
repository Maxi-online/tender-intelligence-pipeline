"""Экспорт данных в CSV, XLSX, Parquet.

Автор: Maxi-online
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import get_settings


def export_dataframe(df: pd.DataFrame, name: str, fmt: str) -> Path:
    """Экспортировать DataFrame в заданный формат.

    :param df: DataFrame для выгрузки.
    :param name: Базовое имя файла без расширения.
    :param fmt: Формат выгрузки (csv, xlsx, parquet).
    :return: Путь к созданному файлу.
    """

    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower()
    file_path = export_dir / f"{name}.{fmt}"

    if fmt == "csv":
        df.to_csv(file_path, index=False)
        return file_path
    if fmt == "xlsx":
        df.to_excel(file_path, index=False)
        return file_path
    if fmt == "parquet":
        df.to_parquet(file_path, index=False)
        return file_path

    raise ValueError(f"Неподдерживаемый формат: {fmt}")


def export_records(records: list[dict], name: str, fmt: str) -> Path:
    """Экспортировать список словарей в файл.

    :param records: Список словарей с данными.
    :param name: Базовое имя файла без расширения.
    :param fmt: Формат выгрузки (csv, xlsx, parquet).
    :return: Путь к созданному файлу.
    """

    df = pd.DataFrame(records)
    return export_dataframe(df, name=name, fmt=fmt)


def export_dossier_docx(title: str, sections: dict[str, list[str]], name: str) -> Path:
    """Сформировать досье в формате DOCX.

    :param title: Заголовок документа.
    :param sections: Секции и строки содержимого.
    :param name: Базовое имя файла без расширения.
    :return: Путь к созданному DOCX файлу.
    """

    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    file_path = export_dir / f"{name}.docx"

    doc = Document()
    doc.add_heading(title, level=1)
    for section_title, lines in sections.items():
        doc.add_heading(section_title, level=2)
        for line in lines:
            doc.add_paragraph(line)
    doc.save(file_path)
    return file_path


def export_dossier_pdf(title: str, sections: dict[str, list[str]], name: str) -> Path:
    """Сформировать досье в формате PDF.

    :param title: Заголовок документа.
    :param sections: Секции и строки содержимого.
    :param name: Базовое имя файла без расширения.
    :return: Путь к созданному PDF файлу.
    """

    settings = get_settings()
    export_dir = Path(settings.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    file_path = export_dir / f"{name}.pdf"

    pdf = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4
    y = height - 60
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, title)
    y -= 30
    pdf.setFont("Helvetica", 12)
    for section_title, lines in sections.items():
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(40, y, section_title)
        y -= 20
        pdf.setFont("Helvetica", 12)
        for line in lines:
            pdf.drawString(50, y, line)
            y -= 16
            if y < 60:
                pdf.showPage()
                y = height - 60
    pdf.save()
    return file_path


def export_projects_excel_template(records: list[dict], name: str) -> Path:
    """Экспортировать проекты в Excel по заданному шаблону.

    :param records: Список словарей с проектами.
    :param name: Базовое имя файла без расширения.
    :return: Путь к созданному XLSX файлу.
    """

    columns = [
        "№п/п",
        "Отрасль",
        "Заказчик",
        "Телефон заказчика",
        "Email заказчика",
        "Инвестор",
        "Телефон инвестора",
        "Email инвестора",
        "Подрядчик",
        "Телефон подрядчика",
        "Email подрядчика",
        "Наименование проекта",
        "Регион",
        "Сумма инвестиций общая, руб",
        "Объем геосинтетических материалов в смете, руб",
        "Срок реализации",
        "Текущая стадия проекта",
    ]
    rows = []
    for idx, item in enumerate(records, start=1):
        rows.append(
            {
                "№п/п": idx,
                "Отрасль": item.get("Отрасль", item.get("industry", "")),
                "Заказчик": item.get("Заказчик", item.get("customer", "")),
                "Телефон заказчика": item.get("Телефон заказчика", ""),
                "Email заказчика": item.get("Email заказчика", ""),
                "Инвестор": item.get("Инвестор", item.get("investor", "")),
                "Телефон инвестора": item.get("Телефон инвестора", ""),
                "Email инвестора": item.get("Email инвестора", ""),
                "Подрядчик": item.get("Подрядчик", item.get("contractor", "")),
                "Телефон подрядчика": item.get("Телефон подрядчика", ""),
                "Email подрядчика": item.get("Email подрядчика", ""),
                "Наименование проекта": item.get(
                    "Наименование проекта",
                    item.get("Объект", item.get("name", "")),
                ),
                "Регион": item.get("Регион", item.get("region", "")),
                "Сумма инвестиций общая, руб": item.get(
                    "Сумма инвестиций общая, руб",
                    item.get("budget", ""),
                ),
                "Объем геосинтетических материалов в смете, руб": item.get(
                    "Объем геосинтетических материалов в смете, руб",
                    item.get("geo_materials_budget", ""),
                ),
                "Срок реализации": item.get("Срок реализации", item.get("end_date", "")),
                "Текущая стадия проекта": item.get("Текущая стадия проекта", item.get("stage", "")),
            }
        )
    df = pd.DataFrame(rows, columns=columns)
    return export_dataframe(df, name=name, fmt="xlsx")
