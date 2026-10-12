#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成演示数据 sample/demo_data.json。

目的：让没有 MCP Token 的人也能看到报告成品长什么样（README 截图 / 本地预览）。
演示数据是虚构的，但结构、字段名、时间格式与麦当劳 MCP 真实返回完全一致，
营养表则直接来自 `list-nutrition-foods` 的真实返回。

用法：
    python make_demo.py            # 需要先跑过 collect.py 拿到真实营养库
    python make_demo.py --force    # 覆盖已存在的 demo_data.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_NUTRITION = PROJECT_ROOT / "data" / "raw" / "nutrition.json"
DEMO_PATH = PROJECT_ROOT / "sample" / "demo_data.json"

STORES = [
    "麦当劳(万达广场店)", "麦当劳(中心医院店)", "麦当劳(高铁站店)",
    "麦当劳(软件园店)", "麦当劳(步行街店)", "麦当劳(大学城店)",
    "麦当劳(汽车站店)", "麦当劳(开发区店)",
]

# 场景化菜单：(餐品名, 单价, 出现权重)
BREAKFAST = [
    ("猪柳蛋麦满分", 19.0, 5), ("猪柳麦满分", 16.0, 4), ("烟肉蛋麦满分", 17.0, 3),
    ("大脆鸡扒麦满分", 20.0, 3), ("原味板烧鸡腿麦满分", 18.5, 2),
    ("脆薯饼", 9.0, 5), ("中杯鲜萃咖啡", 13.0, 6), ("小杯鲜萃咖啡", 11.0, 3),
    ("优品豆浆小杯", 8.5, 2), ("热美式中杯", 14.0, 2),
]
LUNCH = [
    ("巨无霸", 26.5, 6), ("麦辣鸡腿汉堡", 24.0, 6), ("板烧鸡腿堡", 23.5, 5),
    ("双层吉士汉堡", 21.0, 4), ("麦香鸡", 17.0, 4), ("麦香鱼", 18.5, 3),
    ("不素之霸双层牛堡", 30.0, 2), ("双层深海鳕鱼堡", 27.0, 2),
    ("中薯条", 13.0, 8), ("大薯条", 15.0, 4), ("小薯条", 11.0, 3),
    ("麦乐鸡5块", 16.0, 4), ("麦辣鸡翅-2块", 15.5, 2),
    ("可乐中杯", 10.5, 7), ("无糖可口可乐中杯", 10.5, 5), ("可乐大杯", 12.0, 3),
    ("雪碧中杯", 10.5, 2), ("中杯怡泉+C", 11.0, 1),
]
TEATIME = [
    ("圆筒冰淇淋", 6.0, 5), ("奥利奥麦旋风", 14.0, 3), ("草莓新地", 12.0, 2),
    ("香芋派", 9.0, 3), ("菠萝派", 9.0, 2), ("麦乐鸡5块", 16.0, 2),
    ("中薯条", 13.0, 3), ("冰美式中杯", 14.0, 3), ("卡布奇诺中杯", 18.0, 2),
    ("麦旋酷阳光橙", 12.0, 2),
]
LATE_NIGHT = [
    ("双层吉士汉堡", 21.0, 4), ("巨无霸", 26.5, 3), ("麦辣鸡腿汉堡", 24.0, 3),
    ("大薯条", 15.0, 5), ("麦乐鸡5块", 16.0, 4), ("麦辣鸡翅-2块", 15.5, 3),
    ("可乐大杯", 12.0, 5), ("雪碧大杯", 13.0, 2), ("迷你朱古力新地", 9.0, 2),
]

COUPON_NAMES = [
    "巨无霸 5 元券", "薯条免费兑换券", "麦乐鸡 6 元券", "咖啡第二杯半价券",
    "早餐两件套 9.9 元券", "麦旋风 4 元券", "任意消费送圆筒券", "满 30 减 6 券",
    "板烧鸡腿堡 3 元券", "麦香鸡买一送一券", "新地 5 折券", "配送费减免券",
    "1+1 随心配升级券", "派类 3 元券",
]


def weighted_pick(rng: random.Random, pool):
    total = sum(w for *_, w in pool)
    point = rng.uniform(0, total)
    for name, price, weight in pool:
        point -= weight
        if point <= 0:
            return name, price
    return pool[-1][0], pool[-1][1]


def build_combo(rng: random.Random, pool, main_count: int):
    """从场景菜单里挑 main_count 个不重复的餐品，返回 [(名称, 数量, 单价)]。"""
    picked: list[tuple[str, int, float]] = []
    used: set[str] = set()
    for _ in range(main_count):
        for _attempt in range(8):
            name, price = weighted_pick(rng, pool)
            if name not in used:
                used.add(name)
                picked.append((name, rng.choices([1, 2], weights=[9, 1])[0], price))
                break
    return picked


def generate() -> dict:
    rng = random.Random(1024)

    if not RAW_NUTRITION.exists():
        raise SystemExit(
            f"找不到真实营养库 {RAW_NUTRITION}。\n"
            "请先运行：set MCD_MCP_TOKEN=你的Token && python collect.py --only nutrition"
        )
    nutrition = json.loads(RAW_NUTRITION.read_text(encoding="utf-8"))

    start = datetime(2026, 1, 1, 8, 0, 0)
    end = datetime(2026, 10, 11, 21, 0, 0)
    span_days = (end - start).days

    orders = []
    seq = 1
    for _ in range(68):
        day_offset = int(rng.triangular(0, span_days, span_days * 0.82))
        day = (start + timedelta(days=day_offset)).date()
        weekday = day.weekday()

        roll = rng.random()
        if roll < 0.32:
            scene, hour = "breakfast", rng.choice([7, 7, 8, 8, 8, 9])
        elif roll < 0.78:
            scene, hour = "lunch", rng.choice([11, 12, 12, 12, 13, 13, 18, 19])
        elif roll < 0.89:
            scene, hour = "teatime", rng.choice([14, 15, 15, 16, 16])
        else:
            scene, hour = "night", rng.choice([22, 22, 23])

        # 周末更少，深夜几乎只在周末
        if weekday >= 5 and scene == "lunch" and rng.random() < 0.45:
            continue
        if scene == "night" and weekday < 5 and rng.random() < 0.55:
            continue
        if scene == "breakfast" and weekday >= 5 and rng.random() < 0.7:
            continue

        pool = {"breakfast": BREAKFAST, "lunch": LUNCH,
                "teatime": TEATIME, "night": LATE_NIGHT}[scene]
        combo_size = {"breakfast": rng.choice([2, 2, 3]), "lunch": rng.choice([2, 3, 3, 3, 4]),
                      "teatime": rng.choice([1, 2, 2]), "night": rng.choice([2, 3, 3])}[scene]
        picked = build_combo(rng, pool, combo_size)

        amount = sum(price * qty for _, qty, price in picked)
        amount = round(amount * rng.uniform(0.95, 1.0), 1)
        if rng.random() < 0.35:           # 用券
            amount = max(amount - rng.choice([3, 4, 5, 6]), 8.0)
        amount = round(amount, 1)

        moment = datetime(day.year, day.month, day.day, hour,
                          rng.choice([5, 12, 18, 24, 31, 37, 42, 49, 55]),
                          rng.choice([3, 11, 26, 38, 47, 52]))
        delivery = rng.random() < 0.34
        store = rng.choices(STORES, weights=[22, 18, 14, 13, 12, 9, 7, 5])[0]

        orders.append({
            "orderId": f"MCD2026{seq:08d}",
            "orderType": "2" if delivery else "1",
            "createTime": moment.strftime("%Y-%m-%d %H:%M:%S"),
            "beType": "2" if delivery else "1",
            "beCode": f"BE{rng.randint(1000, 9999)}",
            "storeCode": f"{rng.randint(10000, 99999)}",
            "storeName": store,
            "orderStatus": "已完成",
            "realTotalAmount": f"{amount:.2f}",
            "orderProductList": [
                {"productCode": f"P{rng.randint(100000, 999999)}", "productName": name,
                 "quantity": qty, "comboItemList": []}
                for name, qty, _ in picked
            ],
        })
        seq += 1

    orders.sort(key=lambda o: o["createTime"])

    demo = {
        "_note": "演示数据，人物与订单均为虚构；营养表来自麦当劳 MCP list-nutrition-foods 真实返回。",
        "now_time": {
            "success": True, "code": 200, "message": "请求成功（演示数据）",
            "data": {
                "formatted": "2026-10-11 21:00:00", "date": "2026-10-11",
                "datetime": "2026-10-11T21:00:00.000", "year": 2026, "month": 10,
                "day": 11, "dayOfWeek": "SUNDAY", "timezone": "GMT+08:00", "offset": "+08:00",
            },
        },
        "orders": {"success": True, "code": 200, "message": "请求成功（演示数据）",
                   "data": {"list": orders}},
        "account": {
            "success": True, "code": 200, "message": "请求成功（演示数据）",
            "data": {
                "accountId": "DEMO-0000-0000-0000-000000000000",
                "currency": "麦享会积分",
                "availablePoint": "1280", "accumulativePoint": "4680",
                "expiredPoint": "320", "usedPoint": "3400", "frozenPoint": "0",
                "currentMouthExpirePoint": "180", "lastMouthExpirePoint": "60",
                "nextMouthExpirePoint": "140",
            },
        },
        "coupons": {
            "success": True, "code": 200, "message": "请求成功（演示数据）",
            "data": {"list": [
                {"couponName": name, "status": "可用"} for name in COUPON_NAMES
            ]},
        },
        "prizes": {
            "success": True, "code": 200, "message": "请求成功（演示数据）",
            "data": {"list": [
                {"prizeName": "中薯条兑换券", "prizeTime": "2026-03-18 12:41:09"},
                {"prizeName": "50 积分", "prizeTime": "2026-06-02 19:07:55"},
                {"prizeName": "圆筒冰淇淋券", "prizeTime": "2026-09-21 15:22:31"},
            ]},
        },
        "mall": {
            "success": True, "code": 200, "message": "请求成功（演示数据）",
            "data": [{"hasNext": False, "lastId": 0, "list": [
                {"orderId": "MALL20260512001", "productName": "麦麦商城马克杯",
                 "pointAmount": "900", "createTime": "2026-05-12 10:31:00"},
            ]}],
        },
        "nutrition": nutrition,
    }
    return demo


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="生成演示数据")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    args = parser.parse_args(argv)

    if DEMO_PATH.exists() and not args.force:
        print(f"已存在 {DEMO_PATH}，如需重新生成请加 --force")
        return 0

    demo = generate()
    DEMO_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEMO_PATH.write_text(json.dumps(demo, ensure_ascii=False, indent=2), encoding="utf-8")

    orders = demo["orders"]["data"]["list"]
    total = sum(float(o["realTotalAmount"]) for o in orders)
    print(f"已生成 {DEMO_PATH}")
    print(f"  订单 {len(orders)} 笔 · 虚构消费 ¥{total:,.2f} · 营养表 {len(demo['nutrition'])} 款")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
