Customer Report: Tender & Project Intelligence System (TPIS))
===============================================================
Author: Maxi-online
Date: 2026-02-04

1) Purpose and purpose
TPIS is an industrial system that automatically collects, analyses and
Structures data on construction projects and tenders. Results — One
Key parameters and contacts project table ready for export
and follow-up analysis in the BI.

2) Architecture and working logic (by step)
2.1 Automatic source detection
- New sources are being sought through SerpaPI for key construction topics.
- Sources are automatically added to the processing list.
- Car - RSS/Atom (from TML and standard tracks)).

2.2 Collection and Parsing of Materials
- XML, RSS/Atom, XML and PDF formats are supported.
- For HTML, the basic text is drawn.
- For RSS/Atom tapes, all records shall be processed.
- For PDF files, text (pdfplumber) or OCR is extracted via Claude Vision.

2.3 AI analysis and extraction (LLM))
- Normalization of text, selection of entities and parameters via Claude Sonnet.
- Roles and connections are derived from the context:
  - Employer, investor, contractor, winner, claimant, subcontractor
- The elements are presented in a single format:
  - dates in ISO 8601
  - Amounts in rubles, including thousands/millions/billions
  - Telephones and emails in normal form

2.4 Search and ranking
- The search is performed via Perplexity.
- Ran and classification performed via Claude Sonnet 4.5.
- Results are sorted according to relevance and freshness of publications.

2.5 Decodification and Quality
- Duplications of projects and companies are glued to the database level.
- Filters are only working on projects (noise: conferences/exhausts/magazines)).
- The quality flag helps track completeness.

2.6 Formation of a single table
- All data are combined into a single report `/api/reports/projects`.
- The table contains TK fields:
  - Project name
  - Region
  - Phase
  - Time frame for implementation
  - Total investments
  - Geosynthetic material volume
  - Roles and contacts

3) Technology latch
Backend:
- Python 3.12
- FastAPI
- SQLAlchemy Async
- PostgreSQL
- Celery + RabbitMQ

Parsing:
- httpx
- BeautifulSoup4
- lxml
- feedparser
- pdfplumber

LLM – Search and Analysis:
- Perplexity API (web‑search)
- Claude Sonnet 4.5
- regex

Exports:
- pandas
- openpyxl
- pyarrow
- reportlab
- python-docx

Frontend:
- Streamlit

4) Implemented strictly for TK (except Seldon API)
- HTML/RSS/Atom/XML/PDF. Collection
- Automatic auto-detection of new sources.
- LLM-extraction of entities, dates, amounts, contacts.
- Type classification (project/tender/output/analysis) via Claude.
- Search Perplexity + Claude ranking.
- Decodification and normalization.
- Common project table.
- Export CSV/XLSX/Parquet + file PDF/Word.
- Update four times a day.
- UI with filters, tabs, exports, and comparisons.

5) Which requires the keys and access of the customer
- SELDON_BASE_URL and SELDON_API_KEY – Seldon API connection.
- DISCOVERY_SEARCH_URL and DISCOVERY_API_KEY — Access to SerpaPI.
- HTTP_PROXY_URL – Proxie (if blockbacks are required to be bypassed)).

6) Outcome
The system is fully compliant with TK for parsing, AI's analysis,
Normalization, Exports and UI. The only restriction is Seldon API
is awaiting the issuance of the keys by the employer.
