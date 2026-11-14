"""Export data to CSV, XLSX, Parquet.

Author: Maxi-online
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import get_settings


def export_dataframe(df: pd.DataFrame, name: str, fmt: str) -> Path:
    """Export DataFrame to a specified format.

    :param df: DataFrame for unloading.
    :paramname: File reference name without extension.
    :param fmt: Unload format (csv, xlsx, parquet).
    :return: Path to the created file.
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

    raise ValueError(f"Non-supported format: {fmt}")


def export_records(records: list[dict], name: str, fmt: str) -> Path:
    """Export the list of dictionaries to the file.

    :param records: List of data dictionaries.
    :paramname: File reference name without extension.
    :param fmt: Unload format (csv, xlsx, parquet).
    :return: Path to the created file.
    """

    df = pd.DataFrame(records)
    return export_dataframe(df, name=name, fmt=fmt)


def export_dossier_docx(title: str, sections: dict[str, list[str]], name: str) -> Path:
    """Form a dossier in DOCX format.

    :param number: Document title.
    :param sections: Sections and lines of contents.
    :paramname: File reference name without extension.
    :return: Path to the created DOCX file.
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
    """Form a file in PDF format.

    :param number: Document title.
    :param sections: Sections and lines of contents.
    :paramname: File reference name without extension.
    :return: Path to the PDF file created.
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
    """Export projects to Excel according to a given template.

    :param records: List of dictionaries with projects.
    :paramname: File reference name without extension.
    :return: Path to the created XLSX file.
    """

    columns = [
        'No.',
        'Industry',
        'Customer',
        'Customer phone',
        'Customer email',
        'Investor',
        'Investor phone',
        'Investor email',
        'Contractor',
        'Contractor phone',
        'Contractor email',
        'Project name',
        'Region',
        'Total investment, RUB',
        'Estimated geosynthetic materials, RUB',
        'Implementation period',
        'Current project stage',
    ]
    rows = []
    for idx, item in enumerate(records, start=1):
        rows.append(
            {
                'No.': idx,
                'Industry': item.get('Industry', item.get("industry", "")),
                'Customer': item.get('Customer', item.get("customer", "")),
                'Customer phone': item.get('Customer phone', ""),
                'Customer email': item.get('Customer email', ""),
                'Investor': item.get('Investor', item.get("investor", "")),
                'Investor phone': item.get('Investor phone', ""),
                'Investor email': item.get('Investor email', ""),
                'Contractor': item.get('Contractor', item.get("contractor", "")),
                'Contractor phone': item.get('Contractor phone', ""),
                'Contractor email': item.get('Contractor email', ""),
                'Project name': item.get(
                    'Project name',
                    item.get('Facility', item.get("name", "")),
                ),
                'Region': item.get('Region', item.get("region", "")),
                'Total investment, RUB': item.get(
                    'Total investment, RUB',
                    item.get("budget", ""),
                ),
                'Estimated geosynthetic materials, RUB': item.get(
                    'Estimated geosynthetic materials, RUB',
                    item.get("geo_materials_budget", ""),
                ),
                'Implementation period': item.get('Implementation period', item.get("end_date", "")),
                'Current project stage': item.get('Current project stage', item.get("stage", "")),
            }
        )
    df = pd.DataFrame(rows, columns=columns)
    return export_dataframe(df, name=name, fmt="xlsx")
