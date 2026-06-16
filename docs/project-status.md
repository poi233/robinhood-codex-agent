# 项目状态总表 — 做了什么 / 没做什么

> 最后更新：2026-06-15
> 范围：`src/trading_agent/`（约 6500 行 Python）+ 配置 + 编排 + 入口 + 测试（222 passed）
> 用途：**单一权威的"现状"文档**，按子系统逐块说明已实现与未实现。未来要做的事另见
> [`roadmap.md`](./roadmap.md)。
>
> 全局思路：**先在 paper 跑出「可信、可复现、可校准」的结果，再考虑 live。** universe 才 88 个，
> 系统能跑；卡「可信度」的是配置漂移、脏数据、缺校准数据。优先级因此是
> 「正确性 → 校准能力/分层 → 策略质量 → 成本速度」。

---

## 一、整体成熟度

| 维度 | 状态 |
|---|---|
| 核心交易引擎（price/sizing/sell/paper 链路） | ✅ 成型且完整 |
| 安全边界（execution_not_wired / KILL_SWITCH / fail-closed） | ✅ 扎实 |
| 配置一致性（shell 与 Python 入口一致） | ✅ 已统一（P0） |
| 数据干净度（previous_close 等脏数据） | ✅ 已修（P0） |
| paper 仿真真实度（滑点 / pending 生命周期） | ✅ 已加（P1） |
| 选股池分层（重活只跑 active watchlist） | ✅ 已加（P1） |
| 价格 setup 进排序 | ✅ 已加，权重待校准（P2） |
| 成本/速度优化（并发 / quote 瘦身 / subagent） | ✅ 已加（P3） |
| 回看分析（fill rate / blocked 分布） | ✅ 本地部分已加 |
| 回看校准（score 桶 vs 未来收益 / 权重校准） | ⏳ 阻塞于数据积累 |
| 数据可追溯（run_manifest / analytics.db） | ⬜ 未做（P0，见 roadmap B） |
| 只读可视化（Strategy Lab dashboard） | ⬜ 未做（见 roadmap C） |
| Token 成本（DSA/Technical 预计算） | ✅ 已加（P4，见 roadmap D1） |
| review/live 真实下单 | ⛔ 故意未接线 |

---

## 二、逐子系统现状

### 1. 配置与入口（`core/config.py`, `cli.py`）

**已做**
- `python -m trading_agent` 自己加载 `runtime.env` → `runtime.env.local`（local 覆盖 base，
  二者都不覆盖已 export 的 shell env）。cron 与直接 Python 调用生效配置一致。
- `RuntimeConfig` 含 `risk_tier`（live/review）与 `paper_risk_tier`（paper）两个字段，
  `effective_risk_tier` property 按 `TRADING_MODE` 分派。
- CLI 子命令：`premarket` / `intraday` / `postmarket` / `dsa` / `doctor` / `replay`。
- `doctor` 打印生效值：mode、KILL_SWITCH、两个 tier + 各自 notional caps、effective tier、
  Codex 配置、各信号层开关、paper 配置、通知开关。

**没做 / 注意**
- `doctor` 默认值字符串仍写 `'10'`（DSA/TECHNICAL subagents 旧默认），实际 runtime.env 已是 3；
  仅影响"env 完全缺失时"的回显，不影响实际运行（见 roadmap 小项）。

### 2. 风险分层（`src/config/risk_tiers.json`）

**已做**
- 5 档 tier（0–4）。新增 tier 4 `paper_max`（$100k 单 / $400k 日），故意拉高让
  `per_trade_risk_pct` 和组合权重上限成为真正约束。
- runtime.env：`RISK_TIER=3`（live），`PAPER_RISK_TIER=4`（paper）。
- `risk_overlay.py` 用 `min(tier_cap, sizing_buying_power)` 做上限。

**没做**
- tier 之间没有自动一致性校验（如 notional cap 与 per_trade_risk_pct 的关系），靠人工设定。

### 3. Universe / 选股池（`data/universe.py`, `config/*.txt`, `universe_meta.json`）

**已做**
- `universe.txt`：88 个全量扫描池。
- `active_watchlist.txt`：≤30 个高优先级（重活只跑这些）。
- `universe_meta.json`：88 个 symbol 的 tier/theme/liquidity 参考元数据。
- `parse_active_watchlist()`：读 active，缺失时回退全 universe。
- 接线：Kronos + market_feed 跑 active；DSA 仍扫全 universe。

**没做**
- `universe_meta.json` 目前是手动维护的参考，没有自动构建（如 ETF holdings 自动展开）。
- `candidates.py` 的 `selected[:20]`、`risk_overlay.py` 的 `[:8]` 仍是硬编码魔数，未配置化。

### 4. Market feed（`data/market_context.py`）

**已做**
- 增量清理：只删不在本次 run 里的 stale symbol 目录，不再每次全量 `rmtree`。
- 并发：`_process_one_symbol()` + `ThreadPoolExecutor(max_workers=MARKET_FEED_MAX_WORKERS=4)`，
  yfinance I/O-bound 并发收益大。
- `symbols=` 覆盖参数：可只跑 active watchlist。
- 失败容忍：单 symbol 失败记 `partial`，不拖垮整批。

**没做**
- 没有跨 run-date 的 OHLCV 缓存复用（每天仍重新拉同样的历史 bar）。
- 没有 `yf.download` 批量单请求（当前是每 symbol 并发单独请求；并发已大幅缓解，但非最优）。

### 5. 信号层（`signals/`）

**已做**
- DSA 扫描（Codex，全 universe，theme/crowding/promote-demote-block 分类）。
- Kronos 本地预测（active watchlist），失败时写 `build_failed_kronos_payload` 并 fail-closed。
- Technical research（Codex，active watchlist，可 fan-out 到 `TECHNICAL_MAX_SUBAGENTS` 子代理）。
- Technical fallback：market feed 不完整或 prompt 失败时写保守 watch-only 价格层。
- **Token 优化（P4）**：`planner/technical_features.py` 在跑 technical prompt 前，从已收集的
  market_feed OHLCV 纯 Python 算出 SMA/EMA/RSI/MACD/ATR/swing 高低点/趋势/形态标记/多周期一致性/
  相对强度，写 `TECHNICAL_FEATURES_PATH`；technical prompt 改读这份特征包而不是原始图表/OHLCV。
  `signals/dsa_metrics.py` 在跑 DSA prompt 前，对全 88 个 universe symbol 做一次批量 yfinance 下载，
  算出横截面表（return/相对强度/趋势/距高点/量能/ATR%/主题/流动性）+ 主题聚合 + market breadth，
  写 `DSA_METRICS_PATH`；DSA prompt 改读这份表，催化剂查询只针对 promote/reconsider 候选。
  两者都有 `ENABLE_*_PRECOMPUTE` 开关可秒回退；**输出 schema 不变**，scoring/risk_overlay 不受影响。

**没做**
- Kronos 仍是单标的串行推理（本地模型，受 active watchlist 降到 ≤30 缓解，但未做 batch 推理）。
- token 优化上线时 B1/B2（run_manifest/strategy_registry）尚未实现，没有按设计登记为新的
  strategy version，因此目前无法区分优化前后的 paper 样本（见 roadmap D1 遗留注意）。

### 6. 评分与风险覆盖（`planner/scoring.py`, `risk_overlay.py`, `data_status.py`, `premarket_diagnostics.py`）

**已做**
- 评分：DSA 0.25 / technical 0.30 / Kronos 0.15 / quote 0.10 / catalyst 0.20，按有效覆盖归一化。
- 技术动作归一化（strong_promote…block 映射到统一刻度，未知动作回退 observe + warning）。
- Catalyst 缺失时中性（50），不当 bearish。
- 性能修复：signal JSON 文件读取提到 dict comprehension 外（20 候选从 80 次读降到 4 次）。
- 风险覆盖：分离 `watchlist_candidates` 与 `tradable_candidates`；阈值来自 `scoring_profiles.yaml`。
- 诊断：`premarket_diagnostics.json` 输出分数分布、阈值、覆盖、未映射动作、warning 等。
- `scoring_profiles.yaml`：3 个 profile（aggressive_growth / balanced / conservative）。

**没做**
- 评分权重（0.25/0.30/…）仍是先验设定，未经回看数据校准。

### 7. 盘中策略引擎（`policy/`）

**已做**
- 排序（`candidate_selector.py`）：`trade_readiness_score` 六分量，权重合计 1.00，含
  **`price_setup_score`（0.15，P2 新增）**。
- `price_setup_score`（`technical.py:estimate_price_setup_score`）：排序时用实时 quote + watch
  levels 算 0-100（no-trade/chase→0，zone 外→20，breakout→60+RR，pullback→70+RR）。
- 定价（`price_policy.py`）：entry zone / breakout trigger / no-trade zone / chase 限制 /
  最低 reward:risk 全部硬校验。
- 定量（`sizing_policy.py`）：risk-budget 起步，按 single/daily/cash-buffer/单股·ETF·主题权重上限收口，
  再乘 score×market×research 乘数。
- 卖出（`sell.py`）：技术目标 / 失效位 / 风险减仓触发，分 partial-take-profit vs defensive-exit。
- 硬闸门（`risk.py`）：KILL_SWITCH、stale plan、stale/missing quote、execution_blocking、
  market_regime∈{no_trade,risk_off}。
- 低频控制：cooldown(buy/stop)、max_new_positions per day/week。
- `today_allowlist` 确定性兜底：final planner 写空时用 `risk_overlay.tradable_candidates`。
- 删除了 `trade_readiness_score` 里重复的 `candidate_total` 项。

**没做**
- `price_setup_score` 权重 0.15 是保守起点，**待 replay component attribution 校准**。
- 排序仍在完整定价之前（`price_setup_score` 是代理分量，非真实定价结果反哺）。

### 8. Paper broker（`paper/broker.py`）

**已做**
- 成交模型 `conservative`：买价≤limit 才成交，卖价≥limit 才成交，否则 pending。
- **滑点**（`PAPER_SLIPPAGE_BPS=10`）：买 `min(limit, ref*(1+slip))`，卖 `max(limit, ref*(1-slip))`，
  记账全用成交价。
- **pending 生命周期**：后续 intraday run 用新 quote reconcile pending；日终
  `PAPER_CANCEL_PENDING_AT_DAY_END=1` 撤未成交单。
- 账本：account.json / positions.json（加权均价）/ orders.jsonl / equity_curve.jsonl。
- daily_usage 只被成交单更新。

**没做**
- 没有部分成交（partial fill）模型，只有全成或不成。
- 没有盘中实时 reconcile 之外的撮合时序模型（如排队、价格穿越的精确撮合）。

### 9. 回看分析（`replay/analysis.py`）

**已做**
- `discover_run_dates()`：扫 run-date，支持 `--since/--until`。
- `collect_paper_orders()`：按 order_id 合并事件流（submission→pending_filled/day_end_cancel）取终态。
- `fill_rate_summary()`：filled/pending/canceled/rejected + 成交率 + notional + 分 symbol。
- `blocked_reason_summary()`：would-trade vs no-trade + reason 频次排名。
- `format_replay_report()` + `--output` JSON。

**没做（阻塞于数据积累）**
- score 桶 vs 1/3/5 日未来收益。
- entry-zone 命中率 / breakout 成功率。
- component attribution（各分量对实际收益的贡献）——P2 权重校准的前置依赖。

### 10. 编排（`orchestration/`）

**已做**
- premarket：分阶段 DAG，advisory 组并发，fail-closed，最后 normalize plan_state + 诊断 + archive。
- intraday：纯 Python，先 reconcile pending，再 sell-first then buy，写一条 decision，
  paper 成交发邮件。
- postmarket：paper day-end + 绩效汇总 + 中文报告 + Codex 复盘 prompt。
- 三个入口都用 `effective_risk_tier`。

**没做**
- intraday review/live 分支仍 `execution_not_wired`（故意）。

### 11. 数据 / quote（`data/live_quotes.py`）

**已做**
- 修复 `previous_close=price` 脏数据（改 `period="5d"` 取真实前收，用 `.values[-1]` 避免 FutureWarning）。
- intraday quote 瘦身：`_quote_symbols()` 去掉全 universe，只拉 watchlist+allowlist+持仓+挂单。
- 要求 live quote：缺失/过期则 block，不回退 snapshot。

**没做**
- live quote 仍是 yfinance（非交易所实时源）；paper 阶段可接受。

### 12. 其余

**已做**：通知（email）、合约校验（`contracts/`）、报告（`reporting/`）、运行历史日志、
仓库自带 skills 安装/校验、安全检查脚本、Kronos 可移植安装。

---

## 三、按优先级批次的完成记录（commit 索引）

| 批次 | 内容 | 关键 commit |
|---|---|---|
| **P0** 正确性 | env 加载 + doctor；paper/live tier 解耦 + tier4；previous_close 修复；allowlist 兜底；删重复计分 + scoring 重复读 | `7b5d8d3` `9d53047` `f0cc272` `88a838b` `3011bad` `3b80d72` `f35b947` |
| **P1-A** 校准能力 | paper broker v2（滑点 + 日终撤单）；replay 本地部分（fill rate + blocked 分布） | `6754d41` `27cc225` |
| **P1-B** 选股池分层 | active_watchlist + universe_meta；Kronos/market_feed 按 active 跑 | `96a5a8f` |
| **P2** 策略质量 | price_setup_score 进排序（权重待校准） | `8134271` |
| **P3** 成本速度 | market_feed 并发；intraday quote 瘦身；subagents 10→3 | `ebd756a` |
| **P4** Token 优化 | technical_features.py + dsa_metrics.py 预计算；technical/DSA prompt 改读特征包/横截面表；env flag + doctor 回显 | (本次未提交 commit hash 待补) |

---

## 四、明确未做的事（去向 roadmap）

按 roadmap 全局阶段归类（详细步骤/验收/依赖见 [`roadmap.md`](./roadmap.md)）：

- **A 正确性与安全闸**：env 加载早于 early gate；Tier 4 非 paper fail-closed；配置化魔数
  （`selected[:20]`、`[:8]`、doctor/runtime_block 默认值）。
- **B 数据可追溯基建（P0）**：run_manifest（每次 lifecycle run）、strategy_registry、
  analytics.db builder、strategy-changelog。
- **C 只读可视化与观测**：Strategy Lab dashboard（Streamlit 只读）、theme/speculative 集中度诊断。
- **D 工程优化**：market_feed 跨日缓存/batch、Kronos batch 推理、paper 部分成交模型。
  （DSA/Technical token 优化已完成，见上方 P4 与 roadmap D1。）
- **E 数据驱动校准（阻塞 2–3 周 paper）**：forward/benchmark returns + entry-zone 命中率 +
  component attribution、评分/价格 setup 权重校准、near-miss tracking、bid/ask/spread 成交质量。
- **F 后期/故意推后**：strategy compare、review/live 真实下单接线、dashboard config editor。
