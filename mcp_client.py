"""
Mission 1 — MCP 클라이언트 테스트 스크립트
Streamable HTTP MCP 서버(mcp_server.py)에 연결해 rag_query 도구를 호출합니다.

Usage:
    python mcp_client.py [SERVER_URL] [QUESTION] [SOURCE]

Defaults:
    SERVER_URL = http://localhost:8000/mcp
    QUESTION   = "What is Python used for?"
    SOURCE     = "wiki"
"""

import asyncio
import sys

# Windows 콘솔 UTF-8 출력 설정
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession


async def call_rag(server_url: str, question: str, source: str) -> None:
    print(f"Connecting to MCP server: {server_url}")
    print(f"Question : {question}")
    print(f"Source   : {source}")
    print("-" * 60)

    async with streamablehttp_client(server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"Available tools: {tool_names}\n")

            # Call rag_query tool
            result = await session.call_tool(
                "rag_query",
                {"question": question, "source": source},
            )

            print("=== Response ===")
            for content in result.content:
                if hasattr(content, "text"):
                    print(content.text)
                else:
                    print(content)


def main() -> None:
    server_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"
    question   = sys.argv[2] if len(sys.argv) > 2 else "What is Python used for?"
    source     = sys.argv[3] if len(sys.argv) > 3 else "wiki"

    asyncio.run(call_rag(server_url, question, source))


if __name__ == "__main__":
    main()
