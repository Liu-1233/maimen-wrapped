---
name: maimen-wrapped
description: 生成「麦门年度报告」——基于麦当劳 MCP 的本人订单、积分、券包与营养数据，产出一张可截图分享的自包含 HTML 年度账单卡片。当用户想生成麦当劳年度报告、麦门账单、麦麦战报、查看自己在麦当劳的消费/热量统计，或提到 maimen-wrapped 时使用此技能。
agent_created: true
---

# 麦门年度报告（Maimen Wrapped）

把麦当劳 MCP 返回的本人账户数据，算成一份有人格、可截图分享的年度账单卡片。
核心卖点不是"省钱"，而是**社交货币**：热量换算成"相当于几个巨无霸"、钠换算成"几克盐"、
再配上一组麦门人格标签。

## 什么时候用

- 用户说"帮我生成麦当劳年度报告 / 麦门账单 / 麦麦战报 / 我一年吃了多少"
- 用户想看自己在麦当劳的消费统计、热量统计、积分与券包盘点
- 用户提到 `maimen-wrapped`

## 前置条件

麦当劳 MCP Token（在 https://open.mcd.cn/mcp 控制台申请），并已在 WorkBuddy
自定义连接器中启用 `mcd-mcp`。配置示例见仓库根目录 `mcp-config.example.json`。

未配置时，引导用户完成配置后重试；只做演示时可跳过采集，直接用 `--demo` 出示例报告。

## 工作流程

### 1. 采集数据

**优先方式：直接调用 MCP 工具**（Token 已在连接器里，无需环境变量）。逐个调用下表
工具，把返回的 `data` 部分分别落盘到项目的 `data/raw/<键名>.json`：

| 键名 | MCP Tool | 参数 | 内容 |
|---|---|---|---|
| `now_time` | `now-time-info` | — | 服务器时间，确定报告周期 |
| `orders` | `order-list` | — | 到店 / 外送历史订单 |
| `account` | `query-my-account` | — | 积分账户 |
| `coupons` | `query-my-coupons` | `page:"1", pageSize:"200"` | 卡包优惠券 |
| `prizes` | `query-my-prizes` | `pageNum:"1", pageSize:"50"` | 积分抽奖中奖记录 |
| `mall` | `mall-order-list` | `size:10` | 麦麦商城兑换订单 |
| `nutrition` | `list-nutrition-foods` | — | 160 款餐品营养库 |

注意：`page`/`pageSize`/`pageNum` 这类参数传**字符串**，`size` 传数字。

**备选方式：运行脚本采集**（适合在 WorkBuddy 之外复现）：

```bash
export MCD_MCP_TOKEN="你的Token"    # Windows CMD: set MCD_MCP_TOKEN=...
python scripts/collect.py
```

任一工具失败不要中断整体流程：跳过该项、继续其余采集，报告会对缺失项降级展示。

### 2. 渲染报告

```bash
python scripts/build_report.py            # 读 data/raw/，输出 data/麦门年度报告.html
python scripts/build_report.py --demo     # 用 sample/demo_data.json 出演示报告
```

脚本纯标准库、零依赖、不联网。生成后用 `present_files` 打开 HTML 给用户看。

### 3. 空数据处理

账号没有历史订单时，报告会渲染"还没有找到你的麦门足迹"空状态页。此时：

- 如实告知用户该账号暂无订单数据（新注册账号很常见）；
- 提议用 `--demo` 先看报告成品；
- 不要伪造数据冒充真实结果。

## 关键实现细节

- **营养库格式**：`list-nutrition-foods` 返回的 `data` 不是 JSON，而是
  `[160]{productName,energyKj,energyKcal,...}:` + 缩进数据行的自定义格式。
  解析器在 `scripts/nutrition.py`，不要自己临时写正则。
- **餐品名匹配**：订单里的餐品名与营养库名称不完全一致（如带"（中）"等规格后缀），
  `NutritionTable.match()` 已做去后缀 + 双向包含匹配；匹配不上的餐品不计入营养统计，
  报告会展示"营养匹配率"提示用户。
- **时间字段**：订单 `createTime` 可能是字符串或秒/毫秒时间戳，`parse_time()` 已兼容。
- **输出形态**：单个自包含 HTML，CSS 全部内联、无外链、无脚本。保持这个形态——
  用户拿它截图发朋友圈，任何外链或脚本都会破坏这个用途。

## 数据边界

- 只读取用户本人的麦当劳账户数据，不落库、不上传，全部留在本地 `data/` 目录；
- `data/`、`sample/demo_data.json` 中的演示数据为虚构，需明确告知用户；
- 报告输出不构成医疗或营养建议，页面底部已内置该免责声明，勿删。
