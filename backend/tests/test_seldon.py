'Seldon Unit Tests: Mapping, Participant/Winner Extract.'

from __future__ import annotations
import os

import sys
from pathlib import Path

# Add backend to path when starting from the root of the repository
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from app.services.seldon_service import (
    extract_participants_from_protocol,
    extract_winner_from_protocol,
    map_purchase_to_model,
    map_purchase_to_tpis_schema,
)


# Example from Seldon documentation (Annex 2): One object purchase
SAMPLE_PURCHASE = {
    "SeldonId": 1028827079,
    "reportId": 3,
    "filterId": None,
    "filterName": None,
    "notificationNumber": "SBR035-210014478000083",
    "contractType": {"code": 4, "name": "Запрос котировок"},
    "sourceContractType": None,
    "purchaseLink": "http://utp.sberbank-ast.ru/RussianPost/NBT/PurchaseView/5/0/0/741087",
    "publishDate": "2021-04-23T07:23:00",
    "firstPublishDate": "2021-04-23T07:23:00",
    "subject": "Запрос коммерческих предложений для закупки по предмету: Оказание услуг по перевозке наличных денежных средств",
    "purchasePrice": None,
    "currency": {"code": "RUB", "name": "Российский рубль"},
    "epName": 'Demonstration Procurement Platform',
    "epLink": "http://utp.sberbank-ast.ru/",
    "status": {
        "codeStatusEIS": None,
        "statusEIS": None,
        "codeStatusSeldon": 3,
        "statusSeldon": "Завершённая закупка",
    },
    "startDate": "2021-04-23T07:23:00",
    "endDate": "2021-05-10T23:59:00",
    "organizer": {"name": 'Demonstration Postal Operator', "inn": "7707083893"},
    "lotsList": [],
    "contactInfo": {"person": 'Demo Contact', "email": os.environ["EMAIL"], "phone": "+7 123 456-78-90"},
}


def test_map_purchase_to_tpis_schema() -> None:
    'Mapping raw purchase into the TK TPIS scheme.'
    out = map_purchase_to_tpis_schema(SAMPLE_PURCHASE)
    assert out["tender_id"] == "1028827079"
    assert out["title"] == SAMPLE_PURCHASE["subject"]
    assert out["currency"] == "RUB"
    assert out["status"] == "Завершённая закупка"
    assert out["stage"] == "Запрос котировок"
    assert out["customer"] == 'Demonstration Postal Operator'
    assert out["source_url"] == SAMPLE_PURCHASE["purchaseLink"]
    assert out["contact_info"] == SAMPLE_PURCHASE["contactInfo"]


def test_map_purchase_to_model() -> None:
    '===SeldonPurchase===Maping in the SeldonPurchase fields.'
    out = map_purchase_to_model(SAMPLE_PURCHASE)
    assert out["seldon_id"] == 1028827079
    assert out["report_id"] == 3
    assert out["subject"] == SAMPLE_PURCHASE["subject"]
    assert out["status_name"] == "Завершённая закупка"
    assert out["customer_name"] == 'Demonstration Postal Operator'
    assert out["customer_inn"] == "7707083893"
    assert "raw_purchase" in out


def test_map_purchase_to_model_requires_seldon_id() -> None:
    'Without seldonId, the mapper leaves ValueError.'
    try:
        map_purchase_to_model({"subject": "Test"})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_extract_participants_from_protocol_empty() -> None:
    'An empty protocol is an empty list of participants.'
    assert extract_participants_from_protocol(None) == []
    assert extract_participants_from_protocol({}) == []


def test_extract_participants_from_protocol() -> None:
    'Extraction of participants from the structure of the protocol (organizations + dataApps).'
    protocol = {
        "lotsList": [
            {
                "apps": {
                    "organizations": [
                        {"id": 1, "name": 'Demo Supplier A', "inn": "111", "ogrnSeldon": "222"},
                        {"id": 2, "name": 'Demo Supplier B', "inn": "333"},
                    ],
                    "dataApps": [
                        {"organizationId": 1, "admitted": True, "resultType": "Допущен"},
                        {"organizationId": 2, "admitted": False, "resultType": "Отклонён"},
                    ],
                },
            },
        ],
    }
    participants = extract_participants_from_protocol(protocol)
    assert len(participants) == 2
    names = {p.get("name") for p in participants}
    assert 'Demo Supplier A' in names
    assert 'Demo Supplier B' in names


def test_extract_winner_from_protocol_empty() -> None:
    'An empty protocol is no winner.'
    assert extract_winner_from_protocol(None) is None
    assert extract_winner_from_protocol({}) is None


if __name__ == "__main__":
    test_map_purchase_to_tpis_schema()
    test_map_purchase_to_model()
    test_map_purchase_to_model_requires_seldon_id()
    test_extract_participants_from_protocol_empty()
    test_extract_participants_from_protocol()
    test_extract_winner_from_protocol_empty()
    print("All tests passed.")
