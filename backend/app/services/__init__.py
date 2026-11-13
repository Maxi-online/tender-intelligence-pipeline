"""Service exports, loaded on demand to keep pure utilities independent of infrastructure.

Author: Maxi-online
"""
from importlib import import_module

_EXPORTS = {'load_keywords_config': ('app.services.config_loader', 'load_keywords_config'), 'load_sources_config': ('app.services.config_loader', 'load_sources_config'), 'DiscoveryService': ('app.services.discovery', 'DiscoveryService'), 'export_dossier_docx': ('app.services.exporter', 'export_dossier_docx'), 'export_dossier_pdf': ('app.services.exporter', 'export_dossier_pdf'), 'export_projects_excel_template': ('app.services.exporter', 'export_projects_excel_template'), 'export_records': ('app.services.exporter', 'export_records'), 'ingest_html_page': ('app.services.ingest', 'ingest_html_page'), 'ingest_rss': ('app.services.ingest', 'ingest_rss'), 'ingest_sitemap': ('app.services.ingest', 'ingest_sitemap'), 'compute_confidence': ('app.services.matching', 'compute_confidence'), 'diff_fields': ('app.services.matching', 'diff_fields'), 'normalize_currency': ('app.services.normalize', 'normalize_currency'), 'normalize_date': ('app.services.normalize', 'normalize_date'), 'normalize_phone': ('app.services.normalize', 'normalize_phone'), 'classify_text': ('app.services.llm_processing', 'classify_text'), 'extract_entities': ('app.services.llm_processing', 'extract_entities'), 'ingest_sources': ('app.services.pipeline', 'ingest_sources'), 'match_tenders_and_articles': ('app.services.pipeline', 'match_tenders_and_articles'), 'dedupe_companies': ('app.services.dedupe_companies', 'dedupe_companies'), 'normalize_name': ('app.services.dedupe_companies', 'normalize_name'), 'SeldonClient': ('app.services.seldon_client', 'SeldonClient'), 'fetch_tenders': ('app.services.seldon_service', 'fetch_tenders'), 'ingest_tenders': ('app.services.seldon_service', 'ingest_tenders')}
__all__ = list(_EXPORTS)

def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module), attribute)
    globals()[name] = value
    return value
