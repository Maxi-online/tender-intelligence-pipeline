"""Юнит-тесты модуля Seldon: маппинг, извлечение участников/победителя."""

from __future__ import annotations
import os

import sys
from pathlib import Path

# Добавить backend в path при запуске из корня репозитория
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from app.services.seldon_service import (
    extract_participants_from_protocol,
    extract_winner_from_protocol,
    map_purchase_to_model,
    map_purchase_to_tpis_schema,
)


# Пример из документации Seldon (Приложение 2): один объект purchase
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
    "epName": "Сбер А. Коммерческие закупки",
    "epLink": "http://utp.sberbank-ast.ru/",
    "status": {
        "codeStatusEIS": None,
        "statusEIS": None,
        "codeStatusSeldon": 3,
        "statusSeldon": "Завершённая закупка",
    },
    "startDate": "2021-04-23T07:23:00",
    "endDate": "2021-05-10T23:59:00",
    "organizer": {"name": "УФПС Приморского края", "inn": "7707083893"},
    "lotsList": [],
    "contactInfo": {"person": "Иванов И.И.", "email": os.environ["EMAIL"], "phone": "+7 123 456-78-90"},
}


def test_map_purchase_to_tpis_schema() -> None:
    """Маппинг сырого purchase в схему ТЗ TPIS."""
    out = map_purchase_to_tpis_schema(SAMPLE_PURCHASE)
    assert out["tender_id"] == "1028827079"
    assert out["title"] == SAMPLE_PURCHASE["subject"]
    assert out["currency"] == "RUB"
    assert out["status"] == "Завершённая закупка"
    assert out["stage"] == "Запрос котировок"
    assert out["customer"] == "УФПС Приморского края"
    assert out["source_url"] == SAMPLE_PURCHASE["purchaseLink"]
    assert out["contact_info"] == SAMPLE_PURCHASE["contactInfo"]


def test_map_purchase_to_model() -> None:
    """Маппинг в поля модели SeldonPurchase."""
    out = map_purchase_to_model(SAMPLE_PURCHASE)
    assert out["seldon_id"] == 1028827079
    assert out["report_id"] == 3
    assert out["subject"] == SAMPLE_PURCHASE["subject"]
    assert out["status_name"] == "Завершённая закупка"
    assert out["customer_name"] == "УФПС Приморского края"
    assert out["customer_inn"] == "7707083893"
    assert "raw_purchase" in out


def test_map_purchase_to_model_requires_seldon_id() -> None:
    """Без seldonId маппер бросает ValueError."""
    try:
        map_purchase_to_model({"subject": "Test"})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_extract_participants_from_protocol_empty() -> None:
    """Пустой протокол — пустой список участников."""
    assert extract_participants_from_protocol(None) == []
    assert extract_participants_from_protocol({}) == []


def test_extract_participants_from_protocol() -> None:
    """Извлечение участников из структуры протокола (organizations + dataApps)."""
    protocol = {
        "lotsList": [
            {
                "apps": {
                    "organizations": [
                        {"id": 1, "name": "ООО Рога", "inn": "111", "ogrnSeldon": "222"},
                        {"id": 2, "name": "ООО Копыта", "inn": "333"},
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
    assert "ООО Рога" in names
    assert "ООО Копыта" in names


def test_extract_winner_from_protocol_empty() -> None:
    """Пустой протокол — нет победителя."""
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
