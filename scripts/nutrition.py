#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦当劳营养库解析器。

`list-nutrition-foods` 返回的 data 不是标准 JSON，而是一段紧凑的自定义格式：

    [160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
      猪柳麦满分,null,1288,308,16,16,24,781,213
      巨无霸,null,2146,513,27,26,42,961,171
      ...

第一行是「[条数]{字段名列表}:」，之后每行一条记录，逗号分隔，缩进两格。
官方没有单独的解析文档，所以这里把它显式实现出来，方便复用。

字段单位：energyKj = 千焦，energyKcal = 千卡，protein/fat/carbohydrate = 克，
         sodium = 毫克，calcium = 毫克。
"""
from __future__ import annotations

import re

_HEADER_RE = re.compile(r"^\[(\d+)\]\{([^}]*)\}\s*:?\s*$")

# 中文餐品名里常见的"规格后缀"，匹配营养库时先剥掉能提高命中率
_NOISE_SUFFIXES = (
    "套餐", "（中）", "(中)", "（大）", "(大)", "（小）", "(小)",
    "中杯", "大杯", "小杯", "中份", "大份", "小份", "（标准）", "(标准)",
)


class NutritionTable:
    """餐品营养表，支持按名称模糊匹配。"""

    def __init__(self, rows: list[dict] | None = None):
        self.rows: list[dict] = rows or []
        self._index: dict[str, dict] = {}
        for row in self.rows:
            key = self._normalize(row.get("productName", ""))
            if key and key not in self._index:
                self._index[key] = row

    # ---------------------------------------------------------------- 构造

    @classmethod
    def from_text(cls, text: str) -> "NutritionTable":
        """从 MCP 返回的原始文本构造可用表。"""
        return cls(cls.parse_text(text))

    @classmethod
    def from_payload(cls, payload) -> "NutritionTable":
        """从 MCP 返回值构造。payload 可以是原始字符串、dict 或已解析的列表。"""
        if isinstance(payload, cls):
            return payload
        if isinstance(payload, list):
            return cls(payload)
        if isinstance(payload, dict):
            payload = payload.get("data", payload)
            if isinstance(payload, list):
                return cls(payload)
            if not isinstance(payload, str):
                return cls([])
        if isinstance(payload, str):
            return cls(cls.parse_text(payload))
        return cls([])

    # ---------------------------------------------------------------- 解析

    @staticmethod
    def parse_text(text: str) -> list[dict]:
        """解析 `[160]{...}:` + 缩进数据行 的自定义格式。"""
        if not text:
            return []

        lines = [ln.rstrip() for ln in text.splitlines()]
        fields: list[str] = []
        rows: list[dict] = []
        start = 0

        for i, line in enumerate(lines):
            match = _HEADER_RE.match(line.strip())
            if match:
                fields = [f.strip() for f in match.group(2).split(",") if f.strip()]
                start = i + 1
                break

        if not fields:
            return []

        for line in lines[start:]:
            stripped = line.strip()
            if not stripped or stripped.startswith(("[", "#")):
                continue
            row = NutritionTable._split_row(stripped, fields)
            if row:
                rows.append(row)

        return rows

    @staticmethod
    def _split_row(line: str, fields: list[str]) -> dict | None:
        """按字段数切分。真实数据里餐品名可能自带逗号，所以多出来的部分并回第一列。"""
        parts = [p.strip() for p in line.split(",")]
        width = len(fields)
        if len(parts) < width:
            return None
        if len(parts) > width:
            overflow = len(parts) - width
            parts = [",".join(parts[: overflow + 1])] + parts[overflow + 1:]

        row: dict = {}
        for key, raw in zip(fields, parts):
            row[key] = NutritionTable._coerce(raw)
        return row

    @staticmethod
    def _coerce(raw: str):
        if raw == "" or raw.lower() == "null":
            return None
        try:
            number = float(raw)
        except ValueError:
            return raw
        return int(number) if number.is_integer() else number

    # ---------------------------------------------------------------- 查询

    @staticmethod
    def _normalize(name: str) -> str:
        if not name:
            return ""
        key = re.sub(r"\s+", "", str(name)).strip().lower()
        for noise in _NOISE_SUFFIXES:
            if key.endswith(noise.lower()) and len(key) > len(noise):
                key = key[: -len(noise)]
        return key

    def match(self, product_name: str) -> dict | None:
        """按餐品名匹配营养记录：精确 → 去规格后缀 → 双向包含。"""
        key = self._normalize(product_name)
        if not key:
            return None
        if key in self._index:
            return self._index[key]

        for index_key, row in self._index.items():
            if key in index_key or index_key in key:
                return row
        return None

    def calories(self, product_name: str, quantity: int = 1) -> float:
        """返回该餐品的千卡数，匹配不到返回 0。"""
        row = self.match(product_name)
        if not row:
            return 0.0
        kcal = row.get("energyKcal") or 0
        try:
            return float(kcal) * max(int(quantity), 0)
        except (TypeError, ValueError):
            return 0.0

    def __len__(self) -> int:
        return len(self.rows)


if __name__ == "__main__":
    demo = """[3]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
  巨无霸,null,2146,513,27,26,42,961,171
  中薯条,null,1210,289,4,12,38,165,18
  可乐中杯,null,616,147,0,0,36,0,10
"""
    table = NutritionTable.from_text(demo)
    print(f"解析到 {len(table)} 条")
    for item in ("巨无霸", "大薯条", "可乐", "不存在的餐品"):
        print(f"  {item:<8} -> {table.calories(item)} kcal")
