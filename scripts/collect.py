#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采集麦当劳 MCP 数据，落到 data/raw/ 目录。

用法：
    export MCD_MCP_TOKEN="你的Token"
    python collect.py                 # 采集全部
    python collect.py --only orders   # 只采集某几项

采集项与对应 MCP Tool：
    now_time   -> now-time-info        服务器时间（确定报告周期）
    orders     -> order-list           到店 / 外送历史订单
    account    -> query-my-account     积分账户
    coupons    -> query-my-coupons     卡包优惠券
    prizes     -> query-my-prizes      积分抽奖中奖记录
    mall       -> mall-order-list      麦麦商城兑换订单
    nutrition  -> list-nutrition-foods 160 款餐品营养库
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcd_client import McdMcpClient, McdMcpError  # noqa: E402
from nutrition import NutritionTable  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

TASKS = {
    "now_time": ("now-time-info", {}),
    "orders": ("order-list", {}),
    "account": ("query-my-account", {}),
    "coupons": ("query-my-coupons", {"page": "1", "pageSize": "200"}),
    "prizes": ("query-my-prizes", {"pageNum": "1", "pageSize": "50"}),
    "mall": ("mall-order-list", {"size": 10}),
    "nutrition": ("list-nutrition-foods", {}),
}


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def collect(only: list[str] | None = None) -> int:
    targets = [k for k in TASKS if not only or k in only]
    client = McdMcpClient()

    try:
        server = client.initialize()
        print(f"已连接 {server.get('serverInfo', {}).get('name')} "
              f"v{server.get('serverInfo', {}).get('version')}")
    except McdMcpError as exc:
        print(f"握手失败：{exc}", file=sys.stderr)
        return 1

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"collectedAt": datetime.now().isoformat(timespec="seconds"), "items": {}}

    for key in targets:
        tool_name, args = TASKS[key]
        try:
            payload = client.call(tool_name, args, unwrap_data=False)
            ok = not (isinstance(payload, dict) and payload.get("code") not in (None, 200))
        except McdMcpError as exc:
            print(f"  [失败] {key:<10} {exc}")
            manifest["items"][key] = {"tool": tool_name, "ok": False, "error": str(exc)}
            continue

        # 营养库走独立落地：原始文本 + 解析后的结构化数据
        if key == "nutrition":
            text = payload.get("data") if isinstance(payload, dict) else payload
            text = text if isinstance(text, str) else json.dumps(payload, ensure_ascii=False)
            (RAW_DIR / "nutrition.txt").write_text(text, encoding="utf-8")
            rows = NutritionTable.parse_text(text)
            dump(RAW_DIR / "nutrition.json", rows)
            summary = f"{len(rows)} 款餐品"
        else:
            dump(RAW_DIR / f"{key}.json", payload)
            summary = _summarize(key, payload)

        print(f"  [完成] {key:<10} {summary}")
        manifest["items"][key] = {"tool": tool_name, "ok": ok, "summary": summary}

    dump(RAW_DIR / "manifest.json", manifest)
    print(f"\n原始数据已写入 {RAW_DIR}")
    return 0


def _summarize(key: str, payload) -> str:
    data = payload.get("data") if isinstance(payload, dict) else payload
    try:
        if key == "orders":
            return f"{len(data.get('list') or [])} 笔订单"
        if key == "account":
            return f"可用积分 {data.get('availablePoint', '-')}"
        if key == "coupons":
            coupons = data.get("list") if isinstance(data, dict) else None
            return f"{len(coupons)} 张券" if coupons else "券包为空"
        if key == "prizes":
            records = data.get("list") if isinstance(data, dict) else None
            return f"{len(records)} 条中奖记录" if records else "无中奖记录"
        if key == "mall":
            rows = data[0].get("list") if isinstance(data, list) and data else None
            return f"{len(rows)} 笔商城订单" if rows else "无商城订单"
    except (AttributeError, IndexError, TypeError):
        pass
    return "已获取"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="采集麦当劳 MCP 数据")
    parser.add_argument("--only", nargs="+", choices=sorted(TASKS),
                        help="只采集指定项")
    raise SystemExit(collect(parser.parse_args().only))
