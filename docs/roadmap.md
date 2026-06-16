# 未来工作清单（Roadmap）

> 最后更新：2026-06-15
> 配套：现状见 [`project-status.md`](./project-status.md)。本文件只列**未做**的事，按优先级与依赖
> 排序，每项给目标、具体步骤、涉及文件、验收标准、阻塞依赖。
>
> 原则：**不用魔数换魔数。** 任何新权重/阈值在固化前必须经回看数据校准。

---

## 优先级总览

| 级别 | 主题 | 阻塞状态 |
|---|---|---|
| **R1** | replay 数据驱动校准（score 桶 / attribution） | ⏳ 阻塞于数据积累（2–3 周 paper） |
| **R2** | P2 价格 setup 权重校准 | ⏳ 依赖 R1 |
| **R3** | 配置化魔数 + doctor 默认值修正 | ✅ 可立即做 |
| **R4** | market_feed 跨日缓存 / batch 拉取 | ✅ 可立即做 |
| **R5** | Kronos batch 推理 | ✅ 可立即做（需 Kronos 接口确认） |
| **R6** | paper 部分成交模型 | ✅ 可立即做 |
| **R7** | review/live 真实下单接线 | ⛔ 故意推后（需干净 review 日志 + 人工解锁） |

---

## R1 — replay 数据驱动校准（阻塞）

**目标**：把"凭感觉调参"变成"凭数据调参"。在已有的 `replay/analysis.py` 上补三块分析。

**阻塞依赖**：需要积累 **2–3 周（约 10–15 个交易日）** 的 paper run 数据，每天要有：
`candidate_scores.json`、paper `orders.jsonl`、`decisions.jsonl`。当前只有少量 run date，样本不足。

**具体步骤**（数据到位后）：
1. **score 桶 vs 未来收益**
   - 新增 `replay/forward_returns.py`：对每个历史 run date 的候选，用 yfinance 拉该 symbol 之后
     1/3/5 个交易日收益。
   - 按 `candidate_total` / `trade_readiness_score` 分桶（如 [0-50,50-70,70-85,85+]），算每桶平均
     未来收益 + 命中率。
   - 验收：输出每桶样本数、均值、胜率；桶单调性（高分桶收益应更高）可观测。
2. **entry-zone 命中率 / breakout 成功率**
   - 对 `setup_type=pullback/breakout` 的成交，统计后续是否触及 target_1 vs 触及 stop。
   - 验收：分 setup_type 输出 win/loss/未决计数。
3. **component attribution**
   - 对每个分量（dsa/technical/kronos/quote/catalyst/price_setup），算其得分与未来收益的相关性
     /信息系数（IC）。
   - 验收：输出每分量 IC 排名，作为 R2 权重调整依据。

**涉及文件**：`replay/analysis.py`（扩展）、新增 `replay/forward_returns.py`、`cli.py`（新 flag 如
`--forward-returns`）、对应测试。

**注意**：forward returns 需要联网 yfinance，测试用 mock；真实运行要处理停牌/数据缺口。

---

## R2 — P2 价格 setup 权重校准（依赖 R1）

**目标**：把 `trade_readiness_score` 里 `price_setup_score` 的权重 `0.15`（及其他分量权重）从
"保守先验"改成"数据校准值"。

**阻塞依赖**：R1 的 component attribution 输出。

**具体步骤**：
1. 用 R1 的 IC 排名，按贡献重新分配六个分量权重（仍约束合计 1.00）。
2. 同时校准 `estimate_price_setup_score` 的内部常数（20/60/70 基准、RR 奖励斜率）。
3. 在 `policy_profiles.json` / `scoring_profiles.yaml` 里把这些值配置化（见 R3），不再硬编码。
4. 更新 `test_price_sizing.py` 锁住新行为。

**验收**：新权重有 attribution 数据支撑；文档记录"为什么是这个值"；回看胜率/收益较旧权重不劣化。

**涉及文件**：`policy/candidate_selector.py`、`policy/technical.py`、配置文件、测试。

---

## R3 — 配置化魔数 + doctor 默认值修正（可立即做）

**目标**：消除散落的硬编码常数，统一到配置。

**具体项**：
1. `planner/candidates.py` 的 `selected[:20]` → `scoring_profiles.yaml` 的 `max_scored_candidates`。
2. `planner/risk_overlay.py` 的 `[:8]`（scored/watchlist/tradable）→ 配置项
   `max_watchlist` / `max_tradable`。
3. `cli.py` `_run_doctor` 里 `DSA_MAX_SUBAGENTS`/`TECHNICAL_MAX_SUBAGENTS` 回显默认值从 `'10'`
   改为 `'3'`，与 runtime.env 当前值一致。
4. `runtime_block.py` 同名默认值同步为 `'3'`。

**验收**：改配置即可调整这些上限，无需改代码；`doctor` 在 env 缺失时回显与 runtime.env 一致。

**涉及文件**：`planner/candidates.py`、`planner/risk_overlay.py`、`cli.py`、
`prompts/runtime_block.py`、`scoring_profiles.yaml`、测试。

**注意**：改 `[:8]` 这类要确认下游消费者（final planner prompt、policy 交集）对数量无隐含假设。

---

## R4 — market_feed 跨日缓存 / batch 拉取（可立即做）

**目标**：进一步降低 yfinance 调用量与延迟（并发已做，缓存与 batch 是下一步）。

**具体步骤**：
1. **跨日缓存**：长周期 bar（1w/1d）跨 run-date 基本不变，只需追加最新 bar。可缓存到
   `runtime/cache/ohlcv/<symbol>/<timeframe>.json`，每天只拉增量。
2. **batch 拉取**：考虑用 `yf.download(tickers=[...], group_by='ticker')` 单请求多标的，替代
   per-symbol 并发请求（注意 1h/15m 的 period 限制与对齐）。

**验收**：同样数据下 yfinance 请求次数显著下降；data_status 仍准确反映 ok/partial/failed。

**涉及文件**：`data/market_context.py`、可能新增 `data/ohlcv_cache.py`、测试。

**注意**：缓存要有失效策略（如 split/dividend 调整后失效）；`auto_adjust=False` 下要小心复权差异。

---

## R5 — Kronos batch 推理（可立即做，需接口确认）

**目标**：Kronos 本地推理是 premarket 最慢的一环之一。当前 active watchlist≤30 已缓解，但仍是
逐标的串行。

**具体步骤**：
1. 确认 `kronos_generate_signals.py` / 上游 Kronos 是否支持 batch 输入（多标的一次前向）。
2. 若支持，改 `signals/kronos.py` 的 live payload 构建走 batch。
3. 若不支持，评估用进程池并行多个推理（注意显存/CPU）。

**验收**：active watchlist 全量 Kronos 推理时间下降；signal 输出与逐标的一致。

**涉及文件**：`signals/kronos.py`、`src/scripts/kronos/kronos_generate_signals.py`、测试（mock）。

---

## R6 — paper 部分成交模型（可立即做）

**目标**：当前 paper 只有"全成或不成"。加部分成交让仿真更真实。

**具体步骤**：
1. 在 `paper/broker.py` 引入 `PAPER_PARTIAL_FILL`（默认关）：当 quote 在 limit 附近时按某概率/
   比例部分成交。
2. orders.jsonl 记录 filled_qty < quantity，剩余转 pending。
3. reconcile 时累积部分成交。

**验收**：部分成交路径有测试覆盖；daily_usage/positions 记账正确；默认关闭时行为不变。

**涉及文件**：`paper/broker.py`、`test_broker.py`、`runtime.env`（新 flag）。

**注意**：部分成交会让 fill rate 统计语义变化，R1 的 replay 要相应处理。

---

## R7 — review / live 真实下单接线（故意推后）

**目标**：把 review/live 从 `execution_not_wired` 接到真实 Robinhood MCP。

**前置条件（硬性）**：
- replay 显示 paper 成交率/胜率/blocked 分布合理。
- 至少若干周 paper 日志"无聊且正确"。
- review 路径先证明只 review 不下单。
- 人工显式移除 `KILL_SWITCH`，人工设 `RISK_TIER`（绝不让 Codex 改）。

**具体步骤（分阶段）**：
1. **review 模式**：intraday 在 `TRADING_MODE=review` 时调用 `review_equity_order`（只审单不下单），
   把 review 结果写 decisions/orders 审计日志。验证从不触发 `place_equity_order`。
2. **live tier 0**：仅在 review 日志干净后，接 `place_equity_order`，从 tier 0（$10/$25）起。
3. 每个阶段都要有 fail-closed 测试与回滚开关。

**验收**：review 模式可证明非下单；live tier 0 单笔受 $10 cap 严格约束；任何异常 fail-closed。

**涉及文件**：`orchestration/intraday.py`、`policy/engine.py`、`.codex/config.toml`（MCP 审批）、
新增测试。

**注意**：这是整个项目风险最高的改动。MCP 审批策略、KILL_SWITCH、tier 上限三道闸必须同时在位。

---

## 立即可做的建议顺序

数据还没积累够之前（R1/R2 阻塞），可先做不依赖数据的工程项：

1. **R3**（配置化魔数）— 低风险、清理债务。
2. **R4**（market_feed 缓存）或 **R6**（部分成交）— 看哪个对当前 paper 观察更有用。
3. 持续每天跑 paper，积累 R1 所需数据。
4. 2–3 周后回到 **R1 → R2**，用真实数据校准。
5. review/live（**R7**）只在以上都稳定后，由人工主导推进。
