import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/"backend"))
from app.services.matching import compute_confidence,diff_fields
from app.services.normalize import normalize_currency,normalize_date
from app.services.sitemap import parse_sitemap

def run():
    first={"title":"Строительство школы","currency":normalize_currency("руб."),"date":normalize_date("14.11.2026")}
    second={"title":"Строительство школы","currency":"RUB","date":"2026-11-14"}
    urls=parse_sitemap('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.invalid/tender/1</loc></url></urlset>')
    return {"mode":"synthetic-normalization-and-matching","record":first,"differences":diff_fields(first,second,["title","currency","date"]),"matching_score":compute_confidence(first["title"],second["title"]),"source_urls":urls,"score_is_probability":False,"llm_extraction_executed":False}
if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
