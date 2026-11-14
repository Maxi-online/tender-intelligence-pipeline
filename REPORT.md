# Tender Intelligence Pipeline: implementation reference

Author: Maxi-online. Based on the implementation notes dated 2026-02-04.
This document describes the pipeline's code paths and original integration scope.
The [main README](README.md) records the public demonstration, verification and
current limitations. The feature inventory below is not a production acceptance
certificate or a claim that external provider accounts were exercised offline.

## Purpose and outputs

The pipeline collects construction-project and tender material, extracts
structured entities, normalizes records and prepares exports for analysis.
Its consolidated project table carries source references, project attributes,
organizations and contact fields. This preserves a path from a record back to
the material from which it was extracted.

## Processing stages

### 1. Source discovery

Discovery integrations search for sources using configured topics. RSS/Atom
feeds can be detected through HTML links and common feed locations. Discovered
sources can enter the ingestion workflow. Public configuration starts with
`sources: []`, an empty region list and generic vocabulary. Operators must
explicitly configure approved sources and provider access for connected use.

### 2. Fetching and parsing

Adapters handle HTML, RSS/Atom, XML and PDF. HTML processing extracts the main
text; feed processing iterates entries. PDF processing can extract text through
pdfplumber, with an optional vision/OCR provider path for supported inputs.
Availability of an adapter does not establish extraction quality for every site
or scanned document.

### 3. Entity extraction and normalization

The LLM-assisted path extracts organizations, project attributes and contextual
roles such as customer, investor, contractor, winner, applicant and subcontractor.
Normalization handles ISO 8601 dates, currency amounts and magnitude terms,
telephone numbers and email addresses. Russian vocabulary and regular
expressions are input-language data rather than untranslated instructions.

### 4. Search, classification and ranking

The source contains provider integrations for web search and LLM analysis,
including Perplexity and Claude paths. Provider selection, model availability
and account access belong to private runtime configuration. Classification
separates projects, tenders, results and analysis; ranking uses relevance and
publication freshness. An LLM score is not a calibrated probability.

### 5. Deduplication and quality indicators

Project/company deduplication and normalization reduce repeated records.
Domain filters suppress irrelevant events and publication noise. Completeness
and quality flags help expose missing fields; they do not verify every claim
against a primary source automatically.

### 6. Consolidation and export

`/api/reports/projects` assembles the consolidated view. Its fields include:

- Project name and description, region, stage and implementation dates.
- Total investment and the domain-specific material estimate when available.
- Organization roles and their contact fields.
- Source material and available provenance/quality indicators.

Export paths cover CSV, XLSX and Parquet, plus PDF/Word dossier generation.
The Streamlit interface provides filters, tabs, comparisons and export controls.
Scheduling is supported by the worker stack; a historical four-runs-per-day
schedule is not an enabled public customer ingestion job.

## Technology inventory

| Layer | Components |
| --- | --- |
| API and persistence | Python, FastAPI, async SQLAlchemy, PostgreSQL |
| Background processing | Celery and RabbitMQ |
| Parsing | httpx, BeautifulSoup4, lxml, feedparser, pdfplumber |
| Search and analysis | Provider adapters, regular expressions, normalization and ranking services |
| Export | pandas, openpyxl, pyarrow, reportlab, python-docx |
| Interface | Streamlit |

Use the checked-in dependency manifests for version requirements. Historical
model names in implementation notes do not guarantee current provider support.

## Integration configuration

Seldon integration uses `SELDON_BASE_URL` and `SELDON_API_KEY`. Discovery uses
`DISCOVERY_SEARCH_URL` and `DISCOVERY_API_KEY`. Configure `HTTP_PROXY_URL` only
when the deployment explicitly needs a proxy. Other provider adapters declare
their own settings in the examples. No working provider credential or customer
source list is supplied in the repository.

## Verification and remaining work

The offline demonstration and tests exercise normalization, matching bounds,
field-level differences, sitemap parsing and neutral public configuration.
Live crawling, Seldon access, LLM extraction quality, OCR performance and the
complete deployed UI require their own integration/evaluation runs. A provider
key alone is not evidence that those checks passed. Evaluate extraction F1 and
deduplication precision/recall on independent labels before making quality claims.
