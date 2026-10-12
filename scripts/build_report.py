#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把麦当劳 MCP 原始数据算成一份「麦门年度报告」。

用法：
    python build_report.py                      # 读 data/raw/，输出到 data/
    python build_report.py --demo               # 用 sample/demo_data.json 出演示报告
    python build_report.py --open               # 生成后自动用浏览器打开

设计原则：
  · 只依赖标准库，双击就能跑，不需要装任何东西；
  · 不联网 —— 数据全部来自 collect.py 落地的本地文件；
  · 输出单个自包含 HTML，CSS 内联、无外链、无脚本，方便截图与分享。
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import webbrowser
from collections import Counter
from datetime import datetime
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nutrition import NutritionTable  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEMO_PATH = PROJECT_ROOT / "sample" / "demo_data.json"
OUTPUT_DIR = PROJECT_ROOT / "data"

MEAL_DELIVERY = {"2", 2, "外送", "DELIVERY"}
BIGMAC_KCAL = 513.0          # 一个巨无霸约 513 千卡
EGG_PROTEIN = 6.0            # 一个鸡蛋约 6 克蛋白质
RUN_KCAL_PER_KM = 60.0       # 慢跑 1 公里约消耗 60 千卡
SODIUM_TO_SALT = 2.54        # 1 mg 钠 ≈ 2.54 mg 食盐


# ====================================================================== 读取

def load_raw(raw_dir: Path) -> dict:
    """读取 collect.py 落地的原始数据。"""
    raw: dict = {}
    for name in ("now_time", "orders", "account", "coupons", "prizes", "mall"):
        path = raw_dir / f"{name}.json"
        if path.exists():
            try:
                raw[name] = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
    nutrition_path = raw_dir / "nutrition.json"
    if nutrition_path.exists():
        try:
            raw["nutrition"] = json.loads(nutrition_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return raw


# ====================================================================== 工具

def parse_time(value):
    """订单时间可能是字符串、秒级或毫秒级时间戳，统一成 datetime。"""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip().replace("/", "-")
    if text.isdigit():
        return parse_time(int(text))
    text = text.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text[:len(fmt) + 8], fmt)
        except ValueError:
            continue
    return None


def to_float(value, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def money(value: float) -> str:
    return f"{value:,.2f}"


def is_delivery(order_type) -> bool:
    return order_type in MEAL_DELIVERY


def envelope(payload) -> dict:
    """从 {data: ...} 信封里取出 data，取不到就原样返回。"""
    if isinstance(payload, dict) and "data" in payload:
        return {"data": payload["data"]}
    return {"data": payload}


# ====================================================================== 分析

def analyze(raw: dict) -> dict:
    table = NutritionTable(raw.get("nutrition") or [])

    orders_root = envelope(raw.get("orders") or {}).get("data") or {}
    orders = orders_root.get("list") or []
    account = (envelope(raw.get("account") or {}).get("data")) or {}
    coupons_root = (envelope(raw.get("coupons") or {}).get("data")) or {}
    coupons = coupons_root.get("list") if isinstance(coupons_root, dict) else None
    prizes_root = (envelope(raw.get("prizes") or {}).get("data")) or {}
    prizes = prizes_root.get("list") if isinstance(prizes_root, dict) else None

    now_root = (envelope(raw.get("now_time") or {}).get("data")) or {}
    now = parse_time(now_root.get("formatted")) or parse_time(now_root.get("datetime")) or datetime.now()

    stats: dict = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "year": now.year,
        "order_count": 0,
        "total_amount": 0.0,
        "avg_amount": 0.0,
        "store_count": 0,
        "top_store": None,
        "delivery_count": 0,
        "products": [],            # [(名称, 份数)]
        "kcal": 0.0,
        "protein": 0.0,
        "fat": 0.0,
        "carb": 0.0,
        "sodium": 0.0,
        "matched_products": 0,
        "total_products": 0,
        "weekday": Counter(),
        "hours": Counter(),
        "points_available": to_float(account.get("availablePoint")),
        "points_accumulative": to_float(account.get("accumulativePoint")),
        "points_expired": to_float(account.get("expiredPoint")),
        "points_expiring": to_float(account.get("currentMouthExpirePoint")),
        "coupon_count": len(coupons) if coupons else 0,
        "prize_count": len(prizes) if prizes else 0,
        "cities_note": "",
    }

    store_counter: Counter = Counter()
    product_counter: Counter = Counter()
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

    for order in orders:
        if not isinstance(order, dict):
            continue
        stats["order_count"] += 1
        stats["total_amount"] += to_float(order.get("realTotalAmount"))

        store = (order.get("storeName") or "").strip()
        if store:
            store_counter[store] += 1

        if is_delivery(order.get("orderType")):
            stats["delivery_count"] += 1

        moment = parse_time(order.get("createTime"))
        if moment:
            stats["weekday"][weekday_names[moment.weekday()]] += 1
            stats["hours"][moment.hour] += 1

        for item in order.get("orderProductList") or []:
            if not isinstance(item, dict):
                continue
            name = (item.get("productName") or "").strip()
            if not name:
                continue
            try:
                quantity = int(item.get("quantity") or 1)
            except (TypeError, ValueError):
                quantity = 1
            quantity = max(quantity, 1)

            product_counter[name] += quantity
            stats["total_products"] += quantity
            row = table.match(name)
            if row:
                stats["matched_products"] += quantity
                stats["kcal"] += to_float(row.get("energyKcal")) * quantity
                stats["protein"] += to_float(row.get("protein")) * quantity
                stats["fat"] += to_float(row.get("fat")) * quantity
                stats["carb"] += to_float(row.get("carbohydrate")) * quantity
                stats["sodium"] += to_float(row.get("sodium")) * quantity

    if stats["order_count"]:
        stats["total_amount"] = round(stats["total_amount"], 2)
        stats["avg_amount"] = round(stats["total_amount"] / stats["order_count"], 2)

    stats["store_count"] = len(store_counter)
    if store_counter:
        name, count = store_counter.most_common(1)[0]
        stats["top_store"] = {"name": name, "count": count}
    stats["products"] = product_counter.most_common(5)
    stats["product_total"] = sum(product_counter.values())

    # 营养换算 —— 把干巴巴的数字变成能吹的段子
    stats["equiv"] = {
        "bigmac": stats["kcal"] / BIGMAC_KCAL,
        "eggs": stats["protein"] / EGG_PROTEIN,
        "salt": stats["sodium"] * SODIUM_TO_SALT / 1000.0,
        "km": stats["kcal"] / RUN_KCAL_PER_KM,
    }
    stats["matched_rate"] = (
        stats["matched_products"] / stats["total_products"] if stats["total_products"] else 0.0
    )

    # 时间画像
    stats["breakfast_ratio"] = 0.0
    stats["night_ratio"] = 0.0
    if stats["order_count"]:
        stats["breakfast_ratio"] = sum(
            c for h, c in stats["hours"].items() if 5 <= h < 10
        ) / stats["order_count"]
        stats["night_ratio"] = sum(
            c for h, c in stats["hours"].items() if h >= 22 or h < 4
        ) / stats["order_count"]

    stats["favorite_weekday"] = stats["weekday"].most_common(1)[0][0] if stats["weekday"] else "—"
    stats["favorite_hour"] = None
    if stats["hours"]:
        top_hour = stats["hours"].most_common(1)[0][0]
        stats["favorite_hour"] = f"{top_hour:02d}:00 - {top_hour:02d}:59"

    stats["weekday_series"] = [(d, stats["weekday"].get(d, 0)) for d in weekday_names]
    stats["weekday_max"] = max([v for _, v in stats["weekday_series"]] or [0])

    stats["tags"] = _personality(stats)
    return stats


def _personality(stats: dict) -> list[dict]:
    """按规则生成人格标签，最多三个。"""
    top_name = stats["products"][0][0] if stats["products"] else ""
    rules = [
        ("深夜麦门人", "22 点之后还在点单的人，麦门永远为你亮灯",
         stats["night_ratio"] >= 0.2),
        ("早餐战神", "早班麦当劳的常驻嘉宾，一天从热香饼开始",
         stats["breakfast_ratio"] >= 0.35),
        ("巨无霸信徒", "巨无霸是你和这个世界和解的方式",
         "巨无霸" in top_name),
        ("薯条原教旨主义者", "薯条必须现炸、必须趁热、必须加盐",
         "薯条" in top_name),
        ("沙发点单派", "能躺着吃就绝不站着吃，麦乐送是你最好的朋友",
         stats["order_count"] and stats["delivery_count"] / stats["order_count"] >= 0.5),
        ("卡路里精算师", "每一块钱都要花在刀刃上，客单价稳定得像财务报表",
         0 < stats["avg_amount"] <= 25),
        ("豪迈点单流派", "点单从不看价钱，看的是今天的胃口",
         stats["avg_amount"] >= 45),
        ("薅券大师", "券包比钱包还厚，麦麦省是你的第二本能",
         stats["coupon_count"] >= 10),
        ("全城打卡王", "你的足迹遍布这座城市每一家麦当劳",
         stats["store_count"] >= 8),
        ("月度常客", "一个月至少来几趟，店员都快认识你了",
         stats["order_count"] >= 60),
    ]
    matched = [
        {"title": title, "desc": desc, "value": value}
        for title, desc, value in rules if value
    ]
    if not matched:
        matched = [{
            "title": "麦门新朋友",
            "desc": "故事才刚开始，下一次点单就会写进明年的报告里",
            "value": True,
        }]
    return matched[:3]


# ====================================================================== 渲染

TEMPLATE = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>
  :root {
    --bg:#F5F4F1; --card:#FFFFFF; --line:#E7E5E0; --ink:#1E1E1C;
    --ink-2:#5C5B56; --ink-3:#8E8D87; --red:#DA291C; --yellow:#FFC72C;
    --red-soft:#FDEDEB; --yellow-soft:#FFF8E3;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; padding:32px 16px 56px; background:var(--bg); color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
                "Hiragino Sans GB","Microsoft YaHei",sans-serif;
    font-size:14px; line-height:1.65; -webkit-font-smoothing:antialiased;
  }
  .page { max-width:760px; margin:0 auto; }
  .card {
    background:var(--card); border:1px solid var(--line); border-radius:16px;
    padding:24px; margin-bottom:16px;
  }
  .hero { text-align:center; padding:36px 24px; }
  .hero .kicker {
    display:inline-block; font-size:12px; letter-spacing:.16em; color:var(--red);
    border:1px solid var(--red-soft); background:var(--red-soft);
    border-radius:999px; padding:3px 12px; margin-bottom:14px;
  }
  .hero h1 { margin:0 0 8px; font-size:30px; font-weight:600; letter-spacing:.02em; }
  .hero .year { color:var(--red); }
  .hero p { margin:0; color:var(--ink-3); font-size:13px; }
  h2 { margin:0 0 16px; font-size:15px; font-weight:600; }
  h2 .sub { float:right; font-weight:400; color:var(--ink-3); font-size:12px; }
  .tags { display:flex; flex-direction:column; gap:10px; }
  .tag {
    display:flex; gap:14px; align-items:flex-start;
    border:1px solid var(--line); border-left:3px solid var(--red);
    border-radius:12px; padding:14px 16px; background:var(--yellow-soft);
  }
  .tag:nth-child(n+2) { border-left-color:var(--yellow); background:#FCFCFA; }
  .tag .t { font-size:16px; font-weight:600; margin-bottom:2px; }
  .tag .d { color:var(--ink-2); font-size:13px; }
  .kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
  .kpi { border:1px solid var(--line); border-radius:12px; padding:16px 14px; }
  .kpi .v { font-size:22px; font-weight:600; letter-spacing:-.01em; }
  .kpi .v small { font-size:12px; font-weight:400; color:var(--ink-3); margin-left:2px; }
  .kpi .l { color:var(--ink-3); font-size:12px; margin-top:4px; }
  .bar-row { display:flex; align-items:center; gap:12px; margin-bottom:10px; }
  .bar-row .name { flex:0 0 132px; font-size:13px; overflow:hidden;
                   text-overflow:ellipsis; white-space:nowrap; }
  .bar-track { flex:1; background:#F0EFEB; border-radius:6px; height:20px; overflow:hidden; }
  .bar-fill { height:100%; background:var(--red); border-radius:6px; }
  .bar-row:nth-child(2) .bar-fill { background:#E45A4E; }
  .bar-row:nth-child(3) .bar-fill { background:#EC867B; }
  .bar-row:nth-child(4) .bar-fill { background:#F2AFA7; }
  .bar-row:nth-child(5) .bar-fill { background:#F8D3CE; }
  .bar-row .num { flex:0 0 44px; text-align:right; font-size:13px; color:var(--ink-2); }
  .nutri { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }
  .nutri .box { border:1px solid var(--line); border-radius:12px; padding:16px; }
  .nutri .big { font-size:24px; font-weight:600; }
  .nutri .big span { font-size:13px; font-weight:400; color:var(--ink-3); }
  .nutri .convert { margin-top:6px; font-size:13px; color:var(--ink-2); }
  .nutri .convert b { color:var(--red); font-weight:600; }
  .week { display:flex; gap:8px; align-items:flex-end; height:104px; margin-bottom:8px; }
  .week .col { flex:1; display:flex; flex-direction:column;
               justify-content:flex-end; align-items:center; gap:6px; height:100%; }
  .week .col .bar { width:100%; background:var(--yellow); border-radius:6px 6px 0 0;
                    min-height:3px; }
  .week .col.peak .bar { background:var(--red); }
  .week .col .lab { font-size:11px; color:var(--ink-3); }
  .facts { display:flex; flex-wrap:wrap; gap:10px; }
  .fact { border:1px solid var(--line); border-radius:999px; padding:7px 14px;
          font-size:13px; color:var(--ink-2); }
  .fact b { color:var(--ink); font-weight:600; }
  .empty { text-align:center; color:var(--ink-2); padding:26px 12px; }
  .empty .big { font-size:17px; font-weight:600; color:var(--ink); margin-bottom:6px; }
  .empty code { background:#F0EFEB; border-radius:5px; padding:2px 6px;
                font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }
  footer { color:var(--ink-3); font-size:12px; text-align:center;
           line-height:1.75; padding:0 8px; }
  footer a { color:var(--ink-3); }
  @media (max-width:640px) {
    .kpis { grid-template-columns:repeat(2,1fr); }
    .nutri { grid-template-columns:1fr; }
    .hero h1 { font-size:24px; }
    .bar-row .name { flex-basis:96px; }
  }
  @media print {
    body { background:#fff; padding:0; }
    .card { break-inside:avoid; }
  }
</style>
</head>
<body>
<div class="page">

  <div class="card hero">
    <div class="kicker">麦门年度报告</div>
    <h1>你在麦当劳的 <span class="year">$year</span> 年</h1>
    <p>数据来自麦当劳 MCP · 生成于 $generated_at</p>
  </div>

$body

  <footer>
    本报告由「麦门年度报告」Skill 基于麦当劳 MCP 返回的本人账户数据生成。<br>
    本项目为麦当劳程序员创意开发大赛参赛作品，由参赛者独立开发，<b>非麦当劳官方产品</b>。<br>
    报告输出仅供参考，不构成医疗、营养或其他专业建议；餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。
  </footer>

</div>
</body>
</html>
""")


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def bar_rows(pairs: list[tuple[str, int]]) -> str:
    if not pairs:
        return '<p class="empty">暂无餐品记录</p>'
    top = max(v for _, v in pairs) or 1
    rows = []
    for name, count in pairs:
        width = max(count / top * 100, 4)
        rows.append(
            f'<div class="bar-row"><div class="name" title="{esc(name)}">{esc(name)}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div>'
            f'<div class="num">{count} 份</div></div>'
        )
    return "".join(rows)


def week_chart(series: list[tuple[str, int]], peak: str) -> str:
    top = max((v for _, v in series), default=0) or 1
    cols = []
    for day, count in series:
        height = max(count / top * 100, 3) if count else 2
        cls = "col peak" if day == peak and count else "col"
        cols.append(
            f'<div class="{cls}"><div class="bar" style="height:{height:.0f}%"></div>'
            f'<div class="lab">{esc(day)}</div></div>'
        )
    return f'<div class="week">{"".join(cols)}</div>'


def render(stats: dict) -> str:
    sections: list[str] = []

    if not stats["order_count"]:
        sections.append(
            '<div class="card"><h2>还没有找到你的麦门足迹</h2>'
            '<div class="empty"><div class="big">这一年的订单记录还是空的</div>'
            "可能的原因：这个麦当劳账号还没有历史订单，或者订单不在 MCP 提供的查询范围内。<br>"
            "先点一次单，再回来重新生成试试。<br><br>"
            "想直接看报告长什么样？运行 <code>python build_report.py --demo</code> "
            "可以用示例数据出一份演示报告。</div></div>"
        )
        return TEMPLATE.substitute(title=f"麦门年度报告 {stats['year']}",
                                   year=stats["year"],
                                   generated_at=esc(stats["generated_at"]),
                                   body="".join(sections))

    # 人格标签
    tags = "".join(
        f'<div class="tag"><div><div class="t">{esc(t["title"])}</div>'
        f'<div class="d">{esc(t["desc"])}</div></div></div>'
        for t in stats["tags"]
    )
    sections.append(f'<div class="card"><h2>你的麦门人格</h2><div class="tags">{tags}</div></div>')

    # KPI
    kpis = [
        (f'{stats["order_count"]}<small>笔</small>', "下单次数"),
        (f'¥{money(stats["total_amount"])}', "累计消费"),
        (f'¥{money(stats["avg_amount"])}', "平均客单价"),
        (f'{stats["store_count"]}<small>家</small>', "打卡门店"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="v">{v}</div><div class="l">{l}</div></div>'
        for v, l in kpis
    )
    sections.append(f'<div class="card"><h2>数字速览</h2><div class="kpis">{kpi_html}</div></div>')

    # 餐品榜
    sections.append(
        '<div class="card"><h2>你的麦门餐单'
        f'<span class="sub">共 {stats["product_total"]} 份餐品</span></h2>'
        f'{bar_rows(stats["products"])}</div>'
    )

    # 营养账单
    eq = stats["equiv"]
    if stats["kcal"] > 0:
        nutri = [
            (f'{stats["kcal"]:,.0f}<span> 千卡</span>', "累计摄入热量",
             f'相当于 <b>{eq["bigmac"]:.1f}</b> 个巨无霸的热量'),
            (f'{stats["protein"]:,.0f}<span> 克</span>', "蛋白质",
             f'相当于 <b>{eq["eggs"]:.0f}</b> 个鸡蛋'),
            (f'{eq["salt"]:.0f}<span> 克</span>', "折合食盐",
             f'钠摄入 {stats["sodium"]:,.0f} 毫克'),
            (f'{eq["km"]:.0f}<span> 公里</span>', "需要慢跑才消耗得掉",
             "按每公里 60 千卡估算"),
        ]
        boxes = "".join(
            f'<div class="box"><div class="big">{v}</div>'
            f'<div class="l" style="color:var(--ink-3);font-size:12px">{l}</div>'
            f'<div class="convert">{c}</div></div>'
            for v, l, c in nutri
        )
        note = (f'<span class="sub">营养匹配率 {stats["matched_rate"] * 100:.0f}%</span>')
        sections.append(
            f'<div class="card"><h2>营养账单{note}</h2>'
            f'<div class="nutri">{boxes}</div></div>'
        )

    # 时间画像
    facts = [
        f'最常光顾 <b>{esc(stats["top_store"]["name"]) if stats["top_store"] else "—"}</b>'
        + (f'（{stats["top_store"]["count"]} 次）' if stats["top_store"] else ""),
        f'最爱的星期是 <b>{esc(stats["favorite_weekday"])}</b>',
        f'最常下单的时段是 <b>{esc(stats["favorite_hour"] or "—")}</b>',
    ]
    if stats["order_count"]:
        delivery_ratio = stats["delivery_count"] / stats["order_count"] * 100
        facts.append(f'其中 <b>{delivery_ratio:.0f}%</b> 叫了麦乐送')
    sections.append(
        '<div class="card"><h2>你的麦门时间表</h2>'
        f'{week_chart(stats["weekday_series"], stats["favorite_weekday"])}'
        f'<div class="facts">{"".join(f"<div class=fact>{f}</div>" for f in facts)}</div>'
        "</div>"
    )

    # 积分与券
    perks = [
        (f'{stats["points_available"]:,.0f}', "可用积分"),
        (f'{stats["points_accumulative"]:,.0f}', "累计获得积分"),
        (f'{stats["points_expired"]:,.0f}', "已过期积分"),
        (f'{stats["coupon_count"]}', "券包里的券"),
    ]
    perk_html = "".join(
        f'<div class="kpi"><div class="v">{v}</div><div class="l">{l}</div></div>'
        for v, l in perks
    )
    prize_line = (f'积分抽奖中奖 <b>{stats["prize_count"]}</b> 次'
                  if stats["prize_count"] else "今年还没在积分抽奖里中过奖")
    sections.append(
        f'<div class="card"><h2>麦麦省战果</h2><div class="kpis">{perk_html}</div>'
        f'<div class="facts" style="margin-top:14px">'
        f'<div class="fact">{prize_line}</div>'
        f'<div class="fact">即将过期积分 <b>{stats["points_expiring"]:,.0f}</b></div>'
        "</div></div>"
    )

    return TEMPLATE.substitute(
        title=f"麦门年度报告 {stats['year']}",
        year=stats["year"],
        generated_at=esc(stats["generated_at"]),
        body="".join(sections),
    )


# ====================================================================== 入口

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="生成麦门年度报告")
    parser.add_argument("--demo", action="store_true", help="使用 sample/demo_data.json 生成演示报告")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR, help="原始数据目录")
    parser.add_argument("--out", type=Path, default=None, help="输出 HTML 路径")
    parser.add_argument("--open", dest="open_browser", action="store_true", help="生成后打开浏览器")
    args = parser.parse_args(argv)

    if args.demo:
        if not DEMO_PATH.exists():
            print(f"示例数据不存在：{DEMO_PATH}", file=sys.stderr)
            return 1
        raw = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
        default_out = OUTPUT_DIR / "麦门年度报告_示例.html"
    else:
        if not args.raw_dir.exists():
            print(f"还没采集数据。请先运行：python collect.py\n（找不到 {args.raw_dir}）",
                  file=sys.stderr)
            return 1
        raw = load_raw(args.raw_dir)
        default_out = OUTPUT_DIR / "麦门年度报告.html"

    stats = analyze(raw)
    html_text = render(stats)

    out_path = args.out or default_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_text, encoding="utf-8")

    print(f"订单 {stats['order_count']} 笔 · 消费 ¥{money(stats['total_amount'])}"
          f" · 客单价 ¥{money(stats['avg_amount'])} · 门店 {stats['store_count']} 家")
    if stats["kcal"]:
        print(f"累计 {stats['kcal']:,.0f} 千卡，营养匹配率 {stats['matched_rate'] * 100:.0f}%")
    print(f"报告已生成：{out_path}")

    if args.open_browser:
        webbrowser.open(out_path.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
