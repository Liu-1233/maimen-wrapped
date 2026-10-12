# workbuddy.md · WorkBuddy 开发对话上下文

本项目由腾讯 **WorkBuddy** 智能体协助开发，本文件按大赛要求记录开发过程与对话上下文脉络，
用于核验 WorkBuddy 联动活动奖励条件。

## 开发环境

- 工具：WorkBuddy 桌面端（Agent 模式）
- 开发日期：2026-10-12
- 开发者：白七

## 开发过程

### 1. 赛题解读与选题

将麦当劳程序员创意开发大赛的官方仓库（README、`activityGuidelines.md`、
`CONTEST_DECLARATION.md`、`RANKING.md` 榜单快照）投喂给 WorkBuddy，要求逐条读取规则。

WorkBuddy 给出的关键判断：

- 排名唯一依据是 GitHub 公开 Star 数，前 100 名进榜即获奖；
- 抓取 2026-10-12 21:00 的榜单快照后测算：第 1 名 177 Star、第 10 名 38 Star、
  第 100 名附近约 5 Star；
- 榜单前 100 个项目中"省钱策略 / 热量计算 / 点单助手"类高度同质化，
  **没有任何一个项目做"个人消费年度报告"**；
- 结论：避开省钱红海，做"可晒的社交货币型产物"，用内容传播换 Star。

### 2. MCP 能力实测

由 WorkBuddy 直接以 HTTP 方式调用 `https://mcp.mcd.cn`：

- `initialize` 握手成功（`mcd-mcp v1.0.0`）；
- `tools/list` 返回 35 个工具；
- 实测 `now-time-info` / `query-my-account` / `order-list` / `campaign-calendar` /
  `list-nutrition-foods` / `query-my-coupons` / `mall-order-list` 的真实返回结构；
- **发现关键细节**：`list-nutrition-foods` 返回的 `data` 不是 JSON，
  而是 `[160]{productName,energyKj,energyKcal,...}:` + 缩进数据行的自定义格式，
  官方文档未给出解析器，需要自行实现 —— 这成了本项目的技术差异点。

### 3. 代码实现

WorkBuddy 生成了全部代码与文档（Python，仅标准库，零第三方依赖）：

| 文件 | 作用 |
|---|---|
| `scripts/mcd_client.py` | 麦当劳 MCP 零依赖客户端（握手 / tools 列表 / 工具调用 / SSE 与 JSON 双形态解析 / 401 与 429 错误提示） |
| `scripts/nutrition.py` | `[160]{...}:` 自定义格式解析器 + 餐品名模糊匹配（去规格后缀、双向包含） |
| `scripts/collect.py` | 7 个 MCP 工具的数据采集与落地，单工具失败不阻断整体 |
| `scripts/build_report.py` | 分析引擎（订单 × 营养库 × 时间画像 × 人格标签规则）+ 自包含 HTML 渲染 |
| `scripts/make_demo.py` | 虚构演示数据生成器（结构与真实 MCP 返回一致，营养表取真实数据） |
| `SKILL.md` | WorkBuddy Skill 定义 |
| `README.md` / `MCP_INTEGRATION.md` / `mcp-config.example.json` | 大赛要求的说明文件 |

### 4. 验证

- 真实 Token 下运行 `collect.py`：7 项采集全部成功，营养库解析出 **160 款餐品**；
- `build_report.py --demo`：61 笔虚构订单、消费 ¥2,844.50、营养匹配率 **97%**，
  热量 49,448 千卡 → 换算 96.4 个巨无霸 / 慢跑 824 公里；
- 用 Edge 无头模式对生成的 HTML 截图核验版式（`docs/preview.png`）；
- 开发过程中修复 2 处调用错误（`NutritionTable.parse_text` 为静态方法返回列表，
  两处误按实例属性 `.rows` 取值）。

## 与 WorkBuddy 的对话要点摘录

> 开发者：https://github.com/M-China/mcd-developer-innovation-challenge 想报名参加这个比赛你仔细阅读下规则

> WorkBuddy：这个比赛不比技术，比 Star。……抓取榜单快照后测算，当前第 100 名附近约 5 Star。
> 榜上 100 个项目里省钱策略、热量计算、点单助手已经卷成红海，但没有一个做"个人消费年度报告"。
> 这个方向天生带传播力——用户生成一张好看的年度账单卡片，会自己截图发朋友圈。

> 开发者：（提供麦当劳 MCP Token）

> WorkBuddy：Token 有效，服务已握手成功。……实测发现 `list-nutrition-foods` 返回的是
> 160 个餐品的自定义格式，这意味着可以做「订单履历 × 营养库 = 你一年吃掉了多少卡路里」，
> 这是省券类项目完全没碰的差异化点。

## 说明

- 本文件所述过程与结论均为开发当时的真实记录；
- 项目中不含任何真实 Token、密钥或他人个人信息。
