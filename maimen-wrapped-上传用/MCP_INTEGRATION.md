# MCP_INTEGRATION · 麦当劳 MCP 集成说明

本项目**真实调用**麦当劳 MCP Server（`https://mcp.mcd.cn`，Streamable HTTP + Bearer Token）。
所有数据均来自 MCP 工具返回值，项目本身不接入任何其他数据源、不做任何模拟兜底。

## 一、使用的 MCP Server

| 项 | 值 |
|---|---|
| Server | 麦当劳中国 MCP Server |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP |
| 鉴权 | 请求头 `Authorization: Bearer <MCP_TOKEN>` |
| Token 申请 | https://open.mcd.cn/mcp 控制台 → 激活 |
| 限流 | 600 次 / 分钟（本项目单次报告调用 7 次，远低于限额） |

## 二、使用的 Tool（7 个）

| # | Tool | 入参 | 在本项目中的作用 |
|---|---|---|---|
| 1 | `now-time-info` | — | 取服务器时间，确定报告所属年份与生成时间戳 |
| 2 | `order-list` | — | 核心数据源。取到店 / 外送历史订单：订单数、金额（`realTotalAmount`）、门店（`storeName`）、就餐方式（`orderType`）、下单时间（`createTime`）、商品明细（`orderProductList`） |
| 3 | `query-my-account` | — | 积分账户：可用 / 累计 / 已过期 / 本月将过期积分 |
| 4 | `query-my-coupons` | `page:"1"`, `pageSize:"200"` | 卡包优惠券列表，用于"薅券大师"标签与券包统计 |
| 5 | `query-my-prizes` | `pageNum:"1"`, `pageSize:"50"` | 积分抽奖中奖记录，用于"麦麦省战果"板块 |
| 6 | `mall-order-list` | `size:10` | 麦麦商城兑换订单，补充积分消耗去向 |
| 7 | `list-nutrition-foods` | — | 160 款餐品营养库，把订单商品映射成热量 / 蛋白质 / 钠摄入 |

> ⚠️ `query-my-coupons` / `query-my-prizes` 的分页参数须传**字符串**，`mall-order-list` 的 `size` 传数字，否则会参数校验失败。

## 三、调用流程

```
用户发起「生成我的麦门年度报告」
        │
        ▼
[1] now-time-info ────────────► 报告周期 / 生成时间
        │
        ▼
[2..6] order-list / query-my-account / query-my-coupons
       / query-my-prizes / mall-order-list
        │                         全部写入 data/raw/*.json
        ▼
[7] list-nutrition-foods ─────► data/raw/nutrition.txt + nutrition.json
        │                        （自定义 [160]{...}: 格式，scripts/nutrition.py 解析）
        ▼
scripts/build_report.py（纯本地，不联网）
        │   · 订单 × 营养库 匹配 → 热量 / 蛋白质 / 钠 汇总
        │   · 下单时间 → 星期 / 时段画像
        │   · 规则引擎 → 麦门人格标签
        ▼
data/麦门年度报告.html  （单文件、无外链、无脚本，供截图分享）
```

两种调用形态：

- **WorkBuddy 内**：直接由智能体调用 MCP 工具（Token 在自定义连接器中，不落盘到项目）；
- **WorkBuddy 外**：`scripts/mcd_client.py` 提供零依赖标准库客户端，
  `export MCD_MCP_TOKEN=... && python scripts/collect.py` 即可复现同样的采集结果。

## 四、业务价值

麦当劳 MCP 现有工具偏"交易链路"（点餐、领券、下单、兑换）。本项目把其中的
**数据型工具**（历史订单 + 积分账户 + 券包 + 营养库）组合成一条原本不存在的链路：

1. **把交易数据变成身份表达**——"薯条原教旨主义者""深夜麦门人"这类标签，
   让用户的消费记录变成可以晒的社交内容，而不是一条待办；
2. **把营养库变成可感的换算**——49,448 千卡没有体感，
   "相当于 96 个巨无霸""需要慢跑 824 公里"有体感；
3. **给 MCP 生态补一个纯只读、零风险的应用样板**——不点单、不支付、不动账户，
   只读本人数据，适合作为其他开发者接入麦当劳 MCP 的第一个练手项目。

## 五、数据与安全边界

- 只读取用户**本人**账户数据，不涉及他人信息；
- 所有数据仅落在本地 `data/` 目录，不联网上传、不落库；
- 仓库内不含任何真实 Token：`mcp-config.example.json` 仅使用环境变量占位符；
- `sample/demo_data.json` 为**虚构演示数据**，仅用于无 Token 时预览版式；
- 报告输出不构成医疗、营养建议，页面底部已内置该免责声明。
