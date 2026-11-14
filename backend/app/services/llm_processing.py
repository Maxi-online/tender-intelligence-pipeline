'LLM Module: Extraction and Classification (OpenAI)).'

from __future__ import annotations

import json
import logging
import re
from typing import Any
from dataclasses import dataclass

from app.services.openai_client import OpenAIClient

logger = logging.getLogger(__name__)


def _strip_json_markdown(raw: str) -> str:
    "Remove the wrapping ```json ... `'' from LLM's response."
    s = (raw or "").strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


@dataclass
class ExtractedEntities:
    'Results of Essentials.'

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
    'Select key roles and candidates for enrichment through OpenAI.'

    client = OpenAIClient()
    system = (
        'You analyze the text and the already extracted essences. '
        'Key roles (contractor, contractor/implementer, investor, winner) should be selected) '
        'And a list of company candidates for enrichment. '
        "If the roles aren't obvious, use the companies list as the source of the candidates. "
        "If there's a company in the entities, candidates shouldn't be empty. "
        "Just give me the facts you've checked, don't make anything up. "
        'Just give JSON back the species: '
        "{\"customer\": string|null, \"contractor\": string|null, \"investor\": string|null, "
        "\"winner\": string|null, \"candidates\": [string]}."
    )
    user_content = (
        'Text:\n'
        f"{text}\n\n"
        'Material (JSON):\n'
        f"{json.dumps(entities.__dict__, ensure_ascii=False)}\n\n"
        'Just give it back to JSON.'
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
    'Extract Essentials from Text with OpenAI.'

    client = OpenAIClient()
    system = (
        "You're a systems analyst for construction projects and tenders. "
        'Your task is to strictly and fully extract the roles (order, contractor/executive, investor), '
        'The author, the applicant) and their contacts from the text. '
        'If the text clearly indicates the employer or contractor - Reimbursably return them in the relevant fields. '
        'Compare contacts with the immediate role. '
        "Just give me the facts you've checked, don't make anything up. "
        'Give back the only JSON with fixed fields '
        'and row arrays. No comment, no explanation, and no text outside JSON.'
    )
    user_content = (
        'Analysis text (Russian):\n\n'
        f"{text}\n\n"
        'Give back only one JSON object with the next fields. '
        'And the string arrays (if anything is missing, give me back the blank list)):\n'
        "projects, companies, persons, emails, phones, money, dates, "
        "winners, applicants, contractors, subcontractors, customers, investors.\n"
        'Important: roles and contacts should be as complete and accurate as possible. '
        'Make mandatory the assignment of the employer and contractor/operator if specified.'
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
    'Classify text by content type using OpenAI.'

    client = OpenAIClient()
    system = (
        'You strictly classify Russian-language texts on construction tenders and projects. '
        'You need to choose a single tag from the set: '
        '"project", "tender", "results", "insight", "analysis". '
        '"project" and "tender" METHS only if the text clearly describes '
        'specific construction/infrastructure facility, project, construction, reconstruction, '
        'Major maintenance, line object, engineering networks, roads, bridges, interchanges, '
        'Social facilities (schools, day care, hospital, etc.). '
        'If the text relates to the sale of raw materials/refills/equipment, paperwork, scrap metal, '
        'Site services, feedback forms, background information, advertising, etc. — '
        'Never put "project" or "tender", use "results", "insight" or "analysis"". '
        'Answer the {"label": "..."} type with no comment or explanation.'
    )
    user_content = (
        'Classification text (Russian):\n\n'
        f"{text}\n\n"
        'Only return the JSON object {"label": "project\\tender\\effects\\insight\\analysis""}. '
        'Remember: "project"/ "tender" labels are only allowed for construction/infrastructure facilities.'
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
    'Normalize the names of projects for deduplying through OpenAI.'

    unique_titles = [t.strip() for t in titles if t and t.strip()]
    if not unique_titles:
        return {}
    client = OpenAIClient()
    system = (
        'You normalize the names of construction projects for deduplication. '
        'Assess the meaning, sum up the different language of the same draft '
        'to one canonical name. '
        'Give it back JSON-object of the species {"items": [{"input": "<Baseline>", '
        '"canonical": "<canonical>"}]} without text outside JSON. '
        'Canon name should keep object, location, numbers and unique features. '
        "Don't add fake data."
    )
    user_content = (
        'List of names:\n'
        f"{json.dumps(unique_titles, ensure_ascii=False)}\n\n"
        'Only return the JSON object with the key items.'
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
    'Identify noisy/non-project names via OpenAI.'

    unique_titles = [t.strip() for t in titles if t and t.strip()]
    if not unique_titles:
        return {}
    client = OpenAIClient()
    system = (
        'You classify the lines as real names of construction projects/tenders '
        'or noise (events of events, advertising, general phrases without object)). '
        'Give it back JSON-object of the species {"items": [{"input": "<Line>", '
        '"is_noise": true/false}]} without text outside JSON. '
        'If you doubt it, mark is_noise=false; cut off only the clear noise.'
    )
    user_content = (
        'List of rows:\n'
        f"{json.dumps(unique_titles, ensure_ascii=False)}\n\n"
        'Only return the JSON object with the key items.'
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
    'Select the most complete recording of the project via OpenAI.'

    if not candidates:
        return None
    client = OpenAIClient()
    system = (
        'You choose one project record that you need to leave when deduplying. '
        'Assess occupancy and usefulness: customer/contractor, contact, budget, '
        'Descriptions and sources. Give JSON back the species {"keep_id": <id>}.'
    )
    user_content = (
        'Candidates (JSON):\n'
        f"{json.dumps(candidates, ensure_ascii=False)}\n\n"
        'Just give it back to JSON.'
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
    """Find duplicate evidence project teams (same project from different sources)).

    One project can be described differently by different sources. It's important to find evidence:
    One region, one price/budget, one employer, one executing agent/contractor, etc.
    :Param candidates: List of project entries with fields id, name, region, budget, constomer, controller, promoter, ...
    :Return: List of groups: each group is a list of id records that describe the same project.
    """

    if not candidates or len(candidates) < 2:
        return []
    client = OpenAIClient()
    system = (
        "You're an analyst of construction projects and tenders. They give you a list of projects from different sources. "
        'The same draft is often described in different ways: different wordings of the title but the same substance. '
        'Your job is to determine which records are relevant to one project. '
        'Search for evidence: one region, one price/budget (or close values), one customer, one contractor/executive, '
        'same stage/site. Names may differ — focus on the region, budget, customer, contractor. '
        'Just give it back JSON species {"groups": [[id1, id2, ...], [id3, id4], ...]}. '
        'Each in-house group is a list of id records that you consider to be one project. '
        'Records with a unique combination of evidence do not combine with anyone (not to be included in groups or group of id)). '
        'In groups, only groups 2 and more are included. Id take from the "id" field of each record.'
    )
    user_content = (
        'Project records (JSON):\n'
        f"{json.dumps(candidates, ensure_ascii=False)}\n\n"
        'Just give it back to JSON with the group key.'
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
    'Create a brief description of the project through OpenAI.'

    client = OpenAIClient()
    system = (
        "You're an analyst of construction projects. "
        'Form a brief description of the draft (2-4 sentences) strictly within the meaning of the text: '
        'Subject matter, location, stage, budget, employer/contractor. '
        "If there's no data, don't make it up."
    )
    user_content = (
        f"Project title: {title}\n\n"
        f"Text: {text}\n\n"
        'Just return the description without the input.'
    )
    response = await client.chat(system, [{"role": "user", "content": user_content}])
    return _merge_content(response).strip()


async def extract_contacts_from_snippets(snippets: list[str]) -> dict[str, str | None]:
    'Extract email/telephone/INN/OGRN from Snippets via OpenAI.'

    client = OpenAIClient()
    system = (
        'You extract contacts and company requests from text fragments. '
        'Give me back the JSON view. '
        "{\"email\": string|null, \"phone\": string|null, \"inn\": string|null, \"ogrn\": string|null}. "
        "Don't make it up."
    )
    user_content = (
        'Fragments:\n'
        f"{json.dumps(snippets, ensure_ascii=False)}\n\n"
        'Just give it back to JSON.'
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
    'Extract contacts from the MCP useful load of Dadata through OpenAI.'

    client = OpenAIClient()
    system = (
        'You extract company contacts and requests from the JSON MCP useful load. '
        'Give me back the JSON view. '
        "{\"email\": string|null, \"phone\": string|null, \"inn\": string|null, "
        "\"ogrn\": string|null, \"name\": string|null, \"address\": string|null}. "
        "Don't make it up."
    )
    user_content = (
        'JSON Useful Load:\n'
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        'Just give it back to JSON.'
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
    """Extract tender/buy blocks from the text through LLM. Call for lack of regex/keyword blocks.

    :param text: Text of article/page (cut to max_chars)).
    :param max_chars: Maximum symbol value to be sent to LLM.
    :Return: List of dictionaries with fields of title, winner, budget, status).
    """
    snippet = (text or "").strip()[:max_chars]
    if len(snippet) < 200:
        return []
    client = OpenAIClient()
    system = (
        'You extract from the text a list of tender, purchases, contracts (44-FZ, 223-FZ)). '
        'For each entity, return the object with fields: title/subject, Winner (winner/contractor/operator)), '
        'budget (number of rubles, if any), status (type of purchase/status, if any)). '
        'If there are no tenders/purchases in the text, return the empty array []. '
        'Give back JSON alone, the array of objects, without markdown and explanations.'
    )
    user_content = f"Text:\n{snippet}\n\n Return the JSON mass of the objects (tenders/purchases)."
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
    """Extract blocks of projects (building, reconstruction, objects) from the text through the LLM.

    :param text: Text of article/page (cut to max_chars)).
    :param max_chars: Maximum symbol value to be sent to LLM.
    :return: List of field dictionariesname, customer_name, contractor_name, investor_name, budget.
    """
    snippet = (text or "").strip()[:max_chars]
    if len(snippet) < 200:
        return []
    client = OpenAIClient()
    system = (
        'You extract from the text a list of projects: construction, reconstruction, capremont, objects, investment projects. '
        'For each project, return the object with fields: name (project/site name), customer_name (contractor)), '
        'contractor_name (contractor/contractor), investor_name (investor), budget (number of rubles, if any)). '
        'If there are no projects in the text, return the empty array []. '
        'Give back JSON alone, the array of objects, without markdown and explanations.'
    )
    user_content = f"Text:\n{snippet}\n\n"
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
