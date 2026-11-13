"""Check shipped data defaults without initializing providers or infrastructure."""
from pathlib import Path
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[2]
class PublicConfigurationTests(unittest.TestCase):
    def test_source_ingestion_is_not_preconfigured_for_a_customer(self):
        data=yaml.safe_load((ROOT/'config/sources.yaml').read_text(encoding='utf-8'))
        self.assertEqual(data,{'sources':[]})

    def test_search_vocabulary_has_no_region_or_customer_campaign(self):
        data=yaml.safe_load((ROOT/'config/keywords.yaml').read_text(encoding='utf-8'))
        self.assertEqual(data['regions'],[])
        self.assertEqual(set(data),{'construction_keywords','regions'})
        self.assertTrue(data['construction_keywords'])
        self.assertTrue(all(word.isascii() for word in data['construction_keywords']))
