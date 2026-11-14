'.env access test script MCP Datata with keys.'
import asyncio
import sys
from pathlib import Path

# Load .env from the root of the project
root = Path(__file__).resolve().parent.parent
env_file = root / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and k not in __import__("os").environ:
                __import__("os").environ[k] = v

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import get_settings
from app.services.dadata_mcp import check_dadata_mcp_server


async def main():
    s = get_settings()
    print('DADATA_API_KEY:', bool(s.dadata_api_key))
    print('DADATA_SECRET_KEY:', bool(s.dadata_secret_key))
    print('Test MCP Datata...')
    result = await check_dadata_mcp_server()
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
