#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦当劳 MCP 极简客户端（纯标准库，零依赖）。

MCP Server : https://mcp.mcd.cn
传输协议   : Streamable HTTP
鉴权       : 请求头 Authorization: Bearer <MCP_TOKEN>

为什么单独写一个客户端？
  WorkBuddy 能直接调用 MCP 工具，但很多朋友想在自己的脚本 / CI / 其他 MCP Client
  里复用同一套采集逻辑。这里只依赖 Python 标准库，拷走就能跑。

用法：
    export MCD_MCP_TOKEN="你的Token"      # Windows CMD: set MCD_MCP_TOKEN=...
    python mcd_client.py list-tools
    python mcd_client.py call order-list
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-03-26"
CLIENT_INFO = {"name": "maimen-wrapped", "version": "1.0.0"}


class McdMcpError(RuntimeError):
    """麦当劳 MCP 调用异常。"""


def parse_tool_text(text: str):
    """把 MCP 工具返回的文本还原成结构化数据。

    MCP 工具返回的 text 有两种形态：
      1. 「# API Response Information ... ## Original Response」+ JSON 信封
      2. 纯 Markdown 文本（例如活动日历、空券包提示）

    返回：解析成功时为 dict / list，解析不了则原样返回字符串。
    """
    body = text or ""
    marker = "## Original Response"
    if marker in body:
        body = body.split(marker, 1)[1].strip()
    else:
        body = body.strip()

    # 优先整体解析
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        pass

    # 退一步：截取最外层 JSON 对象
    match = re.search(r"\{.*\}", body, re.S)
    if match:
        try:
            return json.loads(match.group(0))
        except (ValueError, TypeError):
            pass

    return text


def unwrap(payload):
    """剥掉 MCP 的 {success, code, message, datetime, data} 信封，取出 data。

    注意：list-nutrition-foods 的 data 本身是一段字符串，这里不做二次解析。
    """
    if isinstance(payload, dict) and "data" in payload and "success" in payload:
        return payload["data"]
    return payload


class McdMcpClient:
    """麦当劳 MCP 客户端。"""

    def __init__(self, token: str | None = None, url: str = DEFAULT_URL, timeout: int = 60):
        self.token = (token or os.environ.get("MCD_MCP_TOKEN") or "").strip()
        if not self.token:
            raise McdMcpError(
                "未找到 MCP Token。请先设置环境变量 MCD_MCP_TOKEN，"
                "Token 可在 https://open.mcd.cn/mcp 控制台申请。"
            )
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._seq = 0

    # ------------------------------------------------------------------ 底层

    def _rpc(self, method: str, params: dict) -> dict:
        self._seq += 1
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": self._seq, "method": method, "params": params},
            ensure_ascii=False,
        ).encode("utf-8")

        request = urllib.request.Request(self.url, data=payload, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json, text/event-stream")
        request.add_header("Authorization", "Bearer " + self.token)

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            hint = {
                401: "Token 无效、已过期或未提供，请到控制台重新申请",
                429: "触发限流（600 次/分钟），请降低请求频率",
            }.get(exc.code, "")
            raise McdMcpError(f"HTTP {exc.code} {hint}".strip()) from exc
        except urllib.error.URLError as exc:
            raise McdMcpError(f"网络异常：{exc.reason}") from exc

        return self._decode(body)

    @staticmethod
    def _decode(body: str) -> dict:
        body = (body or "").strip()
        if body.startswith(("event:", "data:", "id:")):
            lines = [ln[5:].strip() for ln in body.splitlines() if ln.startswith("data:")]
            body = lines[-1] if lines else ""
        if not body:
            raise McdMcpError("MCP 返回了空响应")
        message = json.loads(body)
        if "error" in message:
            raise McdMcpError(f"MCP 错误：{message['error']}")
        return message.get("result", {})

    # ------------------------------------------------------------------ 对外

    def initialize(self) -> dict:
        """握手，返回服务端信息。"""
        return self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )

    def list_tools(self) -> list[dict]:
        return self._rpc("tools/list", {}).get("tools", [])

    def call_raw(self, name: str, arguments: dict | None = None) -> str:
        """调用工具，返回原始文本。"""
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        for item in result.get("content", []):
            if item.get("type") == "text":
                return item.get("text", "")
        return ""

    def call(self, name: str, arguments: dict | None = None, *, unwrap_data: bool = True):
        """调用工具，返回结构化结果（默认剥掉 data 信封）。"""
        payload = parse_tool_text(self.call_raw(name, arguments))
        return unwrap(payload) if unwrap_data else payload


def _main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0

    client = McdMcpClient()
    action = argv[0]

    if action == "list-tools":
        tools = client.list_tools()
        print(f"共 {len(tools)} 个工具：\n")
        for tool in tools:
            print(f"  {tool['name']:<28} {tool.get('description', '').splitlines()[0][:60]}")
        return 0

    if action == "call":
        if len(argv) < 2:
            print("用法：python mcd_client.py call <tool-name> [json参数]", file=sys.stderr)
            return 2
        args = json.loads(argv[2]) if len(argv) > 2 else {}
        print(json.dumps(client.call(argv[1], args, unwrap_data=False),
                         ensure_ascii=False, indent=2))
        return 0

    print(f"未知命令：{action}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
