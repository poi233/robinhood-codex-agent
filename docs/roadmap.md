# 未来工作清单（Roadmap · 全局合并版）

> 最后更新：2026-06-15
> 配套：现状见 [`project-status.md`](./project-status.md)；token 优化详细设计见
> [`design-prompt-token-optimization.md`](./design-prompt-token-optimization.md)。
>
> 本文件已合并三处来源，去重后按全局优先级排序：
> 1. 旧 roadmap 的 R1–R7（校准 / 配置化 / 性能 / 部分成交 / live 接线）。
> 2. `design-prompt-token-optimization.md`（DSA / Technical 两层 token 优化，已成设计，未进 roadmap）。
> 3. `robinhood_codex_agent_strategy_lab_plan`（**Strategy Lab / Dashboard** 新方向 + 若干正确性/观测项）。
>
> 每项给：目标、阻塞依赖、具体步骤、涉及文件、验收标准。
>
> **三条贯穿原则**
> - **不用魔数换魔数**：任何新权重/阈值在固化前必须经回看数据校准。
> - **可追溯优先**：先有 `run_manifest` + `analytics.db`，再做任何会改变行为的改动（token 优化、权重校准
>   都应记为一个**新的 strategy version**），否则积累的 paper 数据无法横向对比。
> - **paper-only 安全**：review/live 继续不接线，dashboard 第一版只读、不可改交易参数。

---

## 全局优先级总览

| 阶段 | 项 | 主题 | 来源 | 状态 / 阻塞 |
|---|---|---|---|---|
| **A 立即做 · 正确性与安全闸** | A1 | env 加载早于 early gate | docx | ✅ **已完成**（2026-06-15） |
| | A2 | Tier 4 非 paper → fail-closed | docx | ✅ **已完成**（2026-06-15） |
| | A3 | 配置化魔数 + doctor/runtime_block 默认值 | 旧 R3 + docx | ✅ **已完成**（2026-06-15） |
| **B 数据可追溯基建（P0）** | B1 | run_manifest（每次 lifecycle run） | docx | ✅ **已完成**（2026-06-15） |
| | B2 | strategy_registry + registry.py | docx | ✅ **已完成**（2026-06-15） |
| | B3 | analytics DB builder（analytics.db） | docx | ✅ **已完成**（2026-06-15） |
| | B4 | strategy-changelog.md | docx | ✅ 可立即做（文档） |
| **C 只读可视化与观测** | C1 | Dashboard MVP（Streamlit 只读） | docx | 依赖 B3 |
| | C2 | theme exposure / speculative cap 诊断 | docx | ✅ 可立即做 |
| **D 工程优化 · 不阻塞** | D1 | DSA/Technical token 优化 | design doc | ✅ **已完成**（2026-06-15，见下方实现记录） |
| | D2 | market_feed 跨日缓存 / batch | 旧 R4 | ✅ 可立即做 |
| | D3 | Kronos batch 推理 | 旧 R5 | ✅ 可立即做（需接口确认） |
| | D4 | paper 部分成交模型 | 旧 R6 + docx P3 | ✅ 可立即做 |
| **E 数据驱动校准** | E1 | replay 校准：forward/benchmark returns + 命中率 + attribution | 旧 R1 + docx P1 | ⏳ 阻塞于 2–3 周 paper 数据 |
| | E2 | 评分 / 价格 setup 权重校准 | 旧 R2 | ⏳ 依赖 E1 |
| | E3 | near-miss tracking | docx P2 | ⏳ 建议随数据建设 |
| | E4 | bid/ask/spread 成交质量 | docx P2 | 可选（paper 阶段弱依赖） |
| **F 后期 / 故意推后** | F1 | strategy compare | docx | 依赖 B1+B2+多 strategy version |
| | F2 | review/live 真实下单接线 | 旧 R7 | ⛔ 故意推后（人工解锁） |
| | F3 | config editor（dashboard 可编辑参数） | docx | ⛔ 最后做 |

> **新旧编号对照**：R1→E1（增 benchmark returns）、R2→E2、R3→A3、R4→D2、R5→D3、R6→D4、R7→F2；
> token 优化设计→D1；docx 的 run_manifest→B1、registry→B2、analytics.db→B3、changelog→B4、
> dashboard→C1、theme 诊断→C2、forward/benchmark/attribution→E1、near-miss→E3、bid/ask/spread→E4、
> strategy compare→F1、config editor→F3。

---

## 立即可做的建议顺序（无数据依赖期）

数据校准（E 阶段）阻塞于 2–3 周 paper 积累，期间按下面顺序推进；越靠前越「时间敏感或解锁后续」：

1. **A1 / A2 / A3** — 正确性与安全闸，低风险、低成本，先清掉。
2. **B1 → B3** — 数据可追溯基建。**越早越好**：每多跑一天没有 manifest/analytics 的 paper，
   就多一天难以回溯对比的数据。B2 registry 与 B1 并行（manifest 要引用 strategy_id）。
3. **C2 / C1** — 先补 theme 诊断（低成本观测），再做只读 dashboard（看懂每天为什么交易/不交易）。
4. **D1 / D2 / D4** — 工程优化挑对当前观察最有用的做；D1 token 优化建议在 B1/B2 之后，作为新
   strategy version 上线，避免污染正在积累的对比样本。
5. 持续每天跑 paper，积累 E1 所需数据。
6. 2–3 周后回到 **E1 → E2**，用真实数据校准；其间补 **E3 / E4**。
7. **F1 / F2 / F3** 只在以上稳定后，由人工主导推进。

---

# A 阶段 · 正确性与安全闸（立即做）

## A1 — env 加载早于 early gate — ✅ 已完成（2026-06-15）

**目标**：确保 `runtime.env` / `runtime.env.local` 在任何 premarket/intraday/postmarket 的 skip-gate
判断**之前**加载。当前部分 `ALLOW_*` 判定发生在 `load_runtime_config` 之前，Python 直跑时
`runtime.env.local` 里的 `ALLOW_WEEKEND_RUN`、`ALLOW_OUTSIDE_MARKET_TEST` 可能不生效。

**实现记录**：
1. ✅ `core/config.py` 把原来的私有 `_load_env_files` 改成公开的 `load_env_files(agent_root)`，
   `load_runtime_config()` 内部仍调用它（保持向后兼容）。
2. ✅ `orchestration/premarket.py` / `intraday.py` / `postmarket.py` 的三个 lifecycle 入口函数，
   现在第一行就调用 `load_env_files(agent_root)`，在 `_is_weekday_pt()` / `_is_intraday_window_pt()` /
   `KILL_SWITCH` 等任何 gate 判断之前完成。`postmarket.py` 里 `build_runtime_paths()` 也顺带挪到
   gate 检查之后，避免同一个排序问题影响路径覆盖。
3. ✅ 测试：`tests/trading_agent/core/test_runtime.py` 三个 `load_env_files` 单测（local 覆盖 base、
   shell export 优先、文件缺失时静默跳过）+ 每个 lifecycle 各 2 个测试（仅在 `runtime.env.local`
   写入 `ALLOW_WEEKEND_RUN=1`、不触碰 `os.environ`，验证周末 gate 被正确放行；以及没有该 override
   时仍正确跳过）。

**涉及文件**：`core/config.py`、`orchestration/premarket.py`、`orchestration/intraday.py`、
`orchestration/postmarket.py`、三个对应测试文件、`tests/trading_agent/core/test_runtime.py`。

**验收**：周末/盘外用 `runtime.env.local` 开关可正确放行；测试覆盖两个 flag。✅ 231 测试通过。

---

## A2 — Tier 4 非 paper → fail-closed — ✅ 已完成（2026-06-15）

**目标**：`RISK_TIER=4`（paper_max，$100k 单 / $400k 日）若被误用到 live/review，会拿到 paper 级 caps，
是真实资金风险。

**实现记录**：
- `core/config.py` 新增 `TierMisconfigurationError(RuntimeError)` 和常量 `PAPER_ONLY_RISK_TIER = 4`；
  `RuntimeConfig.effective_risk_tier` 属性在 `trading_mode != "paper" and risk_tier == 4` 时直接抛出该异常，
  不返回任何 tier 值。
- 确认了异常传播路径：`effective_risk_tier` 在 `intraday.py`、`premarket.py`（`run_risk_overlay` 闭包，非
  advisory 阶段，不被 `_run_advisory` 吞掉）两处被直接访问、无 try/except 包裹，异常会一路冒泡到
  `run_intraday_pipeline` / `run_premarket_pipeline` 顶层，再到 `cli.py` 的 `main()`，最终让进程崩溃退出
  ——符合"抛错或强制 block，绝不放行"的要求。
- `cli.py` 的 `_run_doctor()` 是例外：作为只读诊断工具，捕获 `TierMisconfigurationError` 后不让整个命令崩溃，
  而是把对应行替换为 `FAIL-CLOSED: ...` 提示文本，并将退出码改为 `2`（而不是 `0`），同样不会"放行"，
  只是给出更友好的诊断输出。
- paper 模式不受影响：`effective_risk_tier` 在 `trading_mode == "paper"` 时跳过 guard，照常返回
  `paper_risk_tier`。

**涉及文件**：`core/config.py`、`cli.py`、`tests/trading_agent/core/test_runtime.py`、`tests/trading_agent/test_cli.py`、
`tests/trading_agent/orchestration/test_intraday_policy_integration.py`。

**验收**：✅ `TRADING_MODE` 非 paper 且 tier=4 时进程 fail-closed（`intraday`/`premarket` 抛异常崩溃，
`doctor` 退出码 2 并打印 FAIL-CLOSED）；paper 模式不受影响。238 测试通过（+7 新增）。

---

## A3 — 配置化魔数 + doctor/runtime_block 默认值（旧 R3） — ✅ 已完成（2026-06-15）

**目标**：消除散落硬编码常数，统一到配置；修正 doctor/runtime_block 回显默认值。

**实现记录**：
- 项 3/4（`DSA_MAX_SUBAGENTS`/`TECHNICAL_MAX_SUBAGENTS` 回显默认值）在更早的 P3 commit（`ebd756a`，
  subagents 10→3）里已经同步改成 `'3'`，`cli.py`/`prompts/runtime_block.py`/`runtime.env` 三处一致，
  本次确认后无需再改。
- `src/config/scoring_profiles.yaml` 新增三个顶层（非 per-profile）配置项：`max_scored_candidates: 20`、
  `max_watchlist: 8`、`max_tradable: 8`。`planner/scoring_profiles.py` 的极简 YAML 解析器新增对顶层
  scalar key（非 `default_profile:`/`profiles:`）的通用解析；`DEFAULT_SCORING_PROFILE`、
  `load_scoring_profile()` 返回值都带上这三个字段（无配置文件时回退默认值）。
- `planner/candidates.py` 的 `selected[:20]` → `selected[:max_scored_candidates]`，从
  `load_scoring_profile(paths.config_dir)` 读取。
- `planner/risk_overlay.py` 的三处 `[:8]`（`scored_candidates`/`watchlist_candidates` 用
  `max_watchlist`；`tradable_candidates` 用 `max_tradable`）改为读取已经存在的 `scoring_profile`
  参数（`build_risk_overlay_from_paths` 早已加载它，调用点无需改动）。

**涉及文件**：`planner/candidates.py`、`planner/risk_overlay.py`、`planner/scoring_profiles.py`、
`scoring_profiles.yaml`、`tests/trading_agent/planner/test_candidates.py`（新建）、
`test_scoring_profiles.py`、`test_risk_overlay.py`。

**验收**：✅ 改 `scoring_profiles.yaml` 即可调上限，无需改代码（已用临时配置文件测试验证）；
`doctor`/`runtime_block` 默认值与 runtime.env 当前值一致（确认未漂移）。242 测试通过（+4 新增）。

---

# B 阶段 · 数据可追溯基建（P0，边跑 paper 边建）

> 这一阶段是 Strategy Lab 的地基。目标：让每次运行的「用了哪个策略版本 / 哪个 commit / 哪份配置」
> 可追溯，让分散的 JSON/JSONL 可查询。**没有它，后续 dashboard、strategy compare、可信校准都无从谈起。**

## B1 — run_manifest（每次 lifecycle run） — ✅ 已完成（2026-06-15）

**目标**：每次 premarket / intraday / postmarket 都落一份 `run_manifest.json`，记录当时的策略版本、
git commit、config hash、profiles、风险层、model，保证任何结果可回溯。

**实现记录**：
- 新增 `src/trading_agent/strategy/manifest.py`：`build_run_manifest(agent_root, run_date)` 聚合
  `load_runtime_config`、`load_active_strategy`（B2）、`load_scoring_profile`、`load_policy_profile`、
  `parse_active_watchlist`，写 `runtime/state/runs/<run_date>/run_manifest.json`（覆盖写，最近一次
  调用的入口决定该 run-date 的最新状态）。
- 字段：`run_date`、`strategy_id`、`trading_mode`、`effective_risk_tier`、`scoring_profile`、
  `policy_profile`、`active_watchlist_count`、`git_commit`（`git rev-parse HEAD`，非 git 仓库或失败时
  回退 `"unknown"`）、`config_hash`（trading_mode/两个 risk tier/strategy/scoring_profile/
  policy_profile 组合做 sha256，取前 12 位）、`codex_model`。
- 三个 lifecycle 入口（`premarket.py`/`intraday.py`/`postmarket.py`）都在 `load_runtime_config()`
  之后立即调用 `build_run_manifest()`——即周末/盘外/KILL_SWITCH 等早期 skip-gate 之后、真正开始业务
  逻辑之前。`active_watchlist_count` 用了一个本地容错包装（`universe.txt` 缺失时返回 0 而不是抛错），
  因为 manifest 是辅助性的可追溯元数据，不应该让缺一个文件就拖垮整条 pipeline。
- 因为 `effective_risk_tier` 用了 A2 的 fail-closed 属性，如果某次运行配置错误（live + tier 4），
  manifest 构建本身就会抛 `TierMisconfigurationError`，和 A2 的"绝不放行"语义一致地传播崩溃，
  不会留下一份基于错误配置的 manifest。

**涉及文件**：新增 `strategy/manifest.py`、`tests/trading_agent/strategy/test_manifest.py`；改动
`orchestration/premarket.py`、`orchestration/intraday.py`、`orchestration/postmarket.py`，以及三者
对应的现有测试文件（各加一条 manifest 落盘断言）。

**验收**：✅ 每次运行后该 run-date 目录下有 manifest；字段完整；测试覆盖 git_commit（真实仓库匹配
`git rev-parse HEAD` + 非 git 目录回退 `"unknown"`）和 config_hash（切换 active_strategy 后 hash 必变）。
253 测试通过（+5 新增 manifest 单测，另有 3 个现有编排测试加了 manifest 落盘断言）。

**注意**：**时间敏感**——manifest 越早上线，可对比的历史样本越多。已尽快上线。

---

## B2 — strategy_registry + registry.py — ✅ 已完成（2026-06-15）

**目标**：把「策略版本 + 配置组合 + 变更原因」登记下来。以后调参不是覆盖旧配置，而是新建一个
strategy version，供 B1 manifest 引用、F1 strategy compare 对比。

**实现记录**：
- 新增 `src/config/strategy_registry.yaml`：`active_strategy: baseline_v1` + `strategies` map。
  `baseline_v1` 登记了这次改动前 `runtime.env` 硬编码的值（`risk_tier_live: 3`、
  `risk_tier_paper: 4`、`scoring_profile`/`policy_profile: aggressive_growth`），保证零行为变化。
- 新增 `src/trading_agent/strategy/registry.py`：极简 YAML 解析器（风格与 `scoring_profiles.py`
  一致，不引入 pyyaml 依赖）；`load_active_strategy()` 纯读取，返回 strategy_id/status/两个
  profile 名/两个 risk tier/parent/change_reason；`apply_active_strategy_env_defaults()` 把这
  四个值（`SCORING_PROFILE`/`POLICY_PROFILE`/`RISK_TIER`/`PAPER_RISK_TIER`）写进 `os.environ`，
  但只填未设置的 key——shell export 和 `runtime.env`/`runtime.env.local` 永远优先。
- **关键接线**：`core/config.py` 的 `load_env_files()` 在合并完两个 env 文件后，调用
  `apply_active_strategy_env_defaults()`。这是唯一接线点——premarket/intraday/postmarket/doctor
  都已经在调用 `load_env_files`（A1 的产物），所以全部自动拿到 registry 的值，不需要在四处分别接线。
  `runtime.env` 里原来硬编码的 `RISK_TIER=3`/`PAPER_RISK_TIER=4` 已删除，改成指向 registry 的注释。
  这样切换 `active_strategy` 才能真正「切换整套 profile/tier 组合」，而不是被 `runtime.env` 的旧值挡住。
- 副作用验证：A2 的 `TierMisconfigurationError` fail-closed guard 对 registry 来源的值同样生效——
  如果某个 strategy version 把 `risk_tier_live` 误设成 4，`TRADING_MODE=live` 时一样会 fail-closed。
- `cli.py` `_run_doctor` 新增 `--- Strategy ---` 段，打印 `active_strategy`（含 status）和
  `change_reason`。
- 范围边界（有意不做）：registry 的 `watchlist` 字段目前只是记录，没有反向接线到
  `data/universe.py` 的 `parse_active_watchlist()`（它仍硬编码读 `active_watchlist.txt`）；
  按当前需求这不影响验收标准（profile/tier 切换），留给以后需要切换 watchlist 文件时再做。

**涉及文件**：新增 `src/config/strategy_registry.yaml`、`strategy/registry.py`、
`tests/trading_agent/strategy/test_registry.py`；改动 `core/config.py`、`cli.py`、`runtime.env`、
`tests/trading_agent/core/test_runtime.py`、`tests/trading_agent/test_cli.py`。

**验收**：✅ 用临时 registry 文件测试验证切换 `active_strategy` 同时改变 scoring/policy profile 和
两个 risk tier；`load_active_strategy()` 返回的 `strategy_id` 可供 B1 manifest 引用。248 测试通过
（+6 新增）。

---

## B3 — analytics DB builder（analytics.db） — ✅ 已完成（2026-06-15）

**目标**：新增 `analytics build` 命令，把分散的 runtime JSON/JSONL 汇总成统一可查询库，供 dashboard
与 replay 使用。

**实现记录**：
- 新增 `src/trading_agent/analytics/{__init__,schema,loaders,build_db}.py`；命令
  `python3 -m trading_agent analytics build [--since YYYY-MM-DD] [--until YYYY-MM-DD]`，读
  `runtime/state/runs/*`，写 `runtime/analytics/analytics.db`（SQLite，标准库 `sqlite3`，没引入新依赖）。
- 6 张表如计划：`runs`、`candidates`、`decisions`、`orders`、`paper_equity`、`blocked_reasons`。
  `orders`/`decisions` 复用了已有的 `replay/analysis.py` 的 `collect_paper_orders()`/
  `collect_decisions()`（同一套多事件订单合并 + JSONL 解析逻辑，不重新发明）。
  `candidates` 表的 `is_watchlist`/`is_tradable` 是用同一 run_date 的 `risk_overlay.json` 的
  `watchlist_candidates`/`tradable_candidates` 反查得到的。
- **字段范围调整**：roadmap 原列的 `trade_readiness_score`/`price_setup_score` 目前只在 intraday
  policy 引擎里临时计算（`policy/candidate_selector.py`），从未持久化到任何文件，所以这次没法从
  现有 JSON 拼出这两列。改用 `candidate_scores.json` 里确实存在的
  `technical_score`/`catalyst_score`/`dsa_score`/`kronos_score`/`quote_score`（components 字段）。
  以后如果要做 strategy compare，需要先让 candidate_selector 把这两个分数落盘。
- **幂等实现**：每次 build 都 `DROP TABLE IF EXISTS` + 重新 `CREATE TABLE` + 全量重新 `INSERT`，
  不做增量 upsert——因为源数据是 JSON/JSONL 文件本身，全量重建最简单也最不会有脏数据残留。

**涉及文件**：新增 `analytics/__init__.py`、`schema.py`、`loaders.py`、`build_db.py`、
`tests/trading_agent/analytics/test_build_db.py`；改动 `cli.py`（新增 `analytics build` 子命令）、
`tests/trading_agent/test_cli.py`。

**验收**：✅ 用 fixture run 目录验证 build 出 6 张表且行数正确（含 watchlist/tradable 标记、
blocked_reasons 按 run_date+reason 聚合计数）；重跑两次结果完全一致（幂等）；无数据的 run 目录
返回全 0 行数而不报错。259 测试通过（+6 新增）。

**依赖**：B1（manifest 提供 runs 表的 strategy/commit/hash）。

---

## B4 — strategy-changelog.md

**目标**：人类可读的策略版本变更记录，与 B2 registry 配套。

**具体步骤**：新增 `docs/strategy-changelog.md`，每次新增/调整 strategy version 时追加一条
（版本、父版本、变更原因、日期、对应 commit）。

**验收**：registry 里每个 `change_reason` 在 changelog 有对应条目。

---

# C 阶段 · 只读可视化与观测

## C1 — Dashboard MVP（Streamlit 只读）

**目标**：本地只读控制台，快速看懂「今天为什么交易/不交易、候选如何排序、订单如何成交、
策略是否变好」。运行在 `http://localhost:8501`，只读本机数据，不暴露公网。

**具体步骤**：
1. 命令 `python3 -m trading_agent dashboard`（Streamlit）。
2. 新增 `src/trading_agent/dashboard/{__init__,app,queries,charts}.py`。
3. 页面：
   - **Overview**：plan_state、market_regime、watchlist/tradable count、top_score、pending orders、today PnL。
   - **Candidates**：candidate_score、readiness、technical/price_setup/catalyst、score_status、blocked reason。
   - **Decisions**：每次 intraday run 时间线（no_trade / would_trade / paper_pending / pending_filled / canceled）。
   - **Orders**：submitted/filled/pending/canceled/rejected、limit vs fill、slippage、fill rate。
   - **Replay**：fill rate、blocked reason 分布、by-symbol。
4. 数据源**仅** `analytics.db` + runtime state；**不写任何交易参数**。

**涉及文件**：新增 `dashboard/*`、`cli.py`（新子命令）、`pyproject.toml`（streamlit 依赖）、测试（query helpers）。

**验收**：本地起页面可读 5 个视图；query helper 有单测；无任何写交易配置路径。

**依赖**：B3（analytics.db）。

---

## C2 — theme exposure / speculative cap 诊断

**目标**：`active_watchlist` 偏高 beta / speculative，paper 表现可能被少数主题支配。加诊断量化主题集中度。

**具体步骤**：
1. 在 `premarket_diagnostics.json`（或 risk_overlay）输出 watchlist/tradable 按 `theme` 与
   speculative tier（来自 `universe_meta.json`）的集中度。
2. 超过可配置 cap 时写 warning。

**涉及文件**：`planner/premarket_diagnostics.py` / `planner/risk_overlay.py`、`scoring_profiles.yaml`
（cap 配置）、测试。

**验收**：诊断输出每主题占比；超 cap 有 warning；阈值可配置。

---

# D 阶段 · 工程优化（不阻塞，边等数据边做）

## D1 — DSA / Technical 两层 token 优化 — ✅ 已完成（2026-06-15）

**目标**：在不降低（甚至提升）AI 可用信息量前提下，大幅降低 DSA 与 Technical 两个 Codex 层 token。
核心：**Python 预计算成紧凑特征文件，AI 只读特征做判断。** 完整设计见
[`design-prompt-token-optimization.md`](./design-prompt-token-optimization.md)。

**实现记录（全部完成，222 测试通过）**：
1. ✅ 新增 `planner/technical_features.py`（纯函数：SMA/EMA/RSI/MACD/ATR/swing/相对强度）+ 20 个测试。
2. ✅ 接 `run_technical()`（写 `technical_features.json`），改写 `technical/research.txt`（删图表/原始
   OHLCV 指令，改读特征包，仅 `data_quality="failed"` 时回退原始图表/OHLCV）。
3. ✅ 新增 `signals/dsa_metrics.py`（全 universe 批量下载 + 横截面/主题聚合 + market breadth）+ 5 个测试。
4. ✅ 接 `run_dsa()`（写 `dsa_metrics.json`），改写 `signals/dsa_scan.txt`（读横截面表，催化剂查询限定在
   promote/reconsider 候选，移除"为拉数据而开 subagent"的指令）。
5. ✅ env flag（`ENABLE_TECHNICAL_FEATURES_PRECOMPUTE=1` / `ENABLE_DSA_METRICS_PRECOMPUTE=1`、
   `TECHNICAL_RECENT_BARS=30`、`DSA_METRICS_LOOKBACK_DAYS=180`）+ `doctor` 回显 + `RuntimePaths`/
   `runtime_block.py` 新增 `TECHNICAL_FEATURES_PATH`/`DSA_METRICS_PATH`。
6. ✅ 输出 schema 未改一字（`TECHNICAL_SIGNALS_PATH`/`DSA_SIGNALS_PATH` 结构不变，scoring/risk_overlay
   不受影响）；每个 flag 可单独置 `0` 立即回退到旧行为。

**涉及文件**：新增 `planner/technical_features.py`、`signals/dsa_metrics.py`、改 `orchestration/premarket.py`、
`technical/research.txt`、`signals/dsa_scan.txt`、`core/context.py`、`prompts/runtime_block.py`、
`runtime.env`、`cli.py`、对应测试。

**遗留注意（未解决，记录以免遗忘）**：B1/B2（run_manifest/strategy_registry）尚未实现，所以这次上线
**没有**按原计划登记为一个新的 strategy version——目前没有机制区分"token 优化前/后"的 paper 样本。
等 B1/B2 落地后，应回头把这次上线标记为一个 strategy version 分界点，避免 E1 校准时把优化前后的
样本混在一起当成同一策略。

---

## D2 — market_feed 跨日缓存 / batch（旧 R4）

**目标**：进一步降低 yfinance 调用量与延迟（并发已做，缓存与 batch 是下一步）。

**具体步骤**：
1. **跨日缓存**：长周期 bar（1w/1d）跨 run-date 基本不变，缓存到 `runtime/cache/ohlcv/<symbol>/<timeframe>.json`，
   每天只拉增量。
2. **batch 拉取**：`yf.download(tickers=[...], group_by='ticker')` 单请求多标的（注意 1h/15m period 限制）。

**涉及文件**：`data/market_context.py`、可能新增 `data/ohlcv_cache.py`、测试。

**验收**：同样数据下 yfinance 请求次数显著下降；data_status 仍准确。

**注意**：缓存要有失效策略（split/dividend 调整后失效）；`auto_adjust=False` 下小心复权差异。

---

## D3 — Kronos batch 推理（旧 R5，需接口确认）

**目标**：Kronos 本地推理是 premarket 最慢环节之一，当前逐标的串行（active watchlist≤30 已缓解）。

**具体步骤**：
1. 确认 `kronos_generate_signals.py` / 上游 Kronos 是否支持 batch 输入。
2. 支持则改 `signals/kronos.py` live payload 走 batch；不支持则评估进程池并行（注意显存/CPU）。

**涉及文件**：`signals/kronos.py`、`src/scripts/kronos/kronos_generate_signals.py`、测试（mock）。

**验收**：全量 Kronos 推理时间下降；signal 输出与逐标的一致。

---

## D4 — paper 部分成交模型（旧 R6 / docx P3）

**目标**：当前 paper 只有「全成或不成」，加部分成交让仿真更真实。

**具体步骤**：
1. `paper/broker.py` 引入 `PAPER_PARTIAL_FILL`（默认关）：quote 在 limit 附近时按概率/比例部分成交。
2. orders.jsonl 记 `filled_qty < quantity`，余量转 pending；reconcile 累积。

**涉及文件**：`paper/broker.py`、`test_broker.py`、`runtime.env`（新 flag）。

**验收**：部分成交路径有测试；daily_usage/positions 记账正确；默认关闭时行为不变。

**注意**：会改变 fill rate 统计语义，E1 replay 需相应处理。

---

# E 阶段 · 数据驱动校准（阻塞于 2–3 周 paper 数据）

> **数据要求**：策略有效性判断至少 10–15 个交易日，最好 20–30 个。样本不足时不要因一两天表现大幅调权重。
> 每天至少保留：`candidate_scores.json`、`risk_overlay.json`、`premarket_diagnostics.json`、
> `daily_plan.json`、`decisions.jsonl`、paper `orders.jsonl` / `equity_curve.jsonl`、
> `day_start.json` / `day_end.json` / `postmarket_summary.json`，以及 B1 的 `run_manifest.json`。

## E1 — replay 校准：forward/benchmark returns + 命中率 + attribution（旧 R1 + docx P1）

**目标**：把「凭感觉调参」变成「凭数据调参」。在 `replay/analysis.py` 上补四块分析。

**阻塞依赖**：2–3 周 paper run 数据（见上）。

**具体步骤**：
1. **score 桶 vs 未来收益**：新增 `replay/forward_returns.py`，对每个历史 run date 候选用 yfinance 拉
   该 symbol 之后 1/3/5 交易日收益；按 `candidate_total`/`trade_readiness_score` 分桶算均值+命中率。
2. **benchmark returns（docx 新增）**：对照 SPY/QQQ/SMH/IWM，区分策略 alpha 与市场 beta。
3. **entry-zone 命中率 / breakout 成功率**：对 `pullback/breakout` 成交统计后续触及 target_1 vs stop。
4. **component attribution**：对每分量（dsa/technical/kronos/quote/catalyst/price_setup）算其得分与未来
   收益的相关性/IC，作为 E2 权重依据。

**涉及文件**：`replay/analysis.py`（扩展）、新增 `replay/forward_returns.py`、`cli.py`（如 `--forward-returns`）、测试。

**验收**：每桶样本数/均值/胜率可见，桶单调性可观测；分 setup_type 输出 win/loss/未决；每分量 IC 排名；
benchmark 对照可见。

**注意**：forward returns 需联网 yfinance，测试用 mock；真实运行处理停牌/数据缺口。

---

## E2 — 评分 / 价格 setup 权重校准（旧 R2）

**目标**：把 `trade_readiness_score` 六分量权重（含 `price_setup_score` 的 `0.15`）与 scoring 五分量
权重（dsa 0.25 / technical 0.30 / kronos 0.15 / quote 0.10 / catalyst 0.20）从「保守先验」改成「数据校准值」。

**阻塞依赖**：E1 的 component attribution 输出。

**具体步骤**：
1. 用 IC 排名按贡献重分配权重（约束合计 1.00）。
2. 校准 `estimate_price_setup_score` 内部常数（20/60/70 基准、RR 奖励斜率）。
3. 在 `policy_profiles.json` / `scoring_profiles.yaml` 配置化（见 A3），不再硬编码。
4. 更新测试锁住新行为；新权重作为一个**新 strategy version**登记（B2）。

**涉及文件**：`policy/candidate_selector.py`、`policy/technical.py`、`planner/scoring.py`、配置文件、测试。

**验收**：新权重有 attribution 支撑；文档记录「为什么是这个值」；回看胜率/收益不劣化。

---

## E3 — near-miss tracking（docx P2）

**目标**：记录「差一点到 entry zone / 差一点过 threshold / 被 no-chase block」的候选及其后续表现，
用于优化 entry/threshold，而不是只看成交单。

**具体步骤**：在 decisions/replay 里标记 near-miss 类别，E1 forward returns 对其同样回算后续收益。

**涉及文件**：`policy/engine.py`（标记）、`replay/*`、测试。

**验收**：near-miss 候选有分类计数与后续收益分布。

---

## E4 — bid/ask/spread 成交质量（docx P2，可选）

**目标**：更真实评估成交质量、滑点、流动性风险。paper 阶段弱依赖，可后置。

**具体步骤**：在 quote 采集处记录 bid/ask/spread，写入 orders/analytics，供成交质量分析。

**涉及文件**：`data/live_quotes.py`、`paper/broker.py`、`analytics/*`、测试。

**验收**：订单记录含 spread；replay 可输出按 spread 分组的滑点。

---

# F 阶段 · 后期 / 故意推后

## F1 — strategy compare

**目标**：对比不同 `strategy_id` 的 run count、fill rate、PnL、blocked reasons、平均分，判断新版本是否更好。

**依赖**：B1（manifest）+ B2（registry）+ 至少两个 strategy version 的积累数据。

**具体步骤**：dashboard 增 Strategy Compare 页 / `analytics` 增对比查询。

**验收**：能并排看两个版本的关键指标差异。

---

## F2 — review / live 真实下单接线（旧 R7，⛔ 故意推后）

**目标**：把 review/live 从 `execution_not_wired` 接到真实 Robinhood MCP。

**前置条件（硬性）**：
- replay 显示 paper 成交率/胜率/blocked 分布合理。
- 至少若干周 paper 日志「无聊且正确」。
- review 路径先证明只 review 不下单。
- 人工显式移除 `KILL_SWITCH`，人工设 `RISK_TIER`（绝不让 Codex 改）。

**具体步骤（分阶段）**：
1. **review 模式**：intraday 在 `TRADING_MODE=review` 时调用 `review_equity_order`（只审单不下单），
   审计日志验证从不触发 `place_equity_order`。
2. **live tier 0**：review 日志干净后接 `place_equity_order`，从 tier 0（$10/$25）起。
3. 每阶段都要有 fail-closed 测试与回滚开关。

**涉及文件**：`orchestration/intraday.py`、`policy/engine.py`、`.codex/config.toml`（MCP 审批）、新增测试。

**注意**：全项目风险最高的改动。MCP 审批、KILL_SWITCH、tier 上限三道闸必须同时在位。

---

## F3 — config editor（⛔ 最后做）

**目标**：让 dashboard 可编辑交易参数。**初期坚决不做**——第一版 dashboard 只读，等运行稳定、replay
数据充分后再考虑，且需独立的审批/审计设计。

**前置条件**：C1 dashboard 稳定 + E 阶段校准完成 + 明确的写入审批机制。
