import unittest
from offline_demo import run,compute_confidence,diff_fields,normalize_currency,normalize_date,parse_sitemap

class DataPipelineTests(unittest.TestCase):
    def test_identical_records(self):self.assertEqual(run()["differences"],{})
    def test_matching_is_bounded(self):
        self.assertEqual(compute_confidence("", ""),0);self.assertEqual(compute_confidence("same title","same title"),1)
    def test_currency_and_date(self):self.assertEqual(normalize_currency("руб."),"RUB");self.assertEqual(normalize_date("14.11.2026"),"2026-11-14")
    def test_field_provenance_diff(self):self.assertEqual(diff_fields({"amount":1},{"amount":2},["amount"]),{"amount":{"left":"1","right":"2"}})
    def test_sitemap(self):self.assertEqual(len(run()["source_urls"]),1)
