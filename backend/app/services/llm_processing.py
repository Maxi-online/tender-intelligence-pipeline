"""LLM модуль: извлечение сущностей и классификация (OpenAI)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from dataclasses import dataclass

from app.services.openai_client import OpenAIClient

logger = logging.getLogger(__name__)


def _strip_json_markdown(raw: str) -> str:
    """Убрать обёртку ```json ... ``` из ответа LLM."""
    s = (raw or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


@dataclass
class ExtractedEntities:
    """Результат извлечения сущностей."""

    projects: list[str]
    companies: list[str]
    persons: list[str]
    emails: list[str]
    phones: list[str]
    money: list[str]
    dates: list[str]
    winners: list[str]
    applicants: list[str]
    contractors: list[str]
    subcontractors: list[str]
    customers: list[str]
    investors: list[str]


def _merge_content(response: dict) -> str:
    content = response.get("content") or []
    text_blocks = [b.get("text") for b in content if b.get("type") == "text"]
    return "\n".join(t for t in text_blocks if t)


async def _call_json_with_retry(
    client: OpenAIClient,
    system: str,
    user_content: str,
    *,
    retries: int = 3,
    required_keys: list[str] | None = None,
) -> Any:
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            logger.info("OpenAI JSON call start: required_keys=%s", required_keys)
            response = await client.chat(
                system,
                [{"role": "user", "content": user_content}],
            )
            logger.info("OpenAI JSON call response received")
            data = json.loads(_merge_content(response))
            if required_keys:
                if isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict):
                            raise ValueError("Expected list of objects")
                        missing = [key for key in required_keys if key not in item]
                        if missing:
                            raise ValueError(f"Missing keys: {', '.join(missing)}")
                else:
                    missing = [key for key in required_keys if key not in data]
                    if missing:
                        raise ValueError(f"Missing keys: {', '.join(missing)}")
            return data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("OpenAI JSON call failed: %s", exc)
            continue
    raise RuntimeError(f"LLM JSON parse failed after {retries} attempts") from last_error


async def select_primary_roles(text: str, entities: ExtractedEntities) -> dict[str, object]:
    """Выбрать основные роли и кандидатов для обогащения через OpenAI."""

    client = OpenAIClient()
    system = (
        "Ты анализируешь текст и уже извлеченные сущности. "
        "Нужно выбрать ОСНОВНЫЕ роли (заказчик, подрядчик/исполнитель, инвестор, победитель) "
        "и список кандидатов компаний для обогащения. "
        "Если роли не очевидны, используй список companies как источник кандидатов. "
        "Если в сущностях есть компании, candidates не должен быть пустым. "
        "Верни только проверяемые факты, ничего не выдумывай. "
        "Верни ТОЛЬКО JSON вида: "
        "{\"customer\": string|null, \"contractor\": string|null, \"investor\": string|null, "
        "\"winner\": string|null, \"candidates\": [string]}."
    )
    user_content = (
        "Текст:\n"
        f"{text}\n\n"
        "Сущности (JSON):\n"
        f"{json.dumps(entities.__dict__, ensure_ascii=False)}\n\n"
        "Верни только JSON."
    )
    data = await _call_json_with_retry(
        client,
        system,
        user_content,
        required_keys=["customer", "contractor", "investor", "winner", "candidates"],
    )
    candidates = data.get("candidates") or []
    if isinstance(candidates, str):
        candidates = [candidates]
    if not isinstance(candidates, list):
        candidates = []
    return {
        "customer": data.get("customer"),
        "contractor": data.get("contractor"),
        "investor": data.get("investor"),
        "winner": data.get("winner"),
        "candidates": [str(c).strip() for c in candidates if str(c).strip()],
    }


async def extract_entities(text: str) -> ExtractedEntities:
    """Извлечь сущности из текста с помощью OpenAI."""

    client = OpenAIClient()
    system = (
        "Ты системный аналитик строительных проектов и тендеров. "
        "Твоя задача — строго и полно извлечь роли (заказчик, подрядчик/исполнитель, инвестор, "
        "победитель, заявитель) и их контакты из текста. "
        "Если в тексте явно указан заказчик или подрядчик — ОБЯЗАТЕЛЬНО верни их в соответствующих полях. "
        "Сопоставляй контакты с ближайшей ролью. "
        "Верни только проверяемые факты, ничего не выдумывай. "
        "Верни ТОЛЬКО валидный JSON одного объекта со строго фиксированными полями "
        "и массивами строк. Никаких комментариев, пояснений и текста вне JSON."
    )
    user_content = (
        "Текст для анализа (на русском):\n\n"
        f"{text}\n\n"
        "Верни только один JSON-объект со следующими полями "
        "и массивами строк (если чего-то нет — верни пустой список):\n"
        "projects, companies, persons, emails, phones, money, dates, "
        "winners, applicants, contractors, subcontractors, customers, investors.\n"
        "Важно: роли и контакты должны быть максимально полными и точными. "
        "Обязательно выделяй заказчика и подрядчика/исполнителя, если они указаны."
    )

    data = await _call_json_with_retry(
        client,
        system,
        user_content,
        required_keys=[
            "projects",
            "companies",
            "persons",
            "emails",
            "phones",
            "money",
            "dates",
            "winners",
            "applicants",
            "contractors",
            "subcontractors",
            "customers",
            "investors",
        ],
    )

    def _as_list(key: str) -> list[str]:
        value = data.get(key) or []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(v) for v in value if v]
        return []

    companies = _as_list("companies")
    persons = _as_list("persons")
    projects = [p.strip() for p in _as_list("projects") if p and p.strip()]
    return ExtractedEntities(
        projects=projects,
        companies=list(dict.fromkeys(companies)),
        persons=list(dict.fromkeys(persons)),
        emails=_as_list("emails"),
        phones=_as_list("phones"),
        money=_as_list("money"),
        dates=_as_list("dates"),
        winners=_as_list("winners"),
        applicants=_as_list("applicants"),
        contractors=_as_list("contractors"),
        subcontractors=_as_list("subcontractors"),
        customers=_as_list("customers"),
        investors=_as_list("investors"),
    )


async def classify_text(text: str) -> str:
    """Классифицировать текст по типу контента с помощью OpenAI."""

    client = OpenAIClient()
    system = (
        "Ты строго классифицируешь русскоязычные тексты по тематике строительных тендеров и проектов. "
        "Тебе нужно выбрать ОДНУ метку из набора: "
        '"project", "tender", "results", "insight", "analysis". '
        "МЕТКИ \"project\" и \"tender\" ставь ТОЛЬКО если текст явно описывает "
        "конкретный строительный/инфраструктурный объект, проект, стройку, реконструкцию, "
        "капитальный ремонт, линейный объект, инженерные сети, дороги, мосты, развязки, "
        "социальные объекты (школа, садик, больница и т.п.). "
        "Если текст касается продажи сырья/лома/оборудования, макулатуры, металлолома, "
        "услуг площадок, форм обратной связи, справочной информации, рекламы и т.п. — "
        "НИКОГДА не ставь \"project\" или \"tender\", используй \"results\", \"insight\" или \"analysis\". "
        "Ответь ТОЛЬКО валидным JSON вида {\"label\": \"...\"} без комментариев и пояснений."
    )
    user_content = (
        "Текст для классификации (на русском):\n\n"
        f"{text}\n\n"
        "Верни только JSON-объект {\"label\": \"project|tender|results|insight|analysis\"}. "
        "Помни: метки \"project\"/\"tender\" допустимы только для строительных/инфраструктурных объектов."
    )

    data = await _call_json_with_retry(
        client,
        system,
        user_content,
        required_keys=["label"],
    )
    label = str(data.get("label") or "").strip()

    allowed = {"project", "tender", "results", "insight", "analysis"}
    if label not in allowed:
        raise RuntimeError(f"LLM returned invalid label: {label}")

    return label


async def normalize_project_titles(titles: list[str]) -> dict[str, str]:
    """Нормализовать названия проектов для дедупликации через OpenAI."""

    unique_titles = [t.strip() for t in titles if t and t.strip()]
    if not unique_titles:
        return {}
    client = OpenAIClient()
    system = (
        "Ты нормализуешь названия строительных проектов для дедупликации. "
        "Оценивай смысл, своди разные формулировки одного и того же проекта "
        "к одному каноническому названию. "
        "Верни JSON-объект вида {\"items\": [{\"input\": \"<исходное>\", "
        "\"canonical\": \"<каноническое>\"}]} без текста вне JSON. "
        "Каноническое имя должно сохранять объект, локации, номера и уникальные признаки. "
        "Не добавляй выдуманные данные."
    )
    user_content = (
        "Список названий (JSON-массив строк):\n"
        f"{json.dumps(unique_titles, ensure_ascii=False)}\n\n"
        "Верни только JSON-объект с ключом items."
    )
    data = await _call_json_with_retry(
        client,
        system,
        user_content,
        required_keys=["items"],
    )
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return {}
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        original = str(item.get("input") or "").strip()
        canonical = str(item.get("canonical") or "").strip()
        if original:
            result[original] = canonical
    return result


async def classify_project_titles(titles: list[str]) -> dict[str, bool]:
    """Определить шумные/непроектные названия через OpenAI."""

    unique_titles = [t.strip() for t in titles if t and t.strip()]
    if not unique_titles:
        return {}
    client = OpenAIClient()
    system = (
        "Ты классифицируешь строки как реальные названия строительных проектов/тендеров "
        "или шум (анонсы мероприятий, реклама, общие фразы без объекта). "
        "Верни JSON-объект вида {\"items\": [{\"input\": \"<строка>\", "
        "\"is_noise\": true/false}]} без текста вне JSON. "
        "Если сомневаешься — помечай is_noise=false (оставляй в списке); отсекай только явный шум."
    )
    user_content = (
        "Список строк (JSON-массив строк):\n"
        f"{json.dumps(unique_titles, ensure_ascii=False)}\n\n"
        "Верни только JSON-объект с ключом items."
    )
    data = await _call_json_with_retry(
        client,
        system,
        user_content,
        required_keys=["items"],
    )
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return {}
    result: dict[str, bool] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        original = str(item.get("input") or "").strip()
        is_noise = bool(item.get("is_noise"))
        if original:
            result[original] = is_noise
    return result


async def choose_best_project(candidates: list[dict[str, object]]) -> int | None:
    """Выбрать наиболее полную запись проекта через OpenAI."""

    if not candidates:
        return None
    client = OpenAIClient()
    system = (
        "Ты выбираешь одну запись проекта, которую нужно оставить при дедупликации. "
        "Оцени заполненность и полезность: наличие заказчика/подрядчика, контактов, бюджета, "
        "описания и источников. Верни ТОЛЬКО JSON вида {\"keep_id\": <id>}."
    )
    user_content = (
        "Кандидаты (JSON):\n"
        f"{json.dumps(candidates, ensure_ascii=False)}\n\n"
        "Верни только JSON."
    )
    data = await _call_json_with_retry(
        client,
        system,
        user_content,
        required_keys=["keep_id"],
    )
    try:
        return int(data.get("keep_id"))
    except Exception:
        return None


async def find_duplicate_project_groups(candidates: list[dict[str, object]]) -> list[list[int]]:
    """Найти группы дубликатов проектов по доказательствам (один и тот же проект из разных источников).

    Один проект может по-разному описываться разными источниками. Важно искать доказательства:
    один регион, одна цена/бюджет, один заказчик, один исполнитель/подрядчик и т.д.
    :param candidates: Список записей проектов с полями id, name, region, budget, customer, contractor, investor, ...
    :return: Список групп: каждая группа — список id записей, которые описывают один и тот же проект.
    """

    if not candidates or len(candidates) < 2:
        return []
    client = OpenAIClient()
    system = (
        "Ты аналитик строительных проектов и тендеров. Тебе дают список записей проектов из разных источников. "
        "Один и тот же проект часто описывается по-разному: другие формулировки названия, но те же сущности. "
        "Твоя задача: определить, какие записи относятся к ОДНОМУ И ТОМУ ЖЕ проекту. "
        "Ищи доказательства: один регион, одна цена/бюджет (или близкие значения), один заказчик, один подрядчик/исполнитель, "
        "одна и та же стадия/объект. Названия могут отличаться — ориентируйся на регион, бюджет, заказчика, подрядчика. "
        "Верни ТОЛЬКО JSON вида {\"groups\": [[id1, id2, ...], [id3, id4], ...]}. "
        "Каждая внутренняя группа — список id записей, которые ты считаешь одним проектом. "
        "Записи с уникальным сочетанием доказательств не объединяй ни с кем (не включай в groups или группа из одного id). "
        "В groups включай только группы размером 2 и больше. Id брать из поля \"id\" каждой записи."
    )
    user_content = (
        "Записи проектов (JSON):\n"
        f"{json.dumps(candidates, ensure_ascii=False)}\n\n"
        "Верни только JSON с ключом groups."
    )
    try:
        data = await _call_json_with_retry(
            client,
            system,
            user_content,
            required_keys=["groups"],
        )
    except Exception:
        return []
    raw = data.get("groups")
    if not isinstance(raw, list):
        return []
    result: list[list[int]] = []
    for item in raw:
        if not isinstance(item, list):
            continue
        ids = []
        for x in item:
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                continue
        if len(ids) >= 2:
            result.append(ids)
    return result


async def summarize_project(title: str, text: str) -> str:
    """Сформировать краткое описание проекта через OpenAI."""

    client = OpenAIClient()
    system = (
        "Ты аналитик строительных проектов. "
        "Сформируй краткое описание проекта (2-4 предложения) строго по смыслу текста: "
        "объект, локация, стадия, бюджет, заказчик/подрядчик. "
        "Если данных нет, не выдумывай."
    )
    user_content = (
        f"Название проекта: {title}\n\n"
        f"Текст: {text}\n\n"
        "Верни только текст описания без лишних вводных."
    )
    response = await client.chat(system, [{"role": "user", "content": user_content}])
    return _merge_content(response).strip()


async def extract_contacts_from_snippets(snippets: list[str]) -> dict[str, str | None]:
    """Извлечь email/телефон/ИНН/ОГРН из сниппетов через OpenAI."""

    client = OpenAIClient()
    system = (
        "Ты извлекаешь контакты и реквизиты компании из фрагментов текста. "
        "Верни ТОЛЬКО JSON вида "
        "{\"email\": string|null, \"phone\": string|null, \"inn\": string|null, \"ogrn\": string|null}. "
        "Ничего не выдумывай."
    )
    user_content = (
        "Фрагменты:\n"
        f"{json.dumps(snippets, ensure_ascii=False)}\n\n"
        "Верни только JSON."
    )
    data = await _call_json_with_retry(
        client,
        system,
        user_content,
        required_keys=["email", "phone", "inn", "ogrn"],
    )
    return {
        "email": data.get("email"),
        "phone": data.get("phone"),
        "inn": data.get("inn"),
        "ogrn": data.get("ogrn"),
    }


async def extract_contacts_from_mcp_payload(payload: object) -> dict[str, str | None]:
    """Извлечь контакты из MCP-полезной нагрузки Dadata через OpenAI."""

    client = OpenAIClient()
    system = (
        "Ты извлекаешь контакты и реквизиты компании из JSON-полезной нагрузки MCP. "
        "Верни ТОЛЬКО JSON вида "
        "{\"email\": string|null, \"phone\": string|null, \"inn\": string|null, "
        "\"ogrn\": string|null, \"name\": string|null, \"address\": string|null}. "
        "Ничего не выдумывай."
    )
    user_content = (
        "JSON-полезная нагрузка:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Верни только JSON."
    )
    data = await _call_json_with_retry(
        client,
        system,
        user_content,
        required_keys=["email", "phone", "inn", "ogrn", "name", "address"],
    )
    return {
        "email": data.get("email"),
        "phone": data.get("phone"),
        "inn": data.get("inn"),
        "ogrn": data.get("ogrn"),
        "name": data.get("name"),
        "address": data.get("address"),
    }


async def extract_tender_blocks_llm(text: str, *, max_chars: int = 7000) -> list[dict]:
    """Извлечь блоки тендеров/закупок из текста через LLM. Вызывать при нехватке блоков от regex/ключевых слов.

    :param text: Текст статьи/страницы (обрезается до max_chars).
    :param max_chars: Максимум символов для отправки в LLM.
    :return: Список словарей с полями title, winner, budget, status (какие есть).
    """
    snippet = (text or "").strip()[:max_chars]
    if len(snippet) < 200:
        return []
    client = OpenAIClient()
    system = (
        "Ты извлекаешь из текста перечень тендеров, закупок, контрактов (44-ФЗ, 223-ФЗ). "
        "Для каждой сущности верни объект с полями: title (название/предмет), winner (победитель/подрядчик/исполнитель), "
        "budget (число в рублях, если есть), status (тип закупки/статус, если есть). "
        "Если в тексте нет тендеров/закупок — верни пустой массив []. "
        "Верни ТОЛЬКО JSON — массив объектов, без markdown и пояснений."
    )
    user_content = f"Текст:\n{snippet}\n\nВерни JSON-массив объектов (тендеры/закупки)."
    try:
        response = await client.chat(system, [{"role": "user", "content": user_content}])
        raw = _strip_json_markdown(_merge_content(response))
        data = json.loads(raw) if raw else []
        if not isinstance(data, list):
            data = [data] if isinstance(data, dict) else []
        out = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or item.get("name") or "").strip()
            if not title:
                continue
            budget = item.get("budget")
            if isinstance(budget, str):
                try:
                    budget = float(budget.replace(",", ".").replace(" ", ""))
                except (ValueError, TypeError):
                    budget = None
            out.append({
                "title": title[:512],
                "winner": (item.get("winner") or "").strip()[:256] or None,
                "budget": budget,
                "status": (item.get("status") or "").strip()[:64] or None,
            })
        return out
    except Exception as exc:
        logger.exception("extract_tender_blocks_llm failed: %s", exc)
        return []


async def extract_project_blocks_llm(text: str, *, max_chars: int = 7000) -> list[dict]:
    """Извлечь блоки проектов (строительство, реконструкция, объекты) из текста через LLM.

    :param text: Текст статьи/страницы (обрезается до max_chars).
    :param max_chars: Максимум символов для отправки в LLM.
    :return: Список словарей с полями name, customer_name, contractor_name, investor_name, budget.
    """
    snippet = (text or "").strip()[:max_chars]
    if len(snippet) < 200:
        return []
    client = OpenAIClient()
    system = (
        "Ты извлекаешь из текста перечень проектов: строительство, реконструкция, капремонт, объекты, инвестиционные проекты. "
        "Для каждого проекта верни объект с полями: name (название проекта/объекта), customer_name (заказчик), "
        "contractor_name (подрядчик/генподрядчик), investor_name (инвестор), budget (число в рублях, если есть). "
        "Если в тексте нет проектов — верни пустой массив []. "
        "Верни ТОЛЬКО JSON — массив объектов, без markdown и пояснений."
    )
    user_content = f"Текст:\n{snippet}\n\nВерни JSON-массив объектов (проекты)."
    try:
        response = await client.chat(system, [{"role": "user", "content": user_content}])
        raw = _strip_json_markdown(_merge_content(response))
        data = json.loads(raw) if raw else []
        if not isinstance(data, list):
            data = [data] if isinstance(data, dict) else []
        out = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or item.get("title") or "").strip()
            if not name:
                continue
            budget = item.get("budget")
            if isinstance(budget, str):
                try:
                    budget = float(budget.replace(",", ".").replace(" ", ""))
                except (ValueError, TypeError):
                    budget = None
            out.append({
                "name": name[:512],
                "customer_name": (item.get("customer_name") or item.get("customer") or "").strip()[:256] or None,
                "contractor_name": (item.get("contractor_name") or item.get("contractor") or "").strip()[:256] or None,
                "investor_name": (item.get("investor_name") or item.get("investor") or "").strip()[:256] or None,
                "budget": budget,
            })
        return out
    except Exception as exc:
        logger.exception("extract_project_blocks_llm failed: %s", exc)
        return []


__all__ = [
    "ExtractedEntities",
    "extract_entities",
    "classify_text",
    "select_primary_roles",
    "summarize_project",
    "extract_contacts_from_snippets",
    "extract_contacts_from_mcp_payload",
    "normalize_project_titles",
    "classify_project_titles",
    "choose_best_project",
    "find_duplicate_project_groups",
    "extract_tender_blocks_llm",
    "extract_project_blocks_llm",
]
