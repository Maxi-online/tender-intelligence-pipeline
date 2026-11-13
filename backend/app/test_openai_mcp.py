"""Тест: доступность Dadata через OpenAI Responses API + MCP."""
import asyncio

from app.services.dadata_mcp import enrich_company_with_mcp


async def main():
    inn = "7842155505"
    print("Calling Dadata via OpenAI MCP for INN", inn)
    try:
        result = await enrich_company_with_mcp(inn)
        if result:
            print("OK. Result keys:", list(result.keys()) if isinstance(result, dict) else type(result))
        else:
            print("Result: None (check backend logs for 424 or other errors)")
    except Exception as e:
        print("Exception:", type(e).__name__, str(e))


if __name__ == "__main__":
    asyncio.run(main())
