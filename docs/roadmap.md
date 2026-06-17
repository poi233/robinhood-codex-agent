# 未来工作清单（Roadmap · 全局合并版）

> 最后更新：2026-06-16
> 配套：现状见 [`project-status.md`](./project-status.md)；token 优化详细设计见
> [`design-prompt-token-optimization.md`](./design-prompt-token-optimization.md)；
> 自成长平台 G0–G2 详细实现计划见
> [`superpowers/plans/2026-06-16-self-growth-platform-g0-g2.md`](./superpowers/plans/2026-06-16-self-growth-platform-g0-g2.md)。
>
> 本文件已合并四处来源，去重后按全局优先级排序：
> 1. 旧 roadmap 的 R1–R7（校准 / 配置化 / 性能 / 部分成交 / live 接线）。
> 2. `design-prompt-token-optimization.md`（DSA / Technical 两层 token 优化，已成设计，未进 roadmap）。
> 3. `robinhood_codex_agent_strategy_lab_plan`（**Strategy Lab / Dashboard** 新方向 + 若干正确性/观测项）。
> 4. `robinhood_codex_agent_strategy_lab_self_growth_plan`（**全模块自成长策略平台** G0–G8，见 G 阶段）。
>
> 每项给：目标、阻塞依赖、具体步骤、涉及文件、验收标准。
>
> **四条贯穿原则**
> - **不用魔数换魔数**：任何新权重/阈值在固化前必须经回看数据校准。
> - **可追溯优先**：先有 `run_manifest` + `analytics.db`，再做任何会改变行为的改动（token 优化、权重校准
>   都应记为一个**新的 strategy version**），否则积累的 paper 数据无法横向对比。
> - **paper-only 安全**：review/live 继续不接线，dashboard 第一版只读、不可改交易参数。
> - **自成长受控**：自成长只能在 paper / shadow paper / replay 内运行，**只提议、不自动改 champion，
>   绝不自动升级 live**（不动 TRADING_MODE / RISK_TIER / KILL_SWITCH / 真实下单）。详见 G 阶段。

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
| | B4 | strategy-changelog.md | docx | ✅ **已完成**（2026-06-15） |
| **C 只读可视化与观测** | C1 | Dashboard MVP（Streamlit 只读） | docx | ✅ **已完成**（2026-06-15，视觉未验证） |
| | C2 | theme exposure / speculative cap 诊断 | docx | ✅ **已完成**（2026-06-15） |
| | C3 | Dashboard v2（可读性重构 + 策略对比，含 F1） | 用户新增 | ✅ **已完成**（2026-06-16，首次 headless 渲染验证；像素级视觉仍待人工目测） |
| **D 工程优化 · 不阻塞** | D1 | DSA/Technical token 优化 | design doc | ✅ **已完成**（2026-06-15，见下方实现记录） |
| | D2 | market_feed 跨日缓存 / batch | 旧 R4 | 🟡 部分完成（2026-06-15，缓存做了，batch 未做） |
| | D3 | Kronos batch 推理 | 旧 R5 | ✅ **已完成**（2026-06-16） |
| | D4 | paper 部分成交模型 | 旧 R6 + docx P3 | ✅ **已完成**（2026-06-15） |
| **E 数据驱动校准** | E1 | replay 校准：forward/benchmark returns + 命中率 + attribution + Calibration tab | 旧 R1 + docx P1 | ✅ **机器已建（2026-06-16）**；统计显著性待 paper 数据积累 |
| | E2 | 评分 / 价格 setup 权重校准 | 旧 R2 | ⏳ 依赖 E1（P5） |
| | E3 | near-miss tracking | docx P2 | ✅ **机器已建（2026-06-16，near-threshold 版）**；entry-zone/no-chase 版待 per-candidate 落盘 |
| | E4 | bid/ask/spread 成交质量 | docx P2 | 可选（paper 阶段弱依赖） |
| **新增 · 校准期补强** | G9 | challenger 隔离 paper 账本（shadow orders/equity） | 我的建议 | ✅ **已完成（2026-06-16）** |
| | B5 | strategy_registry.watchlist → active watchlist resolver | 我的建议 | ✅ **已完成（2026-06-16）** |
| **F 后期 / 故意推后** | F1 | strategy compare | docx | 依赖 B1+B2+多 strategy version |
| | F2 | review/live 真实下单接线 | 旧 R7 | ⛔ 故意推后（人工解锁） |
| | F3 | config editor（dashboard 可编辑参数） | docx | ⛔ 最后做 |
| **G 自成长平台 · paper/shadow only** | G-pre | profile 解耦 + 实验账本隔离（可拓展性前置） | 审查新增 | ✅ **已完成**（2026-06-16，profile 按名解析 + `build_experiment_paths`） |
| | G0 | growth_policy + validator 骨架（安全边界） | self-growth | ✅ **已完成**（2026-06-16） |
| | G1 | growth observations（全局诊断） | self-growth | ✅ **已完成**（2026-06-16） |
| | G2 | 模块 diagnosers + dashboard Self-Growth Lab | self-growth | ✅ **已完成**（2026-06-16） |
| | G3 | proposal generator（只写 proposal，不启用） | self-growth | ✅ **已完成**（2026-06-16） |
| | G4 | proposal validator（完整校验） | self-growth | ✅ **已完成**（2026-06-16） |
| | G5 | experiment queue（proposed→…→archived） | self-growth | ✅ **已完成**（2026-06-16） |
| | G6 | shadow paper runner（challenger 隔离并跑） | self-growth | ✅ **已完成**（2026-06-16，决策级；订单/权益 shadow 仿真留待后续） |
| | G7 | evaluator + promotion recommendation | self-growth | ✅ **已完成**（2026-06-16，forward returns 仍待 E1） |
| | G8 | human-in-the-loop promotion（仅人工改 YAML） | self-growth | ✅ **已完成**（2026-06-16） |

> **新旧编号对照**：R1→E1（增 benchmark returns）、R2→E2、R3→A3、R4→D2、R5→D3、R6→D4、R7→F2；
> token 优化设计→D1；docx 的 run_manifest→B1、registry→B2、analytics.db→B3、changelog→B4、
> dashboard→C1、theme 诊断→C2、forward/benchmark/attribution→E1、near-miss→E3、bid/ask/spread→E4、
> strategy compare→F1、config editor→F3。

---

## 立即可做的建议顺序（无数据依赖期）

数据校准（E 阶段）阻塞于 2–3 周 paper 积累，期间按下面顺序推进；越靠前越「时间敏感或解锁后续」：

1. **A1 / A2 / A3** — 正确性与安全闸。✅ 已完成（2026-06-15）。
2. **B1 → B4** — 数据可追溯基建。✅ 已完成（2026-06-15）：run_manifest、strategy_registry、
   analytics.db、strategy-changelog 全部上线。
3. **C1 / C2** — 只读 dashboard + theme 诊断。✅ 已完成（2026-06-15，dashboard 视觉未人工验证）。
4. **D1 / D3 / D4** ✅ 已完成；**D2** 🟡 跨日缓存已做、batch 未做。
5. **G-pre → G0 → G1 → G2** ✅ **已完成**（2026-06-16）：自成长平台的**只读诊断**地基已落地。
   - G-pre 的 profile 按名解析已完成（`load_scoring_profile`/`load_policy_profile` 支持
     `profile_name=`，默认行为不变）；实验账本隔离 `build_experiment_paths` 因为在 G6 之前没有
     消费者，按 YAGNI 推后到 G6。
   - G0（`growth_policy.json` + validator）、G1（`growth observe` + `growth_observations.json`）、
     G2（模块 diagnoser 注册表 + dashboard Self-Growth Lab）全部上线，**只读、paper-safe、零交易
     行为变化**。详见下方各 G 阶段的实现记录。
   - G0–G2 详细 TDD 实现计划见
     [`superpowers/plans/2026-06-16-self-growth-platform-g0-g2.md`](./superpowers/plans/2026-06-16-self-growth-platform-g0-g2.md)。
6. 持续每天跑 paper，积累 E1 所需数据。
7. **G3 → G4 → G5** ✅ **已完成**（2026-06-16）：系统能「提出安全实验」（`growth propose` 只写
   proposal、`growth validate` 完整校验、`growth experiments` 入队），仍不改 champion。
8. 2–3 周后回到 **E1 → E2**，用真实数据校准；其间补 **E3 / E4**。E1 的 forward returns 同时是 G7
   evaluator 的关键输入（目前 G7 把 forward returns 列为缺失指标、相应 gate 推荐）。
9. **G6 → G7 → G8** ✅ **已完成**（2026-06-16）：challenger 在 shadow paper 隔离账本里跑（`growth
   shadow`，已接入 intraday），evaluator 并排对比并生成**人工** promote 建议（`growth evaluate` /
   `recommend`），promote 检查只生成草稿、绝不改 `active_strategy`（`growth promote check`）。
   目前 shadow 只产决策流、订单/权益 shadow 仿真与 E1 forward returns 待补，G7 在这些指标到位前不会
   给出 promote 推荐。
10. **F1 / F2 / F3** 只在以上稳定后，由人工主导推进。

---

## 🎯 当前焦点（2026-06-16 之后）：从「能跑」到「能证明策略有效」

> 工程壳子（A–D 基建、C dashboard、G0–G8 自成长全闭环）已基本成熟。**现在的瓶颈不是再堆功能，
> 而是验证策略本身有没有 edge**：哪个分量真有用、哪个 setup 真能赚、哪些 blocked reason 是保护、
> 哪些是错过。配套每日操作手册见 [`daily-strategy-playbook.md`](./daily-strategy-playbook.md)。

**按优先级排序（含我的判断，不只是"等数据"）：**

1. **P0 · 每天稳定跑 paper，冻结 baseline_v1（持续）**。连续 10–15（最好 20–30）个交易日，
   **不调权重/阈值**，否则样本不可比。期间自成长只用 `observe` + `propose`（写 proposal、不 approve、
   不 shadow），保持 champion 干净。详见 playbook。

2. **P1 · E1 校准地基** — ✅ **机器已建（2026-06-16）**：forward/benchmark returns + component IC
   attribution + setup outcomes + `calibration_report.{json,md}` + `analytics calibrate` + dashboard
   Calibration Tab 全部上线、可离线单测。**现在每积累一天，跑 `analytics calibrate` 就能立刻消费**；
   统计显著性仍需 15–30 个 run date。详见下方 **E1** 实现记录。**下一个代码任务 → P3 的 G9。**

3. **P2 · E3 near-miss tracking** — 复用 E1 forward returns，回答「错过后发生了什么」（门槛/entry
   zone/no-chase 是否太严）。比单看 PnL 更有价值。

4. **P3 · G9 challenger 隔离 paper 账本（shadow orders/equity）** — ✅ **已完成（2026-06-16）**：challenger
   现在有自己的 `experiments/<id>/paper/` 账本，G7 报告含其真实 fill rate / drawdown / PnL，fill-rate 与
   drawdown 两个 promotion gate 真能比较了。见 **G9** 实现记录。**下一个代码任务 → P4 的 B5。**

5. **P4 · 策略版本化 + watchlist resolver（B5）** — ✅ **B5 已完成（2026-06-16）**：切换 `active_strategy`
   现在真能切 watchlist 文件。策略版本化实验本身（建单变量 challenger）等 E1 数据指出该动哪个杠杆后
   再做。**至此"现在能做"的代码任务都已完成，剩 P5(E2) 是真数据阻塞。**

6. **P5 · E2 权重重校准** — 用 E1 的 IC/attribution 重分配评分权重，登记为**新 strategy version**，先
   shadow 再考虑 promote。**绝不**手动拍脑袋调权重。

**贯穿纪律**：冻结 baseline → 一次一个实验 → 只用数据 promote（≥10 shadow 日、fill rate / drawdown /
forward return 不劣于 champion、无 safety violation、人工 approve）。

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
- **字段范围调整**：roadmap 原列的 `trade_readiness_score`/`price_setup_score` 当时只在 intraday
  policy 引擎里临时计算（`policy/candidate_selector.py`），从未持久化，所以 B3 的 `candidates` 表
  改用 `candidate_scores.json` 里确实存在的
  `technical_score`/`catalyst_score`/`dsa_score`/`kronos_score`/`quote_score`（components 字段）。
  **更新（2026-06-16）**：已补上落盘——intraday pipeline 现在每次 run 用同一个纯函数
  `rank_candidates(inputs)` 把每个候选的 `trade_readiness_score`/`price_setup_score` + 六分量写到
  `runtime/logs/runs/<date>/audit/intraday_rankings.jsonl`，`analytics build` 新增第 7 张表
  `intraday_rankings`。这样 E1 的 component attribution / E2 的 `price_setup` 权重校准从这天起有
  真实历史数据；之前的样本仍缺这两个分数。
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

## B4 — strategy-changelog.md — ✅ 已完成（2026-06-15）

**目标**：人类可读的策略版本变更记录，与 B2 registry 配套。

**实现记录**：
- 新增 `docs/strategy-changelog.md`：`baseline_v1` 一条记录（parent/日期/commit/config/change_reason），
  与 `strategy_registry.yaml` 的对应条目一一对应。
- `strategy/registry.py` 新增公开函数 `list_strategy_ids(agent_root)`，读取 registry 里所有
  strategy_id（不止 active 的那个），为以后多版本场景和验收检查提供基础。
- 新增测试 `test_every_registered_strategy_has_a_changelog_entry`：遍历
  `list_strategy_ids()` 的每个 id，断言 changelog 里有对应的 `## {strategy_id}` 标题——这把验收标准
  变成了一个会跑的测试，而不是人工承诺，以后新增 strategy version 忘记写 changelog 会直接测试失败。

**涉及文件**：新增 `docs/strategy-changelog.md`；改动 `strategy/registry.py`、
`tests/trading_agent/strategy/test_registry.py`。

**验收**：✅ registry 里每个 `change_reason` 在 changelog 有对应条目，并由测试强制保证。261 测试通过
（+2 新增）。

---

# C 阶段 · 只读可视化与观测

## C1 — Dashboard MVP（Streamlit 只读） — ✅ 已完成（2026-06-15，视觉效果未人工验证）

**目标**：本地只读控制台，快速看懂「今天为什么交易/不交易、候选如何排序、订单如何成交、
策略是否变好」。运行在 `http://localhost:8501`，只读本机数据，不暴露公网。

**实现记录**：
- 命令 `python3 -m trading_agent dashboard`：`cli.py` 用 `subprocess` 拉起
  `streamlit run src/trading_agent/dashboard/app.py`（懒加载，不让 streamlit 成为其余命令的硬依赖）。
- 新增 `src/trading_agent/dashboard/{__init__,app,queries,charts}.py`：
  - `queries.py`：纯函数，对 `analytics.db`（B3）做 sqlite3 查询，外加少量直接读
    `daily_plan.json`/`risk_overlay.json`（`plan_state`/`market_regime` 不在 analytics.db 里，
    符合 roadmap"数据源仅 analytics.db + runtime state"的范围）；`replay_summary()` 直接复用
    `replay/analysis.py` 的 `build_replay_report`，不重新发明。
  - `charts.py`：薄封装 streamlit 组件（`st.metric`/`st.bar_chart`/`st.dataframe`），不含业务逻辑。
  - `app.py`：单页面（不是多页签/sidebar 导航），5 个区块从上到下用 `st.header()` 依次排列——
    Overview/Candidates/Decisions/Orders/Replay 默认加载时全部一次性渲染，不需要任何点击。
- `pyproject.toml` 新增 `[project.optional-dependencies] dashboard = ["streamlit>=1.30"]`（可选依赖，
  其余命令不受影响）。
- **未做到的部分**：`candidates_table` 没有 `price_setup_score`/`trade_readiness_score` 列，原因同
  B3——这两个分数没有持久化。
- **验证状态（重要）**：query helper 全部有单测（8 个，覆盖 `analytics.db` 缺失/存在两种情况）；
  实际启动过 `streamlit run` 确认进程能跑起来、监听 8501；但**页面视觉效果没有人工核实**——
  本次会话的沙箱环境拿不到 macOS 截屏权限，用户决定"先这样，以后再改可视化部分"，明确说明这部分
  尚未经过人工目测确认，后续要看真实效果需要用户自己跑 `python3 -m trading_agent dashboard` 打开看。

**涉及文件**：新增 `dashboard/__init__.py`、`app.py`、`queries.py`、`charts.py`、
`tests/trading_agent/dashboard/test_queries.py`；改动 `cli.py`、`pyproject.toml`。

**验收**：✅ query helper 有单测（8 个）；无任何写交易配置路径（`queries.py`/`charts.py` 全是只读）。
⚠️ "本地起页面可读 5 个视图"这条本该靠人工核实，本次未完成，留给用户自行验证。275 测试通过
（+8 新增）。

**依赖**：B3（analytics.db）。✅ 已满足。

---

## C2 — theme exposure / speculative cap 诊断 — ✅ 已完成（2026-06-15）

**目标**：`active_watchlist` 偏高 beta / speculative，paper 表现可能被少数主题支配。加诊断量化主题集中度。

**实现记录**：
- `planner/premarket_diagnostics.py` 新增 `theme_diagnostics` 字段，写入 `premarket_diagnostics.json`：
  对 `watchlist_candidates` 和 `tradable_candidates` 各算一份 `theme_distribution`（按
  `universe_meta.json` 的 `theme` 字段分组的 count + pct）、`dominant_theme`、`max_theme_pct`、
  `speculative_pct`（特指 `theme == "speculative"` 那一类的占比，主题名可配置）。
- `scoring_profiles.yaml` 新增三个顶层 cap 配置：`max_theme_concentration_pct: 50`、
  `max_speculative_theme_pct: 40`、`speculative_theme_name: speculative`；超过对应 cap 时往
  `warnings` 列表追加 `theme_concentration_exceeded:{bucket}:{theme}:{pct}%>{cap}%` 或
  `speculative_concentration_exceeded:{bucket}:{pct}%>{cap}%`。
- 没有 `universe_meta.json`（或传入空 `universe_meta`）时只跳过 cap 告警，不跳过整段诊断——避免在
  缺数据时把所有 symbol 归到 `"unknown"` 主题、误触发 100% 集中度告警。
- `build_premarket_diagnostics_from_paths` 新增私有 helper `_load_universe_meta(config_dir)`，
  读取并规范化 `universe_meta.json`（symbol 转大写、跳过非 dict 条目）。

**涉及文件**：`planner/premarket_diagnostics.py`、`planner/scoring_profiles.py`、
`src/config/scoring_profiles.yaml`、`tests/trading_agent/planner/test_premarket_diagnostics.py`、
`tests/trading_agent/planner/test_scoring_profiles.py`。

**验收**：✅ 诊断输出每主题占比（`theme_distribution`）；超 cap 有 warning（dominant theme 和
speculative 占比分别有独立 cap）；阈值通过 `scoring_profiles.yaml` 可配置，测试验证了用自定义
`scoring_profile` 改 cap 后行为随之变化。267 测试通过（+6 新增）。

---

## C3 — Dashboard v2（可读性重构 + 策略对比）— ✅ 已完成（2026-06-16）

**实现记录**：
- `dashboard/app.py` 从单页瀑布流改成 **`st.sidebar`（run-date 选择 + 数据计数）+ `st.tabs` 7 个
  Tab**：① Today / ② Candidates / ③ Decisions / ④ Paper / ⑤ Strategy Comparison / ⑥ Self-Growth /
  ⑦ Themes（与下方设计一致）。
- `dashboard/queries.py` 新增 8 个**纯只读**查询并各有单测：`candidates_with_rankings`（candidates
  join 最新 `intraday_rankings`）、`equity_timeseries`、`blocked_reason_trend`、`strategy_comparison`
  （按 `runs.strategy_id` 聚合 fill rate / no-trade rate / PnL / 平均分 / top blocked reason）、
  `champion_vs_challengers`（读 G7 `experiment_report.json`）、`proposals_overview`、
  `experiment_queue_overview`、`theme_diagnostics`。
- `dashboard/charts.py` 新增可复用组件：`plan_state_badge`（颜色编码）、`today_view`（决策原因人话化）、
  `candidates_with_rankings_view`、`equity_curve_view`、`blocked_reason_trend_view`、
  `strategy_comparison_view`、`champion_vs_challengers_view`、`proposals_and_queue_view`、
  `theme_diagnostics_view`。
- **⑤ 策略对比落地两块**：(a) champion 版本横向对比（**实现 F1**，按 strategy_id 并排；现仅
  `baseline_v1`，UI/查询框架已就位，等切第二个版本就有第二行）；(b) champion vs challenger（读
  `experiment_report.json`，现有数据就能并排，缺失指标标注待补）。
- **验证（重要进步）**：新增 `tests/.../dashboard/test_app_smoke.py`，用 streamlit 的 `AppTest`
  **headless 渲染整个 app**（streamlit 缺失时自动 skip），断言 7 个 Tab 全部无异常渲染——这是 dashboard
  **第一次被自动化验证能真正跑起来**（C1 当年只起过进程、没渲染验证）。查询层 17 个单测全绿。
- **仍未做**：像素级视觉/布局美观度仍需人工 `python3 -m trading_agent dashboard` 目测（沙箱无法截屏）；
  本条只保证「能渲染、查询正确、结构到位」。**全程只读，未碰任何交易代码路径。**

**原设计（保留作参考）**：

> **背景**：C1 的 dashboard 是单页瀑布流（Overview / Candidates / Decisions / Orders / Replay /
> Self-Growth Lab 六块从上往下平铺），`charts.py` 全是 `st.dataframe`/`st.metric` 的薄封装，**视觉
> 从未人工验证**。现在 B/C/G 阶段已经攒下足够多的数据源（`analytics.db` 7 张表 + replay + growth
> 产物 + registry），值得把 dashboard 从「能看」升级到「好读、且能回答问题」。**全程只读，不写任何交易
> 参数**（与 C1 同约束；可编辑参数仍是 F3，最后做）。

**三个目标**
1. **可读性**：从单页瀑布流改成**侧边栏导航 + 多 Tab**，每个 Tab 聚焦一个问题，不用滚一面墙；
   状态用颜色编码（plan_state / fill rate / no-trade rate 的绿/黄/红），金额/百分比/分数统一格式化，
   metric 卡片带 delta（环比昨日 / 对比 champion）。
2. **有用内容**：每屏直接回答一个具体问题（今天为什么交易/不交易、分数和结果的关系、阻断原因趋势、
   paper 表现曲线、自成长在干嘛），而不是甩一堆原始表。
3. **策略对比**：新增一个 **Strategy Comparison** Tab，覆盖两种对比（见下）。

**页面/Tab 设计（建议 7 个 Tab，侧边栏选 run-date / 日期区间 / strategy 过滤）**

| Tab | 回答的问题 | 主要内容（数据源） |
|---|---|---|
| **① Today** | 今天发生了什么、为什么 | plan_state / market_regime 徽章；watchlist/tradable 计数；当日**唯一决策 + 原因叙述**（would_trade/blocked + blocked_reasons 人话化）；当日订单；当日权益快照。源：`daily_plan`/`risk_overlay` + `decisions`/`orders`/`paper_equity` 表 |
| **② Candidates & Scores** | 候选怎么排的、各分量贡献 | 候选表（五分量 dsa/technical/kronos/quote/catalyst + `is_watchlist`/`is_tradable`）**join `intraday_rankings`**（`trade_readiness_score`/`price_setup_score`）；分数分布直方图；score vs 是否 tradable 的散点/分桶。源：`candidates` + `intraday_rankings` 表 |
| **③ Decisions & Blocks** | 为什么大多不交易、卡在哪 | 决策时间线；**blocked-reason 分布（当日）+ 趋势（跨日堆叠）**；no-trade rate 折线。源：`decisions`/`blocked_reasons` 表 + replay |
| **④ Paper Performance** | paper 跑得好不好 | **多日权益曲线**（total_equity / realized_pnl）；max drawdown；fill rate 趋势；按 symbol 的成交统计；部分成交占比。源：`paper_equity`/`orders` 表 + replay |
| **⑤ Strategy Comparison** | 不同策略哪个更好（**本条重点**） | 见下方两节 |
| **⑥ Self-Growth Lab** | 自成长在提什么、实验进展 | 现有 observations + 模块 diagnoser；**新增**：proposals 列表（`runtime/strategy_proposals/`）、实验队列状态（`strategy_experiments.yaml` 的生命周期）、promotion recommendation 摘要（`experiment_report.json`/`promotion_recommendation.md`）。源：growth 全套产物 |
| **⑦ Themes & Exposure** | 主题集中度风险 | C2 的 `theme_diagnostics`（每主题占比、dominant theme、speculative 占比、超 cap 告警）。源：`premarket_diagnostics.json` |

**⑤ Strategy Comparison — 两种对比（核心诉求「不同策略对比」）**

- **(a) Champion 版本横向对比（实现 F1）**：按 `runs` 表的 `strategy_id` 分组，并排展示每个 strategy
  version 的：run 天数、日期区间、fill rate、no-trade rate、平均每日 realized PnL、累计 PnL、top
  blocked reasons、平均 candidate score、平均 trade_readiness_score。表格 + 并排柱状图。
  - **依赖**：至少 2 个 strategy version 各自积累过 run（B1 manifest 已给每个 run 打了 `strategy_id`）。
    现在只有 `baseline_v1`，所以这块**先做出 UI 框架 + 查询**，等真正切过一次策略才有第二条对比。
- **(b) Champion vs Challenger（shadow 实验，G7 数据现在就有）**：直接读 `experiment_report.json`，
  并排展示 champion 与每个 active_shadow/ready_for_review challenger 的：shadow 天数、evaluations、
  would-trade 数/率、no-trade rate、blocked-reason 分布差异、**决策分歧**（challenger 想交易而 champion
  没有的 symbol/日期）、evaluator 裁决（recommend_promote + blocking reasons）。
  - 这是**当下最有信息量**的对比，G6/G7 一跑就有数据。
  - 明确标注**缺失指标**：challenger 的 fill rate / drawdown（G6 只产决策流、订单/权益 shadow 仿真未做）
    和 forward returns（E1 未建）显示为 “待补”，并解释为什么 evaluator 暂不出 promote 建议。

**实现要点（待批准后做）**
- `dashboard/queries.py` 新增纯查询函数（沿用现有「纯函数 + 单测」风格，全部只读）：
  `strategy_comparison(agent_root)`（按 `strategy_id` 聚合 runs/orders/decisions）、
  `champion_vs_challengers(agent_root)`（读 `experiment_report.json`）、
  `equity_timeseries(agent_root, *, since, until)`（跨日权益曲线）、
  `blocked_reason_trend(agent_root)`（跨日堆叠）、
  `candidates_with_rankings(agent_root, run_date)`（candidates join intraday_rankings）、
  `proposals_overview` / `experiment_queue_overview`（读 growth 产物）。
- `dashboard/app.py` 从单页改为 `st.tabs([...])` + `st.sidebar`（run-date / 日期区间 / strategy 过滤）。
- `dashboard/charts.py` 增可复用组件：`status_badge`（颜色编码）、`metric_card_with_delta`、
  `comparison_table`（并排 + 高亮更优值）、`equity_curve_chart`、`stacked_reason_chart`。
- 可选小依赖：仍只用 streamlit 内置图表（`st.bar_chart`/`st.line_chart`/`st.dataframe` 带列格式化）；
  如需更好看的对比图再评估 `altair`（streamlit 自带）——不引入重依赖。

**涉及文件**：`dashboard/app.py`、`queries.py`、`charts.py`；新增 `tests/.../dashboard/test_queries.py`
对新查询的单测；可能给 `analytics` 加一个按 `strategy_id` 聚合的 view/查询。**不动任何交易代码路径。**

**验收标准**
- 侧边栏导航 + 7 个 Tab，每个 Tab 单屏可读、空数据有友好提示。
- **Strategy Comparison Tab**：实验存在时能并排看 champion vs ≥1 challenger 的关键指标（含决策分歧
  与 evaluator 裁决）；存在 ≥2 个 strategy version 时能并排看版本对比（F1）。
- 所有新增查询是纯函数、有单测；`queries.py`/`charts.py` **零写交易参数路径**。
- 状态色编码、金额/百分比格式化、metric delta 到位。
- ⚠️ 同 C1：**页面视觉效果仍需人工跑 `python3 -m trading_agent dashboard` 目测**（沙箱无法截屏）；
  本条验收只保证查询正确性 + 结构，视觉留给用户确认。

**依赖与现状**
- 数据源全部就绪：`analytics.db`（B3，含 G 阶段新增的 `intraday_rankings`）、replay、growth 产物、
  registry。**(b) champion-vs-challenger 现在就能做**；**(a) 版本横向对比**框架能做、但要等切过第二个
  strategy version 才有可比数据。
- **本条实现后，roadmap 的 F1（strategy compare）即由 ⑤(a) 落地**，F1 不再单列实现，只保留为概念入口。

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

## D2 — market_feed 跨日缓存 / batch（旧 R4） — 部分完成（2026-06-15，跨日缓存已做，batch 拉取未做）

**目标**：进一步降低 yfinance 调用量与延迟（并发已做，缓存与 batch 是下一步）。

**实现记录**：
- **跨日缓存（已完成）**：新增 `data/ohlcv_cache.py`，对 1w/1d 两个长周期 timeframe 生效（1h/15m 不缓存，
  变化太快、收益小）。缓存文件 `runtime/cache/ohlcv/<symbol>/<timeframe>.json`（新增 `RuntimePaths.
  ohlcv_cache_dir`，`OHLCV_CACHE_DIR` 可覆盖）。逻辑：
  - 无缓存 → 全量拉取（1d 用 `period=1y`，1w 用 `period=3y`，与原行为一致），写缓存。
  - 有缓存 → 只拉短尾增量（1d 用 `period=5d`，1w 用 `period=1mo`），按 timestamp 去重合并，按原本的
    lookback 窗口（1d 120 天 / 1w 180 天）裁剪过期数据，写回缓存。
  - **失效策略**：增量窗口里和缓存重叠的 bar，如果收盘价相对变化超过 1%（`SPLIT_DIVIDEND_TOLERANCE`），
    判定为 split/dividend 调整导致旧缓存价格不可用，整份缓存丢弃、退回全量拉取重建——直接响应 roadmap
    "缓存要有失效策略" 的要求。
  - `fetch_live_rows()` 新增可选 `period` 参数（默认行为不变），供增量拉取复用同一份 yfinance 调用逻辑。
  - `collect_market_context()`/`_process_one_symbol()` 新增 `cache_dir` 参数（默认 `None` = 不缓存，
    向后兼容现有调用方/测试）；`premarket.py` 接入时传 `paths.ohlcv_cache_dir`，受 `ENABLE_OHLCV_CACHE`
    （默认 1）开关控制，`doctor` 回显。
- **batch 拉取（未做）**：`yf.download(tickers=[...], group_by='ticker')` 单请求多标的没有实现——
  跨日缓存已经把 1w/1d 的全量历史拉取频率从"每天每标的"降到"每天每标的一次短尾增量"，是更大的请求量
  下降来源；batch 拉取要处理不同 timeframe 的 period 限制和响应 shape 差异，复杂度/风险相对单独跨日
  缓存更高，这次先不做，需要时再单独评估。

**涉及文件**：新增 `data/ohlcv_cache.py`、`tests/trading_agent/data/test_ohlcv_cache.py`；改动
`data/market_context.py`、`core/context.py`、`orchestration/premarket.py`、`cli.py`、`runtime.env`、
对应测试文件。

**验收**：✅ 跨日缓存场景下 yfinance 请求次数显著下降（增量 period 远小于全量 period）；data_status
逻辑不变，仍准确（缓存失败不影响其 try/except 包裹）。⏳ batch 拉取未做，见上方"未做"说明。282 测试
通过（+7 新增）。

---

## D3 — Kronos batch 推理（旧 R5） — ✅ 已完成（2026-06-16）

**目标**：Kronos 本地推理是 premarket 最慢环节之一，当前逐标的串行（active watchlist≤30 已缓解）。

**实现记录**：
- 已确认 `.vendor/kronos/model/kronos.py` 的 `KronosPredictor.predict_batch(...)` 支持 batch 输入：
  `df_list` / `x_timestamp_list` / `y_timestamp_list` 同长输入，要求同一 batch 内历史窗口长度一致，
  返回顺序与输入顺序一致。
- `signals/kronos.py` 的 live payload 现在先逐 symbol 拉取/清洗 yfinance 历史数据，再按 `len(window)`
  分组调用 `predict_batch()`；正常 active watchlist 历史长度一致时，一组 symbol 只触发一次 Kronos
  推理调用。短历史标的（如近期 IPO）会进入自己的较短窗口 batch，不会被丢弃。
- batch 接口缺失或运行时失败（例如内存压力）时，自动回退到原来的逐标的 `predict()` 路径；只有单标的
  回退也失败时才把该 symbol 计入 `notes`/`data_status`，避免一个 batch 问题打废整批 active watchlist。

**涉及文件**：`signals/kronos.py`、`src/scripts/kronos/kronos_generate_signals.py`、测试（mock）。

**验收**：✅ mock 覆盖同窗口长度合批、不同窗口长度拆批、batch 失败回退逐标的三条路径；
`tests/scripts/kronos/test_kronos_generate_signals.py` 31 个测试通过。实际耗时下降取决于 active watchlist
规模、CPU/GPU/MPS 与模型配置；本次先保证调用数从“每 symbol 一次推理”降为“每窗口长度一组一次推理”，并保留
逐标的兼容回退。

---

## D4 — paper 部分成交模型（旧 R6 / docx P3） — ✅ 已完成（2026-06-15）

**目标**：当前 paper 只有「全成或不成」，加部分成交让仿真更真实。

**实现记录**：
- `paper/broker.py` 新增 `PAPER_PARTIAL_FILL`（默认 `0`，关）+ `PAPER_PARTIAL_FILL_MIN_RATIO`（默认
  0.3）+ `PAPER_PARTIAL_FILL_THRESHOLD_BPS`（默认 20）。`_partial_fill_ratio()` 是**确定性**模型
  （非随机）：quote 刚好打到 limit → 按 `MIN_RATIO` 成交；超过 limit `THRESHOLD_BPS` 以上 → 全部成交；
  中间线性插值。选确定性而非真随机是为了让部分成交测试可重复、不受 RNG seed 影响——roadmap 原文
  "概率/比例" 里选了"比例"那一半。
  - `_resolve_fill_quantity()`：`PAPER_PARTIAL_FILL=0` 时直接返回满量（`remaining_qty=0`），不调用
    `_partial_fill_ratio`——保证默认关闭时这条新代码路径完全不影响现有行为（已用全部 9 个既有
    `test_broker.py` 测试验证，一字未改全部通过）。
  - `apply_paper_intent()` 和 `reconcile_pending_paper_orders()` 都接入：成交记录新增
    `filled_qty`/`remaining_qty`/`original_quantity` 字段，状态在 `remaining_qty > 0` 时写
    `"partial_filled"`（不是 `"filled"`）；同一个 `order_id` 下追加一条 `event:
    "partial_remainder_pending"` 的 `status: "pending"` 续接记录，把 `quantity` 更新为剩余量——
    这样 `pending_paper_orders()`（取每个 order_id 最新一行）自然在下次 reconcile 时捡到剩余量
    重新尝试成交，不需要新的"待成交队列"概念。
- **未做（roadmap 已预告）**：`replay/analysis.py` 的 `_resolve_final_orders`/`fill_rate_summary`
  和 B3 `analytics.db` 的 `orders`/`decisions` 表目前只从 follow-up 事件里继承 `status`/`fill_price`，
  不继承 `filled_qty`；一个部分成交后还有余量的订单，在 replay/analytics 里会被计成"pending"且
  notional 计 0，而不是"部分成交"。这正是 roadmap 原文那条"注意：会改变 fill rate 统计语义，E1
  replay 需相应处理"——按计划留给 E1 阶段处理，不在这次 D4 范围内。

**涉及文件**：`paper/broker.py`、`tests/trading_agent/paper/test_broker.py`、`runtime.env`、`cli.py`。

**验收**：✅ 部分成交路径有测试（6 个新测试：ratio 计算 3 个、`apply_paper_intent` 部分成交 1 个、
reconcile 补齐剩余量 1 个、关闭时走原逻辑 1 个）；daily_usage（`paper_filled_notional` 按实际成交量算）
/positions（持仓按实际成交量算）记账正确；默认关闭时既有 9 个测试逐字不改全部通过，行为不变。
288 测试通过（+6 新增）。

---

# E 阶段 · 数据驱动校准（阻塞于 2–3 周 paper 数据）

> **数据要求**：策略有效性判断至少 10–15 个交易日，最好 20–30 个。样本不足时不要因一两天表现大幅调权重。
> 每天至少保留：`candidate_scores.json`、`risk_overlay.json`、`premarket_diagnostics.json`、
> `daily_plan.json`、`decisions.jsonl`、paper `orders.jsonl` / `equity_curve.jsonl`、
> `day_start.json` / `day_end.json` / `postmarket_summary.json`，以及 B1 的 `run_manifest.json`。

## E1 — replay 校准：forward/benchmark returns + 命中率 + attribution（旧 R1 + docx P1）— ✅ 机器已建（2026-06-16）

**实现记录（机器全部上线，统计显著性待数据）**：
- `replay/forward_returns.py`（keystone）：`compute_forward_return_records` 对每个历史 run date 的候选用
  **可注入的 price_loader**（默认 yfinance daily close，缺 yfinance 时优雅返回 `[]`）算 1/3/5 交易日
  forward return（entry 取 run date 当天或之后第一根 bar，未来 bar 不足标 `None` 而非猜）；
  `bucket_returns` 按分数分位数桶算均值 + 命中率（桶单调性 = 分数有没有用的最直接证据）。
- `replay/benchmark_returns.py`：SPY/QQQ/SMH/IWM 同期均值收益，区分 alpha 与 beta。
- `replay/component_attribution.py`：对每分量（candidate/trade_readiness/price_setup + dsa/technical/
  kronos/quote/catalyst）算 **Spearman IC**（信息系数）并按 |IC| 排名——**E2 权重重校准的直接依据**。
- `replay/setup_outcomes.py`：每个 setup（pullback/breakout）的成交里有多少先到 `target_1` 再到 `stop`
  （close 近似）；为此让 `paper/broker.py` 的订单记录**带上 setup_type/stop/target**（additive，不破坏现有）。
- `replay/calibration.py`：把上面四块汇总成 `runtime/analytics/calibration_report.{json,md}`；CLI
  `analytics calibrate`；**dashboard 第 8 个 Tab「Calibration」**（queries `calibration_report` + charts
  `calibration_view`），看哪个分数桶有效、哪个分量 IC 高、哪个 setup 赢、benchmark 对照。
- 全部**可离线单测**（注入假 loader，无网络）；只读，不碰交易路径。AppTest headless 渲染验证 8 Tab。
- 测试：`replay/test_forward_returns.py`（5）、`test_calibration_modules.py`（4）、`test_calibration_report.py`
  （2）+ dashboard/CLI 各新增。
- **未做（留作后续）**：① forward returns 还没进 analytics.db 表（目前是独立 report JSON，dashboard 直读，
  够用）；② G7 evaluator 还没把 forward returns 当 gate——因为 challenger 的 forward returns 需要先有
  **G9 challenger 隔离账本**，所以 G7 的接线等 G9。③ D4 部分成交 `filled_qty` 的 fill-quality 仍待补。

**目标**：把「凭感觉调参」变成「凭数据调参」。这是把系统从「能跑」推进到「能证明策略有效」的关键一步。

**关于「阻塞」的修正（我的判断）**：原标注「阻塞于 2–3 周 paper 数据」**只对统计显著性成立，对代码本身
不成立**。forward returns 是用 yfinance 对历史候选日**重算**的；候选分数（`candidate_scores.json`）、
决策 + blocked reason（`decisions.jsonl`）、intraday 六分量（`intraday_rankings.jsonl`，已补落盘）都已
持久化。所以**现在就该把 E1 机器建起来**，让每积累一天立刻可消费、并尽早暴露数据管道 bug——不要等三周。

**建议拆成 5 个纯函数模块（依赖顺序）**：
1. `replay/forward_returns.py`（**keystone**，其余都复用它）：对每个历史 run date 的候选，用 yfinance 拉
   该 symbol 之后 1/3/5 交易日收益；按 `candidate_total` / `trade_readiness_score` / `price_setup_score`
   分桶算均值 + 命中率（桶单调性是「这个分数有没有用」的最直接证据）。处理停牌/数据缺口/未来日不足。
2. `replay/benchmark_returns.py`：对照 SPY / QQQ / SMH / IWM 算同期收益，区分策略 alpha 与市场 beta。
3. `replay/component_attribution.py`：对每分量（dsa / technical / kronos / quote / catalyst / price_setup）
   算其得分与未来收益的相关性 / IC（信息系数），排名——这是 **E2 权重重校准的直接依据**。
4. `replay/setup_outcomes.py`：对 `pullback` / `breakout` 成交统计后续先到 `target_1` 还是 `stop`、
   entry-zone 命中率、breakout 成功率——回答「哪个 setup 真能赚」。
5. （near-miss 见 **E3**，复用 1 的 forward returns。）

**汇总输出 + 可视化**：
- `runtime/analytics/calibration_report.json` + `calibration_report.md`（人话版）；CLI `analytics calibrate`
  （或 `replay --forward-returns`）。
- **dashboard 新增 Calibration Tab**（C3 已是 7 Tab，加第 8 个）：看哪个分数桶最有效、哪个分量最有预测力、
  哪个 setup 最容易成交/最赚、哪个 blocked reason 是真保护 vs 错过机会。
- **接进 G7 evaluator**：把 forward returns 作为 challenger 的真实指标（目前 G7 把它标 unavailable）。

**涉及文件**：新增 `replay/forward_returns.py` / `benchmark_returns.py` / `component_attribution.py` /
`setup_outcomes.py`；扩展 `analytics/`（新表 + builder）、`dashboard/queries.py` + `app.py`（Calibration
Tab）、`growth/evaluator.py`（消费 calibration 指标）、`cli.py`、对应测试（yfinance 用 mock）。

**验收**：每桶样本数/均值/胜率可见且桶单调性可观测；分 setup_type 输出 win/loss/未决；每分量 IC 排名；
benchmark 对照可见；Calibration Tab 渲染（headless AppTest）；G7 能读到 forward-return 指标。

**注意**：forward returns 需联网 yfinance，测试用 mock；真实运行要处理停牌/数据缺口/未来交易日不足
（窗口不够的候选标 `pending` 而不是算错）。**部分成交语义**：D4 的 `filled_qty` 目前没传到 analytics，
E1 做 fill quality 时要一并处理（D4 实现记录里已预告）。

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

## E3 — near-miss tracking（docx P2）— ✅ 机器已建（2026-06-16，near-threshold 版）

**实现记录**：`replay/near_miss.py`：`load_trade_thresholds` 从每个 run 的 `risk_overlay.json` 读
`trade_score_threshold`；`near_threshold_analysis(records, thresholds, margin=5)` 把每个候选按 score vs
当天阈值分成 `cleared`（≥阈值）/ `near_miss`（[阈值−margin, 阈值)）/ `below`，复用 **E1 的
forward-return records**（只算一次）对比三类的后续收益 + 命中率——**直接回答「trade_threshold 是不是太严」**
（若 near_miss 收益 ≈ 或 > cleared，门槛在错过赢家）。已折进 `calibration_report` + dashboard Calibration
Tab。离线可测（`test_near_miss.py` 3 个）。

**未做（留作后续）**：「差一点到 entry zone / 被 no-chase block / reward_risk_too_low」这类**逐候选**
near-miss 需要先把 per-candidate 的 price/size 阶段 block reason 落盘（现在只有单条决策的聚合
blocked_reasons），是个独立的小落盘改动；本次先做了**完全可从现有数据算出**的 near-threshold 版。

**原计划（保留）**：在 decisions/replay 里标记 near-miss 类别，E1 forward returns 对其同样回算后续收益。

---

## E4 — bid/ask/spread 成交质量（docx P2，可选）

**目标**：更真实评估成交质量、滑点、流动性风险。paper 阶段弱依赖，可后置。

**具体步骤**：在 quote 采集处记录 bid/ask/spread，写入 orders/analytics，供成交质量分析。

**涉及文件**：`data/live_quotes.py`、`paper/broker.py`、`analytics/*`、测试。

**验收**：订单记录含 spread；replay 可输出按 spread 分组的滑点。

---

# F 阶段 · 后期 / 故意推后

## F1 — strategy compare — ✅ 已并入 C3 ⑤(a)（2026-06-16）

**目标**：对比不同 `strategy_id` 的 run count、fill rate、PnL、blocked reasons、平均分，判断新版本是否更好。

**现状**：已随 C3 落地——`dashboard/queries.py::strategy_comparison` 按 `runs.strategy_id` 聚合
runs/orders/decisions/candidates/intraday_rankings/paper_equity，dashboard ⑤ Strategy Comparison Tab
并排展示；有单测。F1 不再单列。**约束**：现仅 `baseline_v1` 一个版本，要等人工切过第二个 strategy
version（B2 registry 改 `active_strategy`）后才有第二行可比数据；UI/查询此前已就位。

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

---

# G 阶段 · 全模块自成长策略平台（paper / shadow only）

> 来源：`robinhood_codex_agent_strategy_lab_self_growth_plan` 第 12 章。在 B（manifest / registry /
> analytics）与 C（dashboard / replay）的地基上，把每个模块改造成
> **Observe → Diagnose → Propose → Validate → Shadow Test → Compare → Recommend → Human Approve**
> 的受控闭环。
>
> **核心规则（红线）**：所有模块都可以「自动提议实验」，但**不能自动改 champion 正式策略，绝不自动升级
> live**。Champion = 当前正式 paper 策略；Challenger = 自动生成、在 **shadow paper** 里评估的实验策略。
> 永远禁止自动修改：`TRADING_MODE` / `RISK_TIER` / `PAPER_RISK_TIER` / `KILL_SWITCH` / MCP 审批 /
> `place_equity_order` / `per_trade_risk_pct` / `max_daily_risk_pct` / `max_single_stock_weight`。
>
> **能力分级**：L1 自动诊断（只读，先做）→ L2 自动提议（只生成 YAML/报告）→ L3 shadow 多策略并跑 →
> L4 自动推荐 promote（人工确认）→ ~~L5 自动改 live~~（**明确禁止**）。
>
> **与现有代码的契合点（审查结论）**：
> - `policy/engine.py:generate_order_intent(inputs)` 是**纯函数**（`PolicyInputs → PolicyDecision`，
>   无 I/O）——这让 challenger 的 shadow 评估天然干净：只要能为 challenger 构造 `PolicyInputs`，就能
>   无副作用地算出它的决策。
> - **但** scoring/policy profile 当前通过 **`os.environ` 全局解析**（`load_scoring_profile` /
>   `load_policy_profile` 读 `SCORING_PROFILE`/`POLICY_PROFILE`；`apply_active_strategy_env_defaults`
>   写 env）。同一进程里并跑 champion + 多个 challenger 必须先**解除这个全局耦合**——即 **G-pre**。
> - `analytics.db`（B3）+ `replay/analysis.py`（`build_replay_report` / `discover_run_dates`）已是现成
>   的观察数据源，G1/G2 直接复用、不重新发明。
> - CLI（`cli.py` 的嵌套子命令）、dashboard（`app.py` 单页 + `queries.py` 只读函数）都易于扩展。

---

## G-pre — profile 解耦 + 实验账本隔离（可拓展性前置）— ✅ 已完成（2026-06-16）

**实现记录**：
- ✅ profile 按名解析：`planner/scoring_profiles.py` 的 `load_scoring_profile(config_dir, *,
  profile_name=None)` 和 `policy/profiles.py` 的 `load_policy_profile(agent_root, *,
  profile_name=None)` 都新增了 keyword-only 的 `profile_name`；传入时用它解析，否则回退原有的
  `os.environ` 行为。`policy/loaders.py` 的 `load_policy_inputs(..., policy_profile_name=None)` 把名字
  透传下去。默认 `None` 时行为逐字不变。
- ✅ 实验账本隔离 `build_experiment_paths(agent_root, *, run_date, strategy_id)`（`core/context.py`）：
  随 G6 一起落地，返回 `ExperimentPaths`，把 challenger 的 `shadow_decisions/orders/equity` 全根到
  `runtime/state/runs/<date>/experiments/<strategy_id>/`，与 champion 账本物理隔离。
- 测试：`tests/trading_agent/growth/test_profiles_by_name.py`、`test_shadow_runner.py`（路径隔离断言）。

**目标**：解除「策略配置只能经 `os.environ` 全局生效」的耦合，让任意 strategy 的 profile 可**按名解析**
并显式穿过 pipeline；并让 challenger 的 paper 账本写到**隔离目录**。这是 G6 shadow 的硬前置，也是整个
自成长平台「可拓展性 / 最优化」的关键一笔——小、向后兼容、越早做越好。

**具体步骤**：
1. `planner/scoring_profiles.py`：`load_scoring_profile(config_dir, *, profile_name: str | None = None)`——
   传入 `profile_name` 时用它，否则回退现有的 `os.environ["SCORING_PROFILE"]` 行为（默认 `None`，**零行为变化**）。
2. `policy/profiles.py`：`load_policy_profile(agent_root, *, profile_name: str | None = None)`——同上。
3. `policy/loaders.py`：`load_policy_inputs(..., policy_profile_name: str | None = None)`，把名字透传给
   `load_policy_profile`，不再隐式读 env。
4. `core/context.py`：新增 `experiments_dir`（`run_state_dir / "experiments"`）与一个
   `build_experiment_paths(agent_root, run_date, strategy_id)`，把 challenger 的
   `paper_*` / `decisions` / `orders` 根到 `experiments/<strategy_id>/` 子树，**与 champion 账本物理隔离**。

**涉及文件**：`planner/scoring_profiles.py`、`policy/profiles.py`、`policy/loaders.py`、`core/context.py`、
`strategy/registry.py`（可加 `resolve_strategy(agent_root, strategy_id)` 便于按 id 取 challenger 配置）、对应测试。

**验收**：传 `profile_name` 能在**不触碰 `os.environ`** 的前提下解析到对应 profile；现有调用方（默认
`None`）行为逐字不变、既有测试全绿；`build_experiment_paths` 的所有路径都落在 `experiments/<id>/` 下、
不与 champion 路径重叠。

**注意**：这是「YAGNI 例外」——它本身没有直接消费者（消费者是 G6），但它是被审查明确点名的**可拓展性
瓶颈**；建议作为 G 阶段第一笔重构，避免 G3/G4 校验 proposal 时再绕 env、G6 再被迫大改。

---

## G0 — growth_policy + validator 骨架（安全边界）— ✅ 已完成（2026-06-16）

**实现记录**：
- 新增 `src/config/growth_policy.json`（按计划用 JSON 而非 YAML，与 `policy_profiles.json` 等深层嵌套
  配置一致）：`enabled`/`mode: paper_only`/`proposal`/`allowed_mutations`（scoring/policy/setups 的
  `min`/`max`/`max_delta` + component_weights 和约束）/`forbidden_mutations`（红线清单）/`promotion_rules`。
- 新增 `growth/policy.py`：`load_growth_policy(agent_root)` 读取并合并安全默认值。`forbidden_mutations`
  做**并集处理**——文件可以扩充禁止清单，但永远无法删掉硬编码的红线（篡改/缺字段都会把默认红线并回来）。
- 新增 `growth/validator.py`：`validate_mutation(mutation, policy) -> (ok, violations)`，**失败即拒**——
  任何碰 `forbidden_mutations`、超 `min`/`max`、超 `max_delta`、权重和不在 `[0.95, 1.05]`、或 `mode`
  非 `paper_only` 的 mutation 一律拒绝。骨架已可用，完整 proposal 校验留给 G4。
- 测试：`tests/trading_agent/growth/test_growth_policy.py`（3）、`test_validator.py`（7）。

**目标**：先立**安全边界**再谈自成长。定义自成长允许/禁止修改的范围，所有 growth 命令默认 `paper_only`，
任何非 paper 改动一律 fail-closed。

**具体步骤**：
1. 新增 `src/config/growth_policy.json`（**用 JSON 而非 docx 原写的 yaml**——与 `policy_profiles.json`/
   `risk_tiers.json` 等**嵌套配置一致**，避免为 4 层嵌套手写脆弱的 YAML 解析器、也不引入 pyyaml 依赖）：
   `enabled`、`mode: paper_only`、`proposal`（频率限制）、`allowed_mutations`（scoring/policy/setups 的
   `min`/`max`/`max_delta`、`component_weights` 的和约束）、`forbidden_mutations`（上面那串红线）、`promotion_rules`。
2. 新增 `src/trading_agent/growth/policy.py`：`load_growth_policy(agent_root)` 读取并带默认值。
3. 新增 `src/trading_agent/growth/validator.py`（**骨架**，G4 再补全）：`validate_mutation(mutation, policy)
   -> (ok, violations)`，校验 forbidden 字段、范围、单次 delta、权重和、`paper_only`。

**涉及文件**：新增 `src/config/growth_policy.json`、`growth/__init__.py`、`growth/policy.py`、
`growth/validator.py`、对应测试。

**验收**：validator 能**拒绝**任何触碰 `forbidden_mutations`（TRADING_MODE/RISK_TIER/KILL_SWITCH/
place_equity_order/per_trade_risk_pct…）或超范围/超 delta 的 mutation；合法的 paper-only mutation 通过。

---

## G1 — growth observations（全局诊断）— ✅ 已完成（2026-06-16）

**实现记录**：
- 新增 `growth/observations.py`：`build_growth_context()` 复用 `replay/analysis.py` 的
  `build_replay_report` + `discover_run_dates`（只算一次，供所有 diagnoser 共享）；`global_observations()`
  检测 `low_trade_frequency`、`high_no_trade_rate`、`dominant_blocked_reason`、`high_pending_cancel_rate`、
  `missing_manifest`。每条 observation 是 `Observation` dataclass，含 `type/module/severity/evidence/
  suggested_action`。`write_growth_observations()` 落盘到 `runtime/analytics/growth_observations.json`。
- 阈值（`LOW_TRADE_FREQUENCY_PER_DAY` 等）放在模块级常量——它们调的是**诊断**而非任何交易参数；
  以后需要再提升到配置。
- CLI 新增 `growth observe`（含 `--since`/`--until`），`cli.py` 接线。
- 纯读、不写任何交易参数；`analyzer_failure_rate` 这条按计划留给后续 analyzers diagnoser。
- 测试：`tests/trading_agent/growth/test_observations.py`（2）、`tests/trading_agent/test_cli.py` 新增
  `growth observe` 落盘测试。

**目标**：读 `analytics.db` + replay report + run state，产出 `runtime/analytics/growth_observations.json`。
**不改变任何交易行为。**

**具体步骤**：新增 `growth/observations.py`：检测 `low_trade_frequency`、`high_no_trade_rate`、
`dominant_blocked_reason`、`high_pending_cancel_rate`、`missing_manifest`、`analyzer_failure_rate`；每条
observation 含 `type`/`module`/`severity`/`evidence`/`suggested_action`。CLI 新增 `growth observe`。

**涉及文件**：新增 `growth/observations.py`，改 `cli.py`，对应测试。

**验收**：对 fixture run 目录产出结构化 observations；阈值可配；纯读、不写任何交易参数。

---

## G2 — 模块 diagnosers + dashboard Self-Growth Lab — ✅ 已完成（2026-06-16）

**实现记录**：
- 新增 `growth/diagnosers/`，用**注册表模式**（`DIAGNOSERS: dict[str, Callable[[GrowthContext],
  list[Observation]]]`），`run_all(ctx)` 把共享的 `GrowthContext` fan-out 给每个 diagnoser（只读一次
  analytics，避免重复 I/O）。首批两个代表性 diagnoser：`scoring`（从 `premarket_diagnostics.json` 的
  warnings 检测反复出现的 theme/speculative 集中度）、`setups`（从 blocked_reason 检测 entry/RR 闸主导
  no-trade）。新增模块只需 drop-in 一个文件并注册一行，不动其它 diagnoser（开闭原则）。
- 结果写入 `growth_observations.json` 的 `modules` 字段。
- dashboard：`dashboard/queries.py` 新增只读 `growth_observations(agent_root)`；`charts.py` 新增
  `growth_observations_view(payload)`；`app.py` 加一段 `st.header("Self-Growth Lab (read-only
  diagnostics)")`。
- 测试：`tests/trading_agent/growth/test_diagnosers.py`（3）、`tests/trading_agent/dashboard/
  test_queries.py` 新增 2 个 growth 查询测试。

**目标**：把全局诊断细化到**每个模块**（watchlist / analyzers / features / scoring / setups / risk / paper /
prompt），并在 dashboard 加**只读** Self-Growth Lab 页面展示。

**具体步骤**：新增 `growth/diagnosers/`，用**可拓展的注册表模式**（`DIAGNOSERS: dict[str, Callable[
[GrowthContext], list[Observation]]]`），共享上下文只算一次再 fan-out（**最优化**：避免每个 diagnoser 各
读一遍 analytics）。结果写入 `growth_observations.json` 的 `modules` 字段。dashboard `queries.py` 加
`growth_observations()` 只读函数 + `app.py` 加一段 `st.header("Self-Growth Lab")`。

**涉及文件**：新增 `growth/diagnosers/*`、改 `growth/observations.py`、`dashboard/queries.py`、
`dashboard/charts.py`、`dashboard/app.py`、对应测试。

**验收**：每模块输出 `type/severity/evidence/suggested_action`；新增一个 diagnoser 只需注册、不动其它；
dashboard 页面只读。

> **G0–G2 是「下一步」的安全只读地基，已给出逐任务 TDD 实现计划**：见
> [`superpowers/plans/2026-06-16-self-growth-platform-g0-g2.md`](./superpowers/plans/2026-06-16-self-growth-platform-g0-g2.md)。

---

## G3 — proposal generator（依赖 G0–G2）— ✅ 已完成（2026-06-16）

**实现记录**：
- 新增 `growth/proposals.py`：纯函数 `proposals_from_observations(observations, policy, current, *,
  run_date)` 用**可扩展的规则注册表**（`PROPOSAL_RULES`，风格同 diagnoser 注册表）把 observation 映射成
  候选 mutation。首批两条规则：`low_trade_frequency`/`high_no_trade_rate` → 把 `scoring.trade_threshold`
  降一个 `max_delta` 步（多成交）；`recurring_theme_concentration` → 把 `scoring.watchlist_threshold`
  升一步（收紧 watchlist）。两个都是 `scoring_profiles.yaml` 真实存在的、且在 `growth_policy` 白名单里的字段。
- **安全**：每个候选 mutation 都过 G0 的 `validate_mutation`，只有 `ok=True` 的才会被 emit；步进会按
  `min`/`max` 夹紧，夹到边界变成 no-op 的直接丢弃；emit 数量受
  `growth_policy.proposal.max_new_proposals_per_week` 限制（完整跨 run 频率控制留给 G5 队列）。
- **输出格式调整**：roadmap 原写 YAML，这里改用 **JSON + Markdown**（与 G0 选 JSON 同理——proposal 是会被
  G4/G5 机器回读的嵌套结构，JSON 更稳、与 `growth_policy.json` 一致；`.md` 给人看 rationale）。写到
  `runtime/strategy_proposals/<run_date>/proposal_NNN_<module>_<field>.{json,md}`。
- CLI 新增 `growth propose`（`--since`/`--until`）。**不碰任何 champion 配置**：proposal 只落在
  `runtime/strategy_proposals/` 下，交易路径不读它。
- 测试：`tests/trading_agent/growth/test_proposals.py`（8，含纯函数规则、no-op 夹紧、频率上限、
  write 落盘 + champion 配置零改动、真实仓库 smoke）；`test_cli.py` 新增 `growth propose` 测试。

**原计划（保留）**：

**目标**：把 observations 转成 strategy proposal，但**只写** proposed YAML/Markdown，**不自动启用**。

**具体步骤**：新增 `growth/proposals.py`，输出 `runtime/strategy_proposals/<YYYY-MM-DD>/proposal_*.yaml`
和 `.md`；proposal 只能改 `growth_policy` 白名单参数（threshold / component weights / enabled_setups /
prompt_pack / watchlist cap / feature lookback）。CLI 新增 `growth propose`。

**验收**：proposal 只触及白名单字段；champion 行为零变化。

---

## G4 — proposal validator（完整校验）— ✅ 已完成（2026-06-16）

**实现记录**：`growth/validator.py` 新增 `validate_proposal(proposal, policy)`，把 `validate_mutation`
包成机器可读的 `validated`/`rejected` 裁决；`growth/proposal_review.py` 的 `validate_proposal_file` /
`validate_proposals_dir` 读 proposal JSON、写**同名 `*_validation.json`**，原 proposal 文件零改动。
CLI `growth validate <file|dir>`。仍不启用任何东西。测试 `test_proposal_validation.py`（5）。

**原计划（保留）**：

**目标**：把 G0 的 validator 骨架补全，对 proposal 做完整安全校验。

**具体步骤**：`growth/validator.py` 读 `growth_policy.json`，校验权重和、单次 delta、threshold 范围、
禁止字段、`paper_only`；失败标 `rejected` 并写原因，通过标 `validated`（**仍不自动启用**）。CLI
`growth validate <proposal.yaml>`。

**验收**：能拒绝 live/risk/MCP/safety 相关 mutation；输出 `*_validation.json`。

---

## G5 — experiment queue — ✅ 已完成（2026-06-16）

**实现记录**：`src/config/strategy_experiments.yaml`（扁平 YAML，registry 风格的极简 parser + writer）+
`growth/experiment_queue.py` 实现生命周期状态机 `proposed → human_approved → active_shadow →
ready_for_review → promoted/rejected/archived`。`add_experiment`（从 proposal 入队）、`approve`（→
active_shadow）、`reject`、`archive`、`mark_ready_for_review`；非法转移抛 `ExperimentTransitionError`。
**红线**：`approve` 只推到 `active_shadow`，有测试断言它**绝不改** `strategy_registry.yaml` 的
`active_strategy`。CLI `growth experiments list/add/approve/reject/archive`。测试 `test_experiment_queue.py`（8）。

**原计划（保留）**：

**目标**：管理实验生命周期 `proposed → human_approved → active_shadow → ready_for_review →
promoted/rejected/archived`。

**具体步骤**：新增 `src/config/strategy_experiments.yaml`（扁平结构，沿用 registry 风格的极简 YAML
解析）+ `growth/experiment_queue.py`；CLI `growth experiments list/approve/archive`。**approve 只允许启用
shadow paper，绝不切 `active_strategy`。**

**验收**：approve 只把状态推到 `active_shadow`，不动 `strategy_registry.yaml` 的 `active_strategy`。

---

## G6 — shadow paper runner — ✅ 已完成（2026-06-16，决策级）

**实现记录**：`growth/shadow_runner.py`。对每个 `active_shadow` challenger：用 G-pre 的按名 profile 解析
+ 把实验的 scoring 数值 override 应用到 champion scoring profile，调用**纯函数** `build_risk_overlay`
（复用 champion 已落盘的 premarket 产物，不写 champion overlay）算出 challenger 的 risk_overlay，
`build_challenger_inputs` 把它换进 champion `PolicyInputs` 的副本，跑纯函数 `generate_order_intent`，
把决策 append 到隔离的 `experiments/<id>/shadow_decisions.jsonl`。已接入 intraday（best-effort，
challenger 出错绝不影响 champion）+ CLI `growth shadow`。
- **范围边界**：本次 shadow **只产决策流**（`shadow_decisions.jsonl`）。`shadow_orders/equity` 的 paper
  仿真需要让 paper broker 写到隔离账本，留待后续；G7 因此暂以决策级指标对比，fill rate / drawdown 标为
  unavailable。
- **验收**：champion 的 `paper/*` 与 `decisions.jsonl` 一字不变（有测试断言）；challenger 产物只落在
  `experiments/<id>/`；同输入可复现。测试 `test_shadow_runner.py`（3）+ intraday 集成测试（隔离落盘 1）。

**原计划（保留）**：

**目标**：用相同输入把 `active_shadow` 的 challenger 在**隔离账本**里跑出 shadow 决策/订单/权益曲线，
**绝不影响 champion paper account**。

**具体步骤**：新增 `growth/shadow_runner.py`。每次 intraday 之后，对每个 active_shadow strategy：用 G-pre
的按名 profile 解析 + `build_experiment_paths` 构造该 challenger 的 `PolicyInputs`，调用纯函数
`generate_order_intent`，把结果写 `runtime/state/runs/<date>/experiments/<strategy_id>/`下的
`shadow_decisions.jsonl` / `shadow_orders.jsonl` / `shadow_equity_curve.jsonl`。
- 仅 policy_profile/tier 不同的 challenger：复用 champion 的 premarket 产物（daily_plan/risk_overlay/
  candidate_scores），只换 policy_profile + 隔离账本，**最省**。
- scoring_profile/watchlist 不同的 challenger：需用该 challenger 的 scoring_profile 重算 scoring +
  risk_overlay（复用 `planner/scoring.py` / `risk_overlay.py`，它们也读同一批 signal 文件）。

**验收**：champion 的 `paper/*` 一字不变；challenger 产物只落在 `experiments/<id>/`；同输入可复现。

---

## G7 — evaluator + promotion recommendation — ✅ 已完成（2026-06-16）

**实现记录**：`growth/evaluator.py`。champion 指标复用 `build_replay_report`（fill rate / no-trade rate /
blocked reasons）；challenger 指标从 `shadow_decisions.jsonl` 跨 run date 聚合（would-trade、no-trade
rate、shadow_days、reason 分布）。`_recommendation` 按 `growth_policy.promotion_rules`（`min_shadow_days`、
`fill_rate_not_worse_than_champion`、`max_drawdown_not_worse_than_champion`、`require_human_final_approval`）
裁决——**任何未满足的规则或缺失的指标都是 blocking reason**，所以在 shadow 订单/权益仿真和 E1 forward
returns 到位之前，永远不会给出 promote 推荐（=「未满足时不出建议」）。产出 `experiment_report.json` +
`promotion_recommendation.md`。CLI `growth evaluate` / `growth recommend`。测试 `test_evaluator.py`（4，
含放宽规则后的正向推荐路径 + 仍需人工最终批准）。

**原计划（保留）**：

**目标**：对比 champion vs challengers，**只推荐、不自动 promote**。

**具体步骤**：新增 `growth/evaluator.py`，指标：fill_rate、no_trade_rate、blocked_reason、forward returns
（复用 E1）、max_drawdown、trade frequency、safety violations；产出
`runtime/analytics/experiment_report.json` + `promotion_recommendation.md`。CLI `growth evaluate` /
`growth recommend`。

**验收**：报告并排展示 champion/challenger 指标；`promotion_rules`（`min_shadow_days` 等）未满足时不出
promote 建议。

---

## G8 — human-in-the-loop promotion — ✅ 已完成（2026-06-16）

**实现记录**：`growth/promotion.py`。`build_promotion_check(agent_root, experiment_id)` 校验 challenger
处于 `ready_for_review` 且 evaluator 推荐，给出 `eligible` + blocking reasons，并生成**可直接粘贴**的
changelog 草稿（匹配 `docs/strategy-changelog.md` 格式）和 `strategy_registry.yaml` 条目草稿；
`write_promotion_check` 落到 `runtime/analytics/promotion_drafts/<id>.md`。CLI `growth promote check <id>`。
**红线**：命令**从不**修改 `strategy_registry.yaml` / `active_strategy`（有测试断言 registry 字节不变）——
真正 promote 永远是人工手改 YAML。测试 `test_promotion.py`（5）。

**最终边界（已落地）**：AI 提议 → Python 校验 → paper 实验入队 → shadow 隔离并跑 → evaluator 并排对比 →
人工 promote check 出草稿 → **人类手改 YAML 决定 promote** → live 永远不能自动升级。

**原计划（保留）**：

**目标**：真正切换 `active_strategy` **必须由人工改 `strategy_registry.yaml`**；命令只做校验 + 文档生成。

**具体步骤**：新增 `strategy promote check` 命令（只 validation + 生成 changelog 草稿）；每次 promote 必须
写 `docs/strategy-changelog.md`（已有 B4 的测试强制每个 strategy version 有 changelog 条目）。

**验收**：命令本身**从不**修改 `active_strategy`；promote 后 changelog 有对应条目。

**最终边界**：AI 建议 → Python 校验 → paper 实验 → shadow 并行比较 → dashboard 展示 → **人类决定
promote** → live 永远不能自动升级。

---

## G9 — challenger 隔离 paper 账本（shadow orders/equity）— ✅ 已完成（2026-06-16）

**实现记录**：
- `core/context.py` 新增 `build_experiment_runtime_paths`：返回一个 RuntimePaths，**只把 paper_* 和
  daily_usage 改到 `experiments/<id>/paper/`**，其余路径与 champion 共享（用 `dataclasses.replace`）。
- `paper/broker.py` 的 5 个公开函数（`record_paper_day_start/end`、`apply_paper_intent`、
  `reconcile_pending_paper_orders`、`pending_paper_orders`）新增可选 `paths_override`；默认 = 现有 champion
  行为（既有测试逐字不变），内部 `record_paper_day_start` 调用也转发 override，**champion 账本永不被碰**。
- `policy/loaders.py` 暴露公开 `hydrate_paper_ledger(inputs, paths)`。
- `growth/shadow_runner.py`：paper 模式下，challenger 先 seed 自己的 day_start、reconcile 自己的 pending、
  hydrate 自己的 account/positions/pending（**从自己的账本决策、下单**），would_trade 则 `apply_paper_intent`
  写到隔离账本。
- `growth/evaluator.py`：`challenger_ledger_metrics` 从 `experiments/<id>/paper/` 读出 challenger 的**真实**
  fill rate / max drawdown / realized PnL（champion 也补了 max drawdown），fill-rate 与 drawdown 两个
  promotion gate 现在真能比较，不再标 `unavailable`。
- 测试：`test_isolated_ledger.py`（2）、`test_shadow_runner.py`（隔离账本断言）、`test_evaluator.py`
  （真实 ledger 指标）、intraday 集成测试。**champion paper/* 一字不变**有断言。

**未做**：challenger 的 forward returns 仍待——它依赖把 E1 的 forward-return 计算接到 challenger 的成交上，
属于 E1×G9 的交叉接线，留作后续。

**目标**：让 shadow challenger 不只产决策流，而是有**完整隔离的 paper 账本**，G7 才能拿到 challenger 的
真实 fill rate / drawdown / PnL / turnover，从而给出有意义的 promote 推荐。

**背景**：G6 当前只写 `experiments/<id>/shadow_decisions.jsonl`；`shadow_orders.jsonl` /
`shadow_equity_curve.jsonl` / `account.json` / `positions.json` 未做，所以 G7 把 challenger 的 fill
rate / drawdown 标 `unavailable`，永远不出 promote 建议。

**具体步骤**：让 `paper/broker.py` 的 `apply_paper_intent` / `reconcile_pending_paper_orders` /
`record_paper_day_start/end` 接受**路径覆盖**（或一个 `ledger_root`），shadow runner 用 G-pre 的
`build_experiment_paths` 把 challenger 的 paper 写到 `experiments/<id>/paper/` 下，与 champion 物理隔离。
G7 evaluator 改读 challenger 账本算 fill rate / max drawdown / realized PnL。

**涉及文件**：`paper/broker.py`（路径参数化）、`growth/shadow_runner.py`、`growth/evaluator.py`、
`core/context.py`（`build_experiment_paths` 扩展 paper 子路径）、测试。

**验收**：challenger 的 `experiments/<id>/paper/*` 完整且与 champion 隔离；G7 报告含 challenger 的真实
fill rate / drawdown / PnL；champion `paper/*` 一字不变（断言）。

---

## B5 — strategy_registry.watchlist → active watchlist resolver — ✅ 已完成（2026-06-16）

**实现记录**：`data/universe.py` 的 `parse_active_watchlist(config_dir, *, watchlist_filename=None)`
现在先用 `_resolve_watchlist_filename` 读 `load_active_strategy().watchlist` 解析实际文件名（从 config_dir
反推 agent_root），再读那个文件；缺 registry / 字段是默认 / 解析失败时回退 `active_watchlist.txt`，
文件缺失再回退 `universe.txt`——**完全向后兼容**。新增显式 `watchlist_filename` override 供以后 challenger
用自己的 watchlist。`universe_meta.json` 的 `_comment` 记录了可选的选股层扩展字段（layer/supply_chain/
risk_tags），但**没有凭空给 88 个标的编造分类数据**（没有消费者，YAGNI）。测试
`test_universe_watchlist.py`（5：默认/切换/override/缺文件回退/默认字段向后兼容）。

**未做（有意推后）**：「shadow runner 里 challenger 用其自己的 watchlist」**没接**——当前 shadow 复用
champion 的 premarket `candidate_scores`（那是按 champion watchlist 算的），换 watchlist 需要按 challenger
watchlist **重跑 premarket 打分**（G6 的"贵路径"），且 G3 目前根本不生成 watchlist 类实验。等这两者就绪
再接，避免现在加一个不起作用的接线。

**目标**：让不同 strategy version 能用不同的 watchlist 文件。现在 `strategy_registry.yaml` 的 `watchlist`
字段只是记录，没有反向接线——切换 `active_strategy` 不会真的切 watchlist（B2 实现记录里已点名这是有意
留的边界）。

**具体步骤**：`data/universe.py` 的 `parse_active_watchlist()` 改为先读 `load_active_strategy().watchlist`
解析出实际文件名（回退现有 `active_watchlist.txt`）；shadow runner 里 challenger 用其自己的 watchlist。
配套：`universe_meta.json` 增补 `theme` / `layer` / `supply_chain` / `risk_tags` 字段，支持更细的选股层
实验（见 playbook 的"选股层"）。

**涉及文件**：`data/universe.py`、`strategy/registry.py`、`growth/shadow_runner.py`、`universe_meta.json`、测试。

**验收**：切换 `active_strategy` 到一个带不同 `watchlist` 的版本后，active watchlist 真的随之改变；
默认/缺字段时退回 `active_watchlist.txt`，行为不变。
