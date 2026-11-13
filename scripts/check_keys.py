import json
import os
import ssl
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener


ENV_PATH = Path("g:/AI/tpis2/.env")


def load_env():
    values = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if (not line) or line.startswith("#") or ("=" not in line):
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
                val = val[1:-1]
            values[key] = val
    return values


def get_var(env, key):
    return env.get(key) or os.getenv(key)


def build_opener_with_proxy(proxy_url):
    if not proxy_url:
        return build_opener()
    handler = ProxyHandler({"http": proxy_url, "https": proxy_url})
    return build_opener(handler)


def http_json(url, *, headers, payload, opener):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, headers=headers)
    try:
        with opener.open(request, timeout=30) as resp:
            ok = resp.status == 200
        return ok, None
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def main():
    env = load_env()
    proxy_url = get_var(env, "HTTP_PROXY_URL")
    opener = build_opener_with_proxy(proxy_url)

    results = []

    openrouter_key = get_var(env, "OPENROUTER_API_KEY")
    if openrouter_key:
        payload = {
            "model": "anthropic/claude-sonnet-4.5",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://live.staticflickr.com/3851/14825276609_098cac593d_b.jpg"
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 16,
            "temperature": 0,
        }
        ok, err = http_json(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            opener=opener,
        )
        results.append(("openrouter", ok, err))
    else:
        results.append(("openrouter", False, "OPENROUTER_API_KEY missing"))

    perplex_key = get_var(env, "PERPLEXITY_API_KEY")
    perplex_model = get_var(env, "PERPLEXITY_MODEL") or "sonar-pro"
    if perplex_key:
        payload = {
            "model": perplex_model,
            "messages": [
                {"role": "system", "content": "You are a test agent."},
                {"role": "user", "content": "ping"},
            ],
            "max_tokens": 8,
            "temperature": 0,
        }
        ok, err = http_json(
            "https://api.perplexity.ai/v2/chat/completions",
            headers={
                "Authorization": f"Bearer {perplex_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            opener=opener,
        )
        results.append(("perplexity", ok, err))
    else:
        results.append(("perplexity", False, "PERPLEXITY_API_KEY missing"))

    dadata_key = get_var(env, "DADATA_API_KEY")
    dadata_secret = get_var(env, "DADATA_SECRET_KEY")
    if dadata_key:
        payload = {"query": "7707083893", "count": 1}
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {dadata_key}",
        }
        if dadata_secret:
            headers["X-Secret"] = dadata_secret
        ok, err = http_json(
            "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party",
            headers=headers,
            payload=payload,
            opener=opener,
        )
        results.append(("dadata_rest", ok, err))
    else:
        results.append(("dadata_rest", False, "DADATA_API_KEY missing"))

    for name, ok, err in results:
        if ok:
            print(f"{name}: OK")
        else:
            print(f"{name}: FAIL - {err}")

    failed = [item for item in results if not item[1]]
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
