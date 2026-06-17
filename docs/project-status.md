# 项目状态总表 — 做了什么 / 没做什么

> 最后更新：2026-06-15
> 范围：`src/trading_agent/`（约 6500 行 Python）+ 配置 + 编排 + 入口 + 测试（288 passed）
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
| 回看校准（score 桶 vs 未来收益 / 权重校准） | 🟢 E1 机器已建（forward/benchmark returns + IC attribution + setup outcomes + Calibration tab，见 roadmap E1）；统计显著性待数据积累 |
| 数据可追溯（run_manifest / analytics.db） | ✅ 已加（B1–B4，见 roadmap B） |
| 只读可视化（Strategy Lab dashboard） | ✅ C1–C3 已加；侧边栏 + 8 Tab（策略对比含 F1 + Calibration），headless 渲染验证，像素级视觉仍待人工目测，见 roadmap C3 |
| Token 成本（DSA/Technical 预计算） | ✅ 已加（P4，见 roadmap D1） |
| 自成长平台（observe→propose→shadow→promote） | ✅ G-pre/G0–G9 全闭环（challenger 有隔离 paper 账本，G7 出真实 fill/drawdown/PnL；paper/shadow only，promote 仅人工，见 roadmap G/G9） |
| 自成长诊断/提议/shadow/推荐（growth 全命令树） | ✅ observe/propose/validate/experiments/shadow/evaluate/recommend/promote check 全部上线 |
| 量化价量因子层（非 AI alpha 腿） | ⬜ 规划中（H 阶段 H2，下一个代码任务；ChatGPT Phase 2，见 roadmap H） |
| AI signal 结构化 + 归因 / ablation | 🟡 component IC 已覆盖 dsa/tech/kronos/catalyst；AI schema 标准化 + ablation 待做（H3） |
| 调度自动化 | 🟡 交易生命周期已 cron 化（premarket/intraday/postmarket）；**分析/自成长命令仍手动**，夜间自动化批处理待做（roadmap I1） |
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
- **（roadmap A1）** `core/config.py` 暴露公开的 `load_env_files()`；premarket/intraday/postmarket
  三个 lifecycle 入口现在第一行就调用它，早于 `ALLOW_WEEKEND_RUN`/`ALLOW_OUTSIDE_MARKET_TEST`/
  `ALLOW_KILL_SWITCH_PAPER_TEST` 等任何 skip-gate 判断；只在 `runtime.env.local` 设置、未 export
  到 shell 的 override 现在对直接 `python -m trading_agent` 调用同样生效。
- **（roadmap A2）** `RuntimeConfig.effective_risk_tier` 在 `trading_mode != "paper"` 且解析到
  tier 4（`paper_max`，$100k/$400k）时抛出 `TierMisconfigurationError`，不再放行；该属性在
  `intraday.py`/`premarket.py`（`run_risk_overlay`）均无 try/except 包裹，异常会一路冒泡到进程崩溃。
  `doctor` 单独捕获该异常，打印 `FAIL-CLOSED: ...` 并把退出码改为 `2`（而不是让诊断命令本身崩溃）。
  paper 模式不受影响。
- **（roadmap B2）** 新增 `strategy/registry.py` + `src/config/strategy_registry.yaml`：`load_env_files()`
  在合并完 env 文件后，会用 `active_strategy` 条目回填 `SCORING_PROFILE`/`POLICY_PROFILE`/
  `RISK_TIER`/`PAPER_RISK_TIER`（仅填未设置的 key；shell export 和 env 文件永远优先）。
  `runtime.env` 不再硬编码这两个 tier 值——现在由 registry 的 `baseline_v1` 条目提供（数值不变）。
  `doctor` 新增 `--- Strategy ---` 段显示当前 `active_strategy`/`change_reason`。

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
- **（roadmap A3 已完成）** `candidates.py` 的 `selected[:20]`、`risk_overlay.py` 的三处 `[:8]` 已改读
  `scoring_profiles.yaml` 的 `max_scored_candidates` / `max_watchlist` / `max_tradable`，改配置即可调
  上限，不再需要改代码。

### 4. Market feed（`data/market_context.py`）

**已做**
- 增量清理：只删不在本次 run 里的 stale symbol 目录，不再每次全量 `rmtree`。
- 并发：`_process_one_symbol()` + `ThreadPoolExecutor(max_workers=MARKET_FEED_MAX_WORKERS=4)`，
  yfinance I/O-bound 并发收益大。
- `symbols=` 覆盖参数：可只跑 active watchlist。
- 失败容忍：单 symbol 失败记 `partial`，不拖垮整批。
- **（roadmap D2，部分完成）** 新增 `data/ohlcv_cache.py`：1w/1d 两个长周期 timeframe 跨 run-date 缓存到
  `runtime/cache/ohlcv/<symbol>/<timeframe>.json`，每天只拉短尾增量（1d 用 5 天窗口，1w 用 1 个月窗口）
  而不是全量 1y/3y；重叠 bar 收盘价偏差超 1% 时判定为 split/dividend 调整，整份缓存失效重建。
  `ENABLE_OHLCV_CACHE`（默认 1）控制开关，`doctor` 回显。1h/15m 不缓存。

**没做**
- `yf.download` 批量单请求未做（当前仍是每 symbol 并发单独请求；并发 + 跨日缓存已大幅缓解请求量，
  batch 拉取的 period 限制/响应 shape 差异比单独做缓存更复杂，留给以后需要时再评估）。

### 5. 信号层（`signals/`）

**已做**
- DSA 扫描（Codex，全 universe，theme/crowding/promote-demote-block 分类）。
- Kronos 本地预测（active watchlist），按历史窗口长度分组走 `KronosPredictor.predict_batch()`；
  batch 接口缺失或运行失败时回退到逐标的 `predict()`，整体生成失败时写
  `build_failed_kronos_payload` 并 fail-closed。
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
- **（roadmap C2）** `premarket_diagnostics.json` 新增 `theme_diagnostics`：watchlist/tradable 按
  `universe_meta.json` 的 `theme` 分组的集中度（count/pct）、dominant theme、speculative 主题占比；
  超过 `scoring_profiles.yaml` 里 `max_theme_concentration_pct`/`max_speculative_theme_pct` 时进
  `warnings`。没有 `universe_meta.json` 时只跳过告警，不产生误报。

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
- **（roadmap D4）** `PAPER_PARTIAL_FILL`（默认关）：quote 刚好打到 limit 时按 `PAPER_PARTIAL_FILL_
  MIN_RATIO`（默认 0.3）部分成交，超过 limit `PAPER_PARTIAL_FILL_THRESHOLD_BPS`（默认 20bps）以上
  全部成交，中间线性插值——确定性模型，不用随机数，方便测试可重复。未成交余量以同一个 order_id
  追加一条 `status="pending"` 的续接记录重新进入 `pending_paper_orders()`，下次 reconcile 自动尝试
  补齐。默认关闭时这条新逻辑完全不触发，9 个既有测试一字不改全部通过。

**没做**
- 没有盘中实时 reconcile 之外的撮合时序模型（如排队、价格穿越的精确撮合）。
- `replay/analysis.py`/`analytics.db` 还不认识 `filled_qty`/`partial_filled` 状态——部分成交后的
  余量目前在 fill rate 统计里会被计成"pending"且 notional 算 0，不是"部分成交"。这是 roadmap D4
  原文预告的已知缺口，按计划留给 E1 阶段处理。

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

### 13. 策略可追溯（`strategy/`）

**已做**
- **（roadmap B2）** `strategy/registry.py` + `src/config/strategy_registry.yaml`：策略版本登记
  （scoring/policy profile、paper/live risk tier、change_reason、parent）；`load_env_files()`
  自动用 `active_strategy` 回填对应 env 变量（仅填未设置的 key）。
- **（roadmap B1）** `strategy/manifest.py`：`build_run_manifest()` 在 premarket/intraday/postmarket
  三个入口都会被调用，把 `strategy_id`/`trading_mode`/`effective_risk_tier`/两个 profile 名/
  `active_watchlist_count`/`git_commit`/`config_hash`/`codex_model` 写进
  `runtime/state/runs/<run_date>/run_manifest.json`，供以后 analytics.db（B3）和 strategy compare
  （F1）引用。

- **（roadmap B3）** `analytics/` 包 + `python3 -m trading_agent analytics build`：把
  `runtime/state/runs/*` 下分散的 run_manifest/candidate_scores/risk_overlay/decisions/orders/
  equity_curve 汇总进 `runtime/analytics/analytics.db`（SQLite，6 张表）。每次 build 全量
  drop+recreate+重新 insert，天然幂等。`orders`/`decisions` 复用 `replay/analysis.py` 现成的
  解析/合并逻辑。
- **（roadmap B4）** `docs/strategy-changelog.md`：每个 registry 里的 strategy version 一条记录；
  `strategy/registry.py` 新增 `list_strategy_ids()`，配测试强制要求每个 strategy_id 在 changelog
  里有 `## {strategy_id}` 标题，而不是靠人工记得写。

**没做**
- registry 的 `watchlist` 字段目前只是记录，没有反向接线到 `parse_active_watchlist()`（仍只读
  `active_watchlist.txt`），切换策略不会切换 watchlist 文件本身。
- `analytics.db` 的 `candidates` 表没有 `trade_readiness_score`/`price_setup_score`——这两个分数
  目前只在 intraday policy 引擎里临时计算，没有持久化到任何文件，等以后需要才补。

### 14. Dashboard（`dashboard/`）

**已做（C1 → C3 v2）**
- **（C1）** `python3 -m trading_agent dashboard` 拉起 Streamlit；`queries.py` 纯函数层（sqlite3 查
  `analytics.db` + 少量直接读 state JSON），`streamlit` 是 `pyproject.toml` 可选依赖。
- **（C3 v2，2026-06-16）** 单页瀑布流 → **侧边栏 + 7 Tab**（Today / Candidates / Decisions / Paper /
  Strategy Comparison / Self-Growth / Themes）。新增 8 个只读查询（`strategy_comparison`/
  `champion_vs_challengers`/`equity_timeseries`/`blocked_reason_trend`/`candidates_with_rankings`/
  proposals/queue/theme），各有单测（query 层 17 个）。**策略对比 Tab** 覆盖 champion 版本横向对比
  （= F1）+ champion vs challenger（读 G7 `experiment_report.json`）。
- **首次渲染验证**：`test_app_smoke.py` 用 streamlit `AppTest` headless 跑整个 app（缺 streamlit 自动
  skip），断言 7 Tab 全部无异常渲染——这是 dashboard 第一次被自动化证明「能真正跑起来」。

**没做 / 注意**
- **像素级视觉/布局美观度仍未人工核实**：沙箱无法截屏，只验证了「能 headless 渲染无异常 + 查询正确」，
  没有人眼确认排版好不好看。使用前建议本地跑一次 `python3 -m trading_agent dashboard` 目测。
- 现仅 `baseline_v1` 一个 strategy version，⑤ 策略对比的「版本横向对比」要等切过第二个版本才有第二行
  数据（UI/查询已就位）；challenger 的 fill rate/drawdown、forward returns 仍待 G6 订单仿真 / E1。

### 15. 自成长平台（`growth/`，roadmap G-pre + G0–G8 全闭环）

**已做（全部 paper/shadow only、champion 零行为变化、promote 仅人工）**
- **（G-pre）** profile 按名解析（`load_scoring_profile/policy_profile(..., profile_name=)`，默认 `None`
  行为不变）+ 实验账本隔离 `build_experiment_paths`（challenger 产物根到 `experiments/<id>/`）。
- **（G0）** 安全边界：`growth_policy.json` + `policy.py`（`forbidden_mutations` 并集、只能扩不能削）+
  `validator.py`（`validate_mutation`/`validate_proposal` 失败即拒）。
- **（G1/G2）** observations + 模块 diagnoser 注册表，写 `growth_observations.json`，dashboard 只读
  Self-Growth Lab；CLI `growth observe`。
- **（G3/G4）** proposal 生成器（白名单内、过 validator、按 max_delta 夹紧）+ `proposal_review.py` 完整
  校验写 `*_validation.json`；CLI `growth propose` / `growth validate`。**只写文件、不启用。**
- **（G5）** experiment queue（`strategy_experiments.yaml` + `experiment_queue.py` 状态机）；CLI
  `growth experiments list/add/approve/reject/archive`。**approve 只到 active_shadow，断言不改
  active_strategy。**
- **（G6）** shadow runner：用纯函数 `build_risk_overlay`（challenger scoring override）+
  `generate_order_intent` 在隔离账本跑出 `shadow_decisions.jsonl`，已接入 intraday（best-effort）+ CLI
  `growth shadow`。champion `paper/*`/`decisions` 一字不变。
- **（G7）** evaluator：champion（replay）vs challenger（shadow 决策）并排指标 + `promotion_rules` 裁决，
  写 `experiment_report.json` + `promotion_recommendation.md`；CLI `growth evaluate` / `recommend`。
- **（G8）** promotion check：校验 + 生成 changelog/registry 草稿到 `promotion_drafts/`，CLI
  `growth promote check`。**从不改 `strategy_registry.yaml`（断言字节不变）。**
- **（E1/E2 数据前置）** intraday 六分量 + `trade_readiness_score`/`price_setup_score` 落
  `intraday_rankings.jsonl`，analytics 第 7 张表。
- 测试：`tests/trading_agent/growth/*`（profiles_by_name 3 / growth_policy 3 / validator 7 /
  observations 2 / diagnosers 3 / proposals 8 / proposal_validation 5 / experiment_queue 8 /
  shadow_runner 3 / evaluator 4 / promotion 5）+ CLI/dashboard/analytics/orchestration 各新增，全绿。

**红线（代码强制）**
- 自成长只**诊断 + 提议 + shadow + 推荐**，从不改 champion 交易参数、从不自动 promote、从不碰 review/live。
  永远禁止 mutation：`TRADING_MODE`/`RISK_TIER`/`PAPER_RISK_TIER`/`KILL_SWITCH`/MCP 审批/
  `place_equity_order`/`per_trade_risk_pct`/`max_daily_risk_pct`/`max_single_stock_weight`，validator
  一律 fail-closed。`approve` 不改 active_strategy、`promote check` 不改 registry，均有测试断言。

**没做 / 故意推后**
- G6 目前**只产决策流**：`shadow_orders.jsonl`/`shadow_equity_curve.jsonl` 的 paper 仿真（让 broker 写
  隔离账本）未做；因此 G7 的 challenger fill rate / drawdown 标 unavailable。
- E1 forward returns 未建（阻塞于 2–3 周 paper 数据），G7 把它当缺失指标 → 在它和 shadow 订单仿真到位前
  **永远不出 promote 推荐**。
- `analyzer_failure_rate` observation 留给后续 analyzers diagnoser。

---

## 三、按优先级批次的完成记录（commit 索引）

| 批次 | 内容 | 关键 commit |
|---|---|---|
| **P0** 正确性 | env 加载 + doctor；paper/live tier 解耦 + tier4；previous_close 修复；allowlist 兜底；删重复计分 + scoring 重复读 | `7b5d8d3` `9d53047` `f0cc272` `88a838b` `3011bad` `3b80d72` `f35b947` |
| **P1-A** 校准能力 | paper broker v2（滑点 + 日终撤单）；replay 本地部分（fill rate + blocked 分布） | `6754d41` `27cc225` |
| **P1-B** 选股池分层 | active_watchlist + universe_meta；Kronos/market_feed 按 active 跑 | `96a5a8f` |
| **P2** 策略质量 | price_setup_score 进排序（权重待校准） | `8134271` |
| **P3** 成本速度 | market_feed 并发；intraday quote 瘦身；subagents 10→3 | `ebd756a` |
| **P4** Token 优化 | technical_features.py + dsa_metrics.py 预计算；technical/DSA prompt 改读特征包/横截面表；env flag + doctor 回显 | `bd456f7` `1b1a079` |
| **P5-A1** 正确性 | env 加载提前到 skip-gate 判断之前（premarket/intraday/postmarket） | `7f69775` |
| **P5-A2** 正确性 | Tier 4 非 paper fail-closed（`TierMisconfigurationError` + doctor 退出码 2） | 见 git log |
| **P5-A3** 正确性 | 配置化魔数：`max_scored_candidates`/`max_watchlist`/`max_tradable` 进 `scoring_profiles.yaml` | 见 git log |
| **P5-B2** 数据可追溯 | `strategy_registry.yaml` + `strategy/registry.py`；接入 `load_env_files` | 见 git log |
| **P5-B1** 数据可追溯 | `strategy/manifest.py`：三个 lifecycle 入口都写 `run_manifest.json` | 见 git log |
| **P5-B3** 数据可追溯 | `analytics/` 包 + `analytics build` 子命令：6 张表汇总进 `analytics.db` | 见 git log |
| **P5-B4** 数据可追溯 | `docs/strategy-changelog.md` + `list_strategy_ids()` + 配套测试 | 见 git log |
| **P5-C2** 观测 | `premarket_diagnostics.json` 新增 theme/speculative 集中度诊断 + 可配置 cap | 见 git log |
| **P5-C1** 可视化 | `dashboard/` 包 + `dashboard` 子命令（Streamlit，视觉未人工验证） | 见 git log |
| **P5-D2** 工程优化 | `data/ohlcv_cache.py`：1w/1d 跨日缓存 + split/dividend 失效策略（batch 拉取未做） | 见 git log |
| **P5-D3** 工程优化 | Kronos `predict_batch()`：按窗口长度合批推理，batch 失败回退逐标的 | 见 git log |
| **P5-D4** 工程优化 | paper 部分成交模型：确定性 ratio + 余量续接重新进入 pending 队列 | 见 git log |
| **G-pre/G0–G2** 自成长 Phase 1 | profile 按名解析；`growth_policy.json` + validator；`growth observe` + observations；模块 diagnoser 注册表 + dashboard Self-Growth Lab（全只读、paper-safe） | 见 git log |
| **G3 + 数据前置** 自成长提议 | `growth/proposals.py` + `growth propose`（白名单、过 validator、只写文件）；intraday 分数落盘 `intraday_rankings.jsonl` + analytics 第 7 张表 | 见 git log |
| **G4–G8** 自成长全闭环 | proposal 完整校验（`growth validate`）→ 实验队列（`growth experiments`）→ shadow runner + 隔离账本（`growth shadow`，接入 intraday）→ evaluator（`growth evaluate/recommend`）→ 人工 promote check（`growth promote check`，不改 registry） | 见 git log |
| **C3** Dashboard v2 | 侧边栏 + 7 Tab；8 个只读查询（含 `strategy_comparison`=F1 + `champion_vs_challengers`）；`AppTest` headless 渲染验证 | 见 git log |
| **E1** 策略校准地基 | `replay/forward_returns`（keystone）+ benchmark + component IC attribution + setup outcomes + `calibration_report.{json,md}` + `analytics calibrate` + dashboard 第 8 Tab Calibration；全离线可测 | 见 git log |
| **E3** near-miss | `replay/near_miss.py`：候选按 score vs trade_threshold 分 cleared/near_miss/below 比后续收益（门槛是否太严），折进 Calibration tab | 见 git log |
| **G9** challenger 隔离账本 | `build_experiment_runtime_paths` + broker `paths_override`；shadow runner 跑 challenger 自己的 paper 账本；G7 出真实 fill/drawdown/PnL | 见 git log |
| **B5** watchlist resolver | `parse_active_watchlist` 从 `active_strategy.watchlist` 解析文件名（+override），切策略真能切 watchlist，回退兼容 | 见 git log |
| **TODO_FIX** technical 覆盖 | premarket 全天快照 + intraday merge；`run_symbol_research.sh` 单票输出改写到 `manual/<SYMBOL>/`（不再覆盖全局、可找到） | 见 git log |

---

## 四、明确未做的事（去向 roadmap）

按 roadmap 全局阶段归类（详细步骤/验收/依赖见 [`roadmap.md`](./roadmap.md)）：

- **A 正确性与安全闸**：A1/A2/A3 均已完成（见上方 P5-A1/P5-A2/P5-A3）。下一批是 B 阶段
  （数据可追溯基建：run_manifest / strategy_registry / analytics.db）。
- **B 数据可追溯基建（P0）**：✅ 全部完成（B1/B2/B3/B4，见上方 P5-B1~P5-B4 与第 13 节）。
  下一批是 C 阶段（theme 诊断 + 只读 dashboard）。
- **C 只读可视化与观测**：✅ 全部完成（C1/C2，见上方 P5-C1/P5-C2；C2 见第 6 节，C1 见第 14 节）。
  C1 的页面视觉效果尚未人工核实——见第 14 节"没做/注意"。
- **D 工程优化**：✅ 已完成 D1/D3/D4；D2 的跨日缓存已完成，`yf.download` 多 ticker batch 拉取未做。
  （DSA/Technical token 优化见 P4/D1；market_feed 跨日缓存见 P5-D2；Kronos batch 推理见 P5-D3；
  paper 部分成交见 P5-D4。）
- **E 数据驱动校准（阻塞 2–3 周 paper）**：forward/benchmark returns + entry-zone 命中率 +
  component attribution、评分/价格 setup 权重校准、near-miss tracking、bid/ask/spread 成交质量。
- **F 后期/故意推后**：strategy compare、review/live 真实下单接线、dashboard config editor。
- **G 自成长平台（paper/shadow only）**：growth_policy 安全边界 + 校验器、growth observations、模块
  diagnosers + dashboard Self-Growth Lab（G0–G2，已有详细实现计划
  [`superpowers/plans/2026-06-16-self-growth-platform-g0-g2.md`](./superpowers/plans/2026-06-16-self-growth-platform-g0-g2.md)）；
  proposal 生成/校验/实验队列（G3–G5）；shadow runner + evaluator + 人工 promote（G6–G8）。
  详见 roadmap G 阶段。**只提议、不自动改 champion，绝不自动升级 live。**
