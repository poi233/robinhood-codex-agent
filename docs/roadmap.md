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
> **五条贯穿原则**
> - **不用魔数换魔数**：任何新权重/阈值在固化前必须经回看数据校准。
> - **可追溯优先**：先有 `run_manifest` + `analytics.db`，再做任何会改变行为的改动（token 优化、权重校准
>   都应记为一个**新的 strategy version**），否则积累的 paper 数据无法横向对比。
> - **paper-only 安全**：review/live 继续不接线，dashboard 第一版只读、不可改交易参数。
> - **自成长受控**：自成长只能在 paper / shadow paper / replay 内运行，**只提议、不自动改 champion，
>   绝不自动升级 live**（不动 TRADING_MODE / RISK_TIER / KILL_SWITCH / 真实下单）。详见 G 阶段。
> - **大模块一律 feature-flag 门控、默认关、做完才翻、稳定后清除**：每个会接进 premarket/intraday 热路径
>   的大模块都用一个 `ENABLE_<MODULE>` env flag（**默认 0**）包起来，**无论做到哪一步，flag 关着时新代码
>   路径完全不被调用、对现有系统零影响**；整模块做完 + 测试 + 验收后才把默认翻成 1（或由人工开）；上线
>   稳定一段时间后再做一个清理任务**移除 flag、让行为变成无条件**。详见下方「增量开发与 feature flag 约定」。

---

## 增量开发与 feature flag 约定（贯穿全局）

> 目标：**每个大模块都可以做到一半，但只有整模块完全做完才被真正使用；中间任何状态都不影响已有系统运行。**
> 复用代码库现成的 `ENABLE_<X>` env-flag 习惯（`ENABLE_DSA_SIGNAL_LAYER` / `ENABLE_KRONOS_SIGNAL_LAYER` /
> `ENABLE_TECHNICAL_FEATURES_PRECOMPUTE` / `ENABLE_OHLCV_CACHE` … 都是这套）。

**生命周期（每个大模块都走这四步）**：
1. **建设期（flag 默认 0 = 关）**：模块代码全部新增在**独立文件/包**里，只在**热路径的接入点**用一个
   `if os.environ.get("ENABLE_<MODULE>", "0") == "1":` 包住调用。flag 关着 → 新代码路径**完全不被调用**，
   premarket/intraday/scoring/paper 一字不变。做到一半也安全。
2. **完成期（验收后翻默认）**：整模块（计算 + 落盘 + 接校准/ dashboard + 测试 + 文档）都做完、既有测试
   全绿、`doctor` 能回显该 flag 后，才把默认从 `0` 改成 `1`（或交给人工在 `runtime.env.local` 开）。
3. **稳定期**：上线观察一段时间，确认无回归。
4. **清理期（移除 flag）**：稳定后做一个独立的 cleanup 任务——**删掉 flag 判断、让行为无条件生效**，
   避免 flag 长期堆积。清理本身也是一次可回退的小改动。

**硬约束（保证"半成品零影响"）**：
- **默认 0**：任何未完成的大模块，flag 默认必须是关。
- **加法式、隔离**：新模块只**新增**文件 + 新增输出产物（`runtime/...`）+ 新增 dashboard 区块；**绝不修改**
  现有 scoring / risk_overlay / paper broker / decision 路径的行为（除了那一行 `if flag` 包住的接入点）。
- **只读 / 只写新产物**：和 calibration / growth 一样，新模块只读历史 + 写自己的新文件，不碰 champion
  的 scoring/paper/decisions。
- **既有测试逐字不变全绿**：证明 flag 关着时行为零变化；新代码自己有独立测试（flag 开/关两条路径都测）。
- **`doctor` 回显**：每个 flag 加进 `cli.py` 的 doctor 输出，随时能看当前开关状态。

**各模块的 flag 一览（建设期默认全 0）**：

| 模块 | flag | 接入点 | 翻默认的完成门槛 |
|---|---|---|---|
| ~~H2 价量因子层~~ | ~~`ENABLE_PRICE_FACTOR_LAYER`~~ | premarket local 因子层 | ✅ 已完成并清除 flag（无条件运行；write-only，不进 champion 打分） |
| ~~H3 AI 结构化 schema~~ | ~~`ENABLE_AI_STRUCTURED_SIGNALS`~~ | 原计划：各 AI prompt 的输出契约 | ✅ **改走 normalizer 路线，flag 未用**（2026-06-17）：不动 prompt、只读已有输出落 advisory `ai_signals.json`，不碰热路径故无需 flag（同 H2 最终形态） |
| H4 shadow re-score | `ENABLE_SHADOW_RESCORE` | shadow runner 的 challenger 重打分路径 | factor/analyzer/setup 类 challenger 能在隔离账本跑通 |
| H6 evidence-based proposals | `ENABLE_EVIDENCE_PROPOSALS` | growth propose 的证据校验 | ✅ **gate 已建（2026-06-17，默认 0）**：开时 proposal 必须带 calibration/weight evidence 才生成；更多 evidence 类型增量加后翻默认 |

> 注：纯手动命令（`analytics calibrate`、`growth observe/propose`）和 shadow-only 路径**天然隔离**（不在热
> 路径、不动 champion），可以不强制 flag；**强制 flag 的是会接进 premarket/intraday 热路径的模块**（H2/H3/H4）。
> 已完成的 E1/E3/G9/C3/B5 都属于"手动命令或 shadow-only"，本来就零热路径影响。

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
| | E2 | 评分 / 价格 setup 权重校准 | 旧 R2 | 🟡 **建议机器已建（2026-06-17）**：`analytics weight-suggestion`（IC 倾斜建议，只产建议绝不自动改）；应用待数据 + 人工 B2/G6/G8 |
| | E3 | near-miss tracking | docx P2 | ✅ **机器已建（2026-06-16，near-threshold 版）**；✅ per-candidate block 已开始落盘（2026-06-17，decision 增 `per_candidate_blocks`）；entry-zone/no-chase **分类分析**待 paper 数据积累 |
| | ~~E4~~ | bid/ask/spread 成交质量 | docx P2 | ✅ **已完成（2026-06-17）**：book 捕获 + 逐单 slippage + `analytics fill-quality` 保守成交敏感性（无 flag，capture additive + replay 只读） |
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
| **H 量化因子 + AI 归因 + 校准升级**（ChatGPT 新方向，见下方 H 段） | H0 | calibration foundation（ChatGPT Phase 1） | ChatGPT | 🟢 **基本已完成**（=E1/E3 + C3 Calibration tab）；缺口见 H1 |
| | ~~H1~~ | 校准补强（21/63d horizon · per-candidate 超额收益 · 多 horizon Rank IC + t-stat） | ChatGPT P1 残项 | ✅ **已完成（2026-06-17）**：核心三项落地；更全 near-miss 降级给 E3（需 per-candidate block 落盘） |
| | H2 | **价量因子层**（factors_price + factor_alpha + factor_profiles，ChatGPT Phase 2） | ChatGPT | ✅ **已完成并上线（2026-06-16）**：flag 已开启并**清除**，因子层无条件每天 premarket 落盘（write-only，不进 champion 打分） |
| | ~~H3~~ | AI signal 结构化 + 归因 + ablation（ChatGPT Phase 3） | ChatGPT | ✅ **已完成（2026-06-17，step 1+2+3）**：标准化 AI 信封 + 校验 + normalizer + `ai_signals.json`（write-only advisory，无 flag）；`analytics ai-signal-study`（calibration/方向/code lift）+ `analytics ai-ablation`（每层 marginal IC + AI-vs-因子） |
| | H4 | factor/analyzer/setup shadow 策略（ChatGPT Phase 4 增量） | ChatGPT | ⏳ 依赖 H2 + premarket re-score 路径 |
| | ~~H5~~ | dashboard calibration 子视图扩展（ChatGPT Phase 5 增量） | ChatGPT | ✅ **已完成（2026-06-17）**：Calibration tab 加 fill-quality（E4）+ AI signal study + AI ablation（H3）+ 多 horizon Rank IC/t-stat（H1）子视图；只读、headless 渲染验证 |
| | H6 | self-growth 用 calibration/factor/AI evidence 生成 proposal（ChatGPT Phase 6） | ChatGPT | 🟡 **evidence gate 已建（2026-06-17）**：`ENABLE_EVIDENCE_PROPOSALS` 下 proposal 必须带 calibration/weight evidence 才生成（只更严不更松）；更多 evidence 类型增量加 |
| | H7 | fundamental quality 层（ChatGPT Phase 7） | ChatGPT | ⛔ 故意推后（数据更复杂） |
| | H8 | earnings / analyst revision 事件层（ChatGPT Phase 8） | ChatGPT | ⛔ 故意推后 |
| **I 运维与自动化** | ~~I1~~ | 夜间分析/自成长自动化 cron（收盘后自动跑 analytics/calibrate/growth） | 用户新增 | ✅ **已完成（2026-06-17）**：`run_nightly_analysis.sh` best-effort 批处理 + cron/launchd 示例 + `ENABLE_NIGHTLY_ANALYSIS`（doctor 回显） |
| | ~~I2~~ | 每天一份分析快照（`history/<date>/` + nightly_summary.json） | 用户新增 | ✅ **已完成（2026-06-17）**：`analytics snapshot`，幂等归档 + headline summary |
| | ~~I3~~ | 拿到趋势的功能（`analytics trend` + `build_trend` 纯函数） | 用户新增 | ✅ **已完成（2026-06-17）**：`analytics trend` + `build_trend` 纯函数，逐日时间序列 |
| | ~~I4~~ | dashboard 可视化（新鲜度 + 日期回看每天结果 + 趋势折线） | 用户新增 | ✅ **已完成（2026-06-17）**：第 9 个 Trends tab（新鲜度 + 日期回看 + 趋势折线） |
| **J 评审驱动修正（2026-06-16 外部评审）** | J1 | 止损/退出逻辑校正 + strategy.md 一致性（**live 硬前置**） | 评审 | ⏳ 重要（live 前必修；诚实 paper 校准也需要） |
| | J2 | Codex-facing 文档旧路径统一（risk.md / strategy.md / universe.txt / allowlist.txt / dsa_strategy_weights.json） | 评审 | ✅ **已完成（2026-06-16）** |

> **新旧编号对照**：R1→E1（增 benchmark returns）、R2→E2、R3→A3、R4→D2、R5→D3、R6→D4、R7→F2；
> token 优化设计→D1；docx 的 run_manifest→B1、registry→B2、analytics.db→B3、changelog→B4、
> dashboard→C1、theme 诊断→C2、forward/benchmark/attribution→E1、near-miss→E3、bid/ask/spread→E4、
> strategy compare→F1、config editor→F3。

---

## 已完成项详细记录 → 见归档文件

> A/B/C 三阶段、D1/D3/D4、E1/E3、F1、G 阶段（G-pre–G9）、B5 **全部已完成**；其详细实现记录已移到
> [`roadmap-archive.md`](./roadmap-archive.md)，本文件不再展开。**本文件保留**：优先级总表 + 各贯穿原则/
> 约定 + 当前焦点 + **未完成/规划项**（D2、E2/E4、F2/F3、H、I 阶段）的详细内容。状态以上方总表为准。

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

7. **新方向 · H 阶段（量化因子 + AI 归因）**：评估了用户带来的 ChatGPT 计划，Phase 1（校准地基）/ shadow
   隔离账本 / dashboard calibration tab 之前已做掉一大半。**H2 价量因子层已完成并上线（flag 已开启+清除，
   无条件每天落盘）**。**H1 校准补强已完成（2026-06-17）**（21/63d horizon + 逐候选超额 + 多 horizon Rank
   IC/t-stat）。**E4 成交质量已完成（2026-06-17）**（book 捕获 + 逐单 slippage + `analytics fill-quality`
   保守成交敏感性）。详见文末 **H 阶段** 与 **E4**。

8. **外部评审确认（2026-06-16）+ 收敛后的推荐序**：一次外部评审确认了方向（paper-only / 安全边界 / H2 为
   下一步都对），并提出两点收敛——① **E4 成交质量上调到 P1.5**（paper 成交偏乐观会虚高 edge，须在信任校准
   结论前补，见 E4）；② **live 前必修止损/退出逻辑**（doc 说「跌 3% 只 alert」与 code 实际不一致、分级减仓
   事实失效、无兜底硬止损，见 **J1**）。收敛后的推荐序：
   **稳定 paper 10–30 天（冻结 baseline）→ H2 因子层只落盘 ✅ → H1 校准补强 ✅ → E4 成交质量 ✅ → 再
   shadow challenger / 权重调整**。J2 文档旧路径统一已完成。下一步候选见下方总表（E2 权重重标定需先攒 15–30
   交易日数据；H3 AI schema 可现在做以攒数据）。

**贯穿纪律**：冻结 baseline → 一次一个实验 → 只用数据 promote（≥10 shadow 日、fill rate / drawdown /
forward return 不劣于 champion、无 safety violation、人工 approve）；**先建产数据的代码、让积累立刻开始，
吃数据的分析等数据到位**；**别急 live、别再堆 fancy 自成长**（评审与本焦点一致）。

---

# D 阶段 · 工程优化（不阻塞，边等数据边做）

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

# E 阶段 · 数据驱动校准（阻塞于 2–3 周 paper 数据）

> **数据要求**：策略有效性判断至少 10–15 个交易日，最好 20–30 个。样本不足时不要因一两天表现大幅调权重。
> 每天至少保留：`candidate_scores.json`、`risk_overlay.json`、`premarket_diagnostics.json`、
> `daily_plan.json`、`decisions.jsonl`、paper `orders.jsonl` / `equity_curve.jsonl`、
> `day_start.json` / `day_end.json` / `postmarket_summary.json`，以及 B1 的 `run_manifest.json`。

## E2 — 评分 / 价格 setup 权重校准（旧 R2）— 🟡 建议机器已建（2026-06-17），应用待数据 + 人工

**目标**：把 scoring 五分量权重（dsa 0.25 / technical 0.30 / kronos 0.15 / quote 0.10 / catalyst 0.20）
从「保守先验」改成「数据校准值」。

**已完成（建议机器，安全）**：`analytics/weight_suggestion.py` + `analytics weight-suggestion`——读 E1
calibration 的 component IC，按 IC 把权重往预测力强的分量倾斜（正 IC 加权、负 IC 减权、归一化合计 1.00、
`--damping` 控制幅度），产出 `weight_suggestion.json`（当前 vs 建议 + 逐分量 IC/delta + 免责声明）。
数据不足时 `insufficient_data` 维持当前权重不报错。已接进夜间批处理 + I2 快照归档。

> **红线（已内建）**：此命令**只产建议、绝不自动写** `scoring.WEIGHTS` 或任何 profile。报告 disclaimer 明确：
> 采纳须**人工登记为新 strategy version（B2）→ 跑 shadow challenger（G6）→ 人工 promote（G8）**。
> 「算出数据支撑的建议」≠「自动改策略」。

**剩余（待数据 + 人工，非代码阻塞）**：
1. 攒够 15–30 交易日让 component IC 有统计意义后，人工审 `weight_suggestion.json`。
2. 校准 `estimate_price_setup_score` 内部常数（20/60/70 基准、RR 奖励斜率）——可后续加进同一机器。
3. trade_readiness 六分量权重建议——需先把六分量逐分量落盘进 calibration。
4. 采纳的新权重走 B2 登记 + G6 shadow 验证后再 promote。

**验收（建议机器）**：✅ 有 IC 支撑的权重建议、合计 1.00、可调 damping；✅ 数据不足不报错；✅ 绝不自动应用。

---

## ~~E4 — bid/ask/spread 成交质量（docx P2）~~ — ✅ 已完成（2026-06-17）

**目标**：更真实评估成交质量、滑点、流动性风险。

**为何上调（外部评审，2026-06-16）**：paper 成交可能**偏乐观**——`PAPER_PARTIAL_FILL` 默认关、`PAPER_FILL_MODEL`
是「价格触及 limit 即按 limit 成交」。如果实际成交比仿真差（买在 ask、卖在 bid、宽 spread / 低流动性），
那么用 paper 数据判断策略 edge 会**系统性虚高**。所以 E4 不再是「可选」，而是 **H2 之后、在信任 calibration
的 edge 结论之前**就该补——否则 H 阶段算出的 IC / bucket 收益可能建立在过于乐观的成交上。

**已完成（capture 是 additive、replay 是只读，均不改 live 成交行为，故无需 feature flag）**：
- ✅ **point-in-time 捕获**：`Quote` 增 `bid`/`ask`（+ 派生 `mid`/`spread`/`spread_bps` 属性）；
  `policy/loaders.py::_parse_quote` 解析 book；`OrderIntent` 携带 `bid`/`ask`/`spread_bps`，buy/sell
  intent 从 quote 透传；paper 订单记录新增 `bid`/`ask`/`mid_price`/`spread_bps`/`slippage_bps`（实现 fill
  对 reference 的逐单滑点，正值=对我们更差）。
- ✅ **数据源探测**：`data/live_quotes.py` best-effort 读 yfinance `fast_info` 的 bid/ask，由
  `LIVE_QUOTES_CAPTURE_BOOK`（默认 0）门控——日 OHLCV 源无 book 时 bid/ask 留 None，pipeline 照常跑。
- ✅ **replay 分析**：`replay/fill_quality.py`——逐单 realized slippage（fill vs reference）；按 captured
  spread（有 book 时）或 realized-slippage 流动性代理分桶；**保守成交敏感性**：对一组假设 spread
  （5/10/25/50bps）给出每边成交成本、round-trip edge 缩水（≈ 全 spread）、对总成交名义额的美元拖累——直接回答
  「若按保守成交，校准 edge 会缩水多少」。CLI `analytics fill-quality` → `runtime/analytics/fill_quality_report.{json,md}`。

**涉及文件**：`policy/models.py`、`policy/loaders.py`、`policy/{buy,sell}.py`、`paper/broker.py`、
`data/live_quotes.py`、`replay/fill_quality.py`、`cli.py`、`doctor`；测试 +14。

**验收**：✅ 订单记录含 `spread_bps`/`slippage_bps`；✅ replay 按 spread/流动性分桶输出滑点；✅ 给出「若按
保守成交，edge 缩水多少」的多场景对照（bps + 美元）。388 个测试通过。

> **数据现实**：当前数据源是日 OHLCV（无实时 bid/ask），所以 book 字段默认为 None，分桶回退到 realized-slippage
> 代理、敏感性用假设 spread 场景。基建已就位——接上带 book 的源（设 `LIVE_QUOTES_CAPTURE_BOOK=1`）即自动用真实
> spread，无需改分析代码。这正是「现在采集、否则永远丢失」：先把 capture 管道铺好。

---

# F 阶段 · 后期 / 故意推后

## F2 — review / live 真实下单接线（旧 R7，⛔ 故意推后）

**目标**：把 review/live 从 `execution_not_wired` 接到真实 Robinhood MCP。

**前置条件（硬性）**：
- replay 显示 paper 成交率/胜率/blocked 分布合理。
- 至少若干周 paper 日志「无聊且正确」。
- review 路径先证明只 review 不下单。
- 人工显式移除 `KILL_SWITCH`，人工设 `RISK_TIER`（绝不让 Codex 改）。
- **✅ J1 止损/退出逻辑校正完成（评审新增、live 硬前置）**：现状是 `strategy.md` 写「跌超 3% 不自动卖、
  只 log alert」，但代码 `policy/sell.py` 其实会在 `invalidation_below` 触发**全量自动退出**；同时
  `risk_exit`（分级减仓）路径**事实失效**（`risk_overlay` 从不把 `risk_exit` 放进 `allowed_actions`），且
  缺 technical levels 时**没有兜底硬止损**。**live 前必须**：① 统一 doc 与 code；② 明确止损策略（是否加一道
  固定百分比兜底硬止损）；③ 确保任何持仓都有自动止损、不依赖「人工处理亏损」。详见 **J1**。

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

# H 阶段 · 量化因子 + AI 归因 + 校准升级（ChatGPT 新方向 · 评估 + 计划）

> 来源：用户带来的一份 ChatGPT「Strategy Optimization & AI/Factor Calibration」计划（Phase 1–8）。
> 本段是**我对该计划的评估 + 落到本仓库现状的优先级重排**。

## 我的总评：方向对、分阶段合理，但**没考虑到本仓库已经做掉了一大半**

ChatGPT 的核心主张——**别再堆 AI agent，先建可验证的量化因子 + 校准 + shadow 实验**——和本 roadmap
一直贯彻的原则、以及我这几轮的实现完全一致。分阶段（校准 → 因子 → AI 归因 → shadow → dashboard →
自成长 → 基本面 → 事件）排序也合理，红线（paper/shadow only、point-in-time、不自动 promote、人工改
YAML）与现有 G 阶段安全边界吻合。**但如果把这份计划原样喂给 AI，会重复造已经存在的轮子。**

**ChatGPT 计划 vs 本仓库现状对照（关键）**：

| ChatGPT | 现状 | 说明 |
|---|---|---|
| **Phase 1 Calibration foundation** | 🟢 **基本已做** | `replay/{forward_returns,benchmark_returns,setup_outcomes,near_miss,component_attribution}.py` + `replay/calibration.py` + `calibration_report.{json,md}` + CLI `analytics calibrate` 全在（E1/E3 本会话已建） |
| Phase 1 的 21/63d horizon、per-candidate 超额收益、多 horizon Rank IC + t-stat、更全 near-miss 类别 | ✅ **核心已补**（2026-06-17） | 见 **H1**：21/63d horizon、逐候选 `excess`（vs SPY）、`component_ic_summary`（多 horizon Rank IC + t-stat）已落；更全 near-miss 降级给 E3 |
| **Phase 2 价量因子层** | ❌ **没有** | **真正缺的一条腿**，见 **H2**（最高价值净新增） |
| **Phase 3 AI signal study** | ✅ **已完成** | 标准化 AI schema + 校验 + normalizer + `ai_signals.json`（step 1）；`analytics ai-signal-study` confidence calibration / 方向准确率 / code lift（step 2）；`analytics ai-ablation` 每层 marginal IC + AI-vs-因子（step 3）。全 2026-06-17 落地，normalizer + 只读 replay 路线无需 flag |
| **Phase 4 shadow strategy** | 🟢 **基建已做** | shadow runner（G6）+ challenger **隔离 paper 账本**（G9：shadow_orders/equity/account/positions 已落 `experiments/<id>/paper/`）+ evaluator 读真实 fill/drawdown/PnL 全在。**新增的是**支持 factor/analyzer/setup 类 challenger（需 premarket re-score 路径），见 **H4** |
| **Phase 5 dashboard calibration tab** | ✅ **已完成** | C3 第 8 个 Tab「Calibration」+ 本轮（2026-06-17）增 fill-quality / AI signal study / AI ablation / 多 horizon Rank IC 子视图，见 **H5** |
| **Phase 6 self-growth 用 evidence** | ⏳ **未做** | G3 proposal generator 已在但还没引用 calibration/factor/AI evidence，见 **H6** |
| **Phase 7/8 fundamental / events** | ⛔ **故意推后** | 同 ChatGPT 判断，见 **H7/H8** |

**ChatGPT 计划里需要修正/强调的几点（我的判断）**：
1. **不要重建 Phase 1**——它已存在。把 ChatGPT 的 Phase 1 当作「补强现有模块」（H1），不是从零写。
2. **最高价值净新增是 Phase 2（价量因子层），应作为下一个代码任务**。理由：它是唯一真正缺失的「可
   验证、非 AI 的 alpha」腿；而且**它直接复用我已建好的校准机器**——`factor_alpha_score` 落盘后，
   立刻能被 `bucket_returns` / `component_attribution` 分桶 + 算 IC，几乎不用写新校准代码。
3. **⚠️「现在采集、否则永远丢失」原则（我反复强调的那条）**：H2 的 `factor_panel.json` **必须立刻接进
   premarket 落盘**，哪怕第一版完全不参与打分。因子值是 point-in-time 的，今天不算今天就没有了；
   yfinance 历史价能补算价量因子，但**养成每天落盘 + 让校准从第 1 天就有因子历史**远比三周后再补强。
   （同理 H3 的 AI 标准化 schema 也应尽早接，让 confidence/reason_codes 从现在开始积累。）
4. **数据现实贯穿全程**：H 段几乎所有**洞察**（IC 显著性、factor 有没有 alpha、AI ablation、promote
   决策）都需要 15–30 个交易日。所以策略是：**现在建「产数据」的代码（因子面板、AI schema、H1 的
   horizon 扩展），让积累立刻开始；「吃数据」的分析（显著性、ablation、promote）等数据到位。**
5. **point-in-time / 防作弊**：ChatGPT 的「asof_date、不联网重跑、config_hash 入 manifest、不能只用最终
   PnL 判 AI」都对——而且 `run_manifest.json` 已经记了 `git_commit` + `config_hash`，地基已在。forward
   returns 用 yfinance 历史价（point-in-time 安全）；AI signal study 用已落盘的 per-run 输出（也安全）。
6. **factor 不直接进 champion**——ChatGPT 说得对，和现有 shadow-only 纪律一致：factor 先进
   dashboard/calibration → 再进 shadow strategy → （很久以后、人工 promote）才考虑 champion。

---

## ~~H1 — 校准补强（ChatGPT Phase 1 残项）~~ — ✅ 已完成（2026-06-17，核心三项）

**目标**：把已有校准模块补到 ChatGPT Phase 1 的完整度。都是对现有纯函数的小扩展。

**已完成（核心三项）**：
- ✅ `forward_returns.py`：`DEFAULT_HORIZONS` `(1,3,5)` → `(1,5,21,63)`；价格窗口按 `max_h*2+7` 日自动放宽
  覆盖 63d；未来 bar 不足的 horizon 记 `None`（pending）不猜。
- ✅ **per-candidate 超额收益**：`ForwardReturnRecord` 增 `excess` 字段 = 候选 forward return − 同期 benchmark
  （默认 SPY）return，逐 record 逐 horizon；benchmark 那侧 pending 时记 `None`。`bucket_returns` 多报
  `mean_excess_return`，回答「这档单调性扣掉大盘 beta 后是否还在」。
- ✅ **多 horizon Rank IC + t-stat**：`component_ic_summary`，每 component×horizon 给 pooled IC + 逐 run-date
  截面 IC 时序的 mean/std/t-stat（t = IC_mean/(IC_std/√n)）；接进 `calibration_report.json` 的 `ic_summary`
  + markdown「Multi-horizon Rank IC」表。37 个 replay 测试通过。

**残留（已降级，非 H1 阻塞）**：更全 near-miss 类别的**捕获**已补（2026-06-17：decision 增
`per_candidate_blocks`，逐候选 block 已开始落盘）；剩下的**分类分析**（按 `outside_entry_zone` /
`no_chase` / `reward_risk_too_low` 等类别比后续收益）等 paper 数据积累后并入 E3。拆独立 json 文件优先级低。

<details><summary>原计划具体项（存档）</summary>

**具体**：
- `forward_returns.py`：`DEFAULT_HORIZONS` 从 `(1,3,5)` 扩到 `(1,5,21,63)`（keystone 已支持任意 horizon，
  改默认 + 处理更长窗口未来 bar 不足）。
- **per-candidate 超额收益**：每条 record 增 `excess_vs_SPY/QQQ/SMH` = 候选 forward return − 同期 benchmark
  return（现在 benchmark 只算了**聚合均值**，没做逐候选超额）。
- `component_attribution.py`：从单 horizon Spearman IC 扩成**多 horizon（1/5/21d）Rank IC + 均值/标准差/
  t-stat**（t ≈ IC_mean / (IC_std/√n)）。
- **更全 near-miss 类别**：`outside_entry_zone` / `no_chase` / `reward_risk_too_low` / `observe_only` /
  `market_regime_block` / `theme_concentration_block`——这些是**逐候选**的 block，需先把 per-candidate
  block reason 落盘（现在只有单条决策的聚合 `blocked_reasons`），是个独立小落盘改动（E3 已点名）。
- （可选）按 ChatGPT 拆出 `forward_returns.json` / `setup_outcomes.json` / `near_miss_report.json` 独立文件；
  目前是合并在 `calibration_report.json` 里，够用，独立文件优先级低。

**验收**：calibration_report 含 1/5/21/63d 桶 + 逐候选超额 + 多 horizon Rank IC/t-stat；数据不足标
`insufficient_data` 不报错；不改交易行为。

</details>

---

## H2 — 价量因子层（ChatGPT Phase 2）— ✅ 代码已完成（2026-06-16，flag 默认 0）

**实现记录**（全部按 5 条可扩展性约束 + feature-flag 约定）：
- `features/factors_price.py`：`@factor(name)` **注册表** + 第一批价量因子（12-1/1·3·6m momentum、residual
  momentum、52w 高点接近、5/20d 反转、20/60d realized vol、60d beta、Amihud、dollar volume、volume
  shock）；纯 stdlib，缺数据返回 None 不报错。**加因子 = 一个函数 + 一个装饰器**。
- `config/factor_profiles.json`（JSON，3 层嵌套，同 growth_policy）+ `analyzers/factor_alpha.py`：
  `load_factor_profile`（按名解析，支持未来 challenger）+ `compute_factor_alpha` 横截面 rank 归一化、
  **signed weight = 方向**、coverage 归一化 → `factor_alpha_score`/`factor_components`/`risk_flags`。
  **聚合器遍历 weights dict，加因子=配一行权重，零改聚合代码**。
- `features/factor_store.py`：开放式 panel（新因子=新键）+ 从 market_feed OHLCV 读 + 写
  `factor_panel.json`/`factor_alpha.json`。
- premarket：`run_price_factors` 并行 local stage，包在 `_run_advisory`（因子失败绝不破坏 premarket）；
  **只写两个新产物、不进 champion 打分**；新增 RuntimePaths `factor_panel_path`/`factor_alpha_path`。
- **校准自动 pickup**：`forward_returns` 把 `factor_alpha` + 各因子 rank 折进 calibration records 的
  components → 动态分桶 + Spearman IC **自动覆盖因子**（前一步的「`_SCORE_FIELDS` 动态化」已落地）。
- dashboard：Candidates tab 加 factor view（factor_alpha/risk_flags/各因子 rank）；factor IC/桶已在
  Calibration tab 自动出现。
- 测试：factors_price 6、factor_alpha 7、factor_layer_integration 2、calibration pickup/动态分桶若干、
  dashboard query/render；372 全绿。

**已完成并上线 + flag 已清除（2026-06-16）**：按用户指示，整块功能做完后把 `ENABLE_PRICE_FACTOR_LAYER`
flag **开启并删除所有相关代码**——因子层现在**无条件每天 premarket 运行**（write-only、advisory-wrapped、
不进 champion 打分），不再有 env 开关。从今天起每天落 `factor_panel/factor_alpha`，`analytics calibrate`
可直接看因子 bucket 单调性 + IC。

**未做（留作后续）**：factor 进 **shadow strategy**（H4）；factor 专属 dashboard 子视图扩展（H5 增量）。

---

## H2 — 价量因子层（原计划，保留）

**目标**：加一条**独立的、可验证的量化因子腿**（不直接下单、不直接进 champion 打分），用现有 OHLCV
能算的第一批因子：12-1 momentum、residual momentum、52 周高点接近度、短期反转/pullback 质量、realized
vol、beta、Amihud 非流动性、dollar volume、volume shock。

**新增**：`features/factors_price.py`（纯函数算因子，mock OHLCV 可测）、`features/factor_store.py`、
`analyzers/factor_alpha.py`（按 `factor_profiles.yaml` 加权 + 风险过滤 → `factor_alpha_score`）、
`src/config/factor_profiles.yaml`。输出 `signals/factor_panel.json` + `planner/factor_alpha.json`
（schema 见 ChatGPT 计划）。

### 可扩展性硬约束（让"以后随手加因子"成立 —— 用户明确要求）

> 调研结论：最贵的**校准归因层已经因子无关**（`component_attribution` 自动发现 `components` 里的任意键）；
> 但因子层没建、champion `scoring.WEIGHTS` 写死、`calibration._SCORE_FIELDS` 写死。H2 必须按下面 5 条建成
> **可插拔**，达到「加一个因子 = ① 写函数并注册 ② `factor_profiles.yaml` 加一行权重，下游全自动」：
>
> 1. **因子注册表**：`FACTORS: dict[str, Callable[[OHLCV], float]]`（同 self-growth diagnosers / E1
>    proposal rules 的注册表模式）。加因子 = 注册一行，算面板代码不动。
> 2. **开放式 schema**：`factor_panel.json` / `factor_alpha.json` 的 `symbols[sym]` 是开放 dict，读取方
>    容忍未知键（新因子 = 新键，老代码不炸）。
> 3. **配置驱动权重**：`factor_alpha` 聚合器**遍历 `factor_profiles.yaml` 的 weights dict**（像
>    `scoring.score_candidate` 那样对 components 通用聚合），加因子 = 加一行权重，聚合器零改动。**别学
>    champion `WEIGHTS` 写死。**
> 4. **校准自动 pickup**：让 factor 分数流进校准 records 的 `components`（或并一个 factor components）→
>    `component_attribution` 自动出 IC；**配套把 `calibration._SCORE_FIELDS` 改成动态**（自动包含所有
>    因子），分桶也自动覆盖。
> 5. **自成长通用因子权重 mutation**：`growth_policy.json` 加一个通用 `factor_weights` 类目（带
>    min/max/max_delta + 和约束），让 self-growth 能对**任意因子**权重在边界内提实验（validator 现成的
>    `_validate_weights` 直接复用）。

> 小独立前置：第 4 条里「`_SCORE_FIELDS` 动态化」是个**现在就能做、低风险、独立**的小改动，可先于 H2 落地，
> 让校准分桶和归因一样自动覆盖任意新分量。

### Feature flag 门控（`ENABLE_PRICE_FACTOR_LAYER`，默认 0）— ⚠️ 已超越：实现完成后 flag 已开启并删除，因子层现无条件运行

按「增量开发与 feature flag 约定」：H2 全程在 `ENABLE_PRICE_FACTOR_LAYER` 后面建，**默认关**。
- **建设期（flag=0）**：所有因子代码新增在 `features/` + `analyzers/` 里；premarket 只在一处用
  `if ENABLE_PRICE_FACTOR_LAYER:` 包住「算并落盘 factor_panel/factor_alpha」这一步。flag 关 → premarket
  一字不变，`baseline_v1` 零影响，做到一半也安全。
- **接入点**：premarket 在 market_context 之后、与 DSA/technical 并列的一个 **local 因子层**（纯本地计算，
  不用 Codex）。
- **完成门槛（翻默认）**：因子计算 + 开放式落盘 + factor_alpha 配置聚合 + 校准自动 pickup（含动态
  `_SCORE_FIELDS`）+ dashboard factor 视图 + 测试（flag 开/关两条路径）+ `doctor` 回显，全做完才把默认翻 1。
- **清理期**：稳定后单独移除 flag，让因子层无条件落盘（仍只落盘、不进 champion 打分）。

**⚠️ flag 默认关 vs 立刻攒数据的张力（外部评审，2026-06-16）——重要澄清**：repo 里 `ENABLE_PRICE_FACTOR_LAYER`
**默认 0** 是为了「半成品对所有人零影响」；但**因子落盘路径是只写、不参与 champion 打分**，所以在**你自己的
paper 环境**里，应当**一旦落盘路径做完 + 测试绿，就尽早在 `runtime.env.local` 里设 `ENABLE_PRICE_FACTOR_LAYER=1`**
（不必等整模块全做完）——因为因子是 point-in-time 的，**今天不采集今天就永久丢了**。也就是：**默认关（对仓库）+
paper 尽早开（对你）**，两者不矛盾——开了也只是多落一份 `factor_panel/factor_alpha`，不改任何交易决策。

**两步接入（守 shadow-only 纪律）**：
1. 第一版（本 flag）**只落盘 + 进 dashboard/calibration，绝不碰 champion 打分**。因子值是 point-in-time 的，
   **flag 翻开后从那天起每天落盘**，`bucket_returns`/`component_attribution` 立刻把 `factor_alpha_score`
   当成又一个分量做桶 + IC。
2. 第二版才作为 **shadow strategy**（H4 的 `baseline_v1_plus_price_factors_shadow`）的输入。

**验收**：flag=0 时 premarket / `baseline_v1` 行为逐字不变（既有测试全绿）；flag=1 时 factor_panel/
factor_alpha 可生成、缺数据降 coverage 不 crash；加一个新因子只需「注册 + 配一行权重」，dashboard / 校准
IC / 分桶全自动覆盖；`doctor` 回显 flag。

---

## H3 — AI signal 结构化 + 归因 + ablation（ChatGPT Phase 3）— ✅ step 1+2+3 已完成（2026-06-17）

**现状**：`component_attribution` 已对 dsa/technical/kronos/catalyst/quote 算 forward-return IC（= ChatGPT
要的「AI score vs forward return」「各 AI 层 attribution」的核心）。三步拆解：

1. ✅ **标准化 AI 输出 schema（已完成，2026-06-17）**——`analyzers/ai_signal_schema.py` 定义统一信封
   （`layer`/`symbol`/`asof_date`/`direction`/`confidence`/`time_horizon`/`reason_codes`/`warning_codes`/
   `risk_flags`/`raw_confidence`/`metrics`）+ `validate_ai_signal`（asof_date 必填 ISO 日、direction 枚举、
   confidence∈[0,1] 等强校验）+ 三个 normalizer（kronos/dsa/catalyst，从各层**现有输出**派生标准字段）。
   `analyzers/ai_signals.py::build_and_write_ai_signal_layer` 读 dsa/kronos/catalyst 三件产物 → 归一 → 校验
   → 落 `signals/ai_signals.json`（含 validation 摘要）。premarket 在 catalyst 之后以 advisory 调用。
2. ✅ **`replay/ai_signal_study.py`（已完成，2026-06-17）**——把标准化信封 join 候选 forward returns，按层给：
   confidence calibration（高 confidence 是否真挣更高收益）、directional accuracy（long/short 是否对）、
   confidence→return rank IC、reason/warning code 的 lift vs baseline。CLI `analytics ai-signal-study` →
   `ai_signal_study.{json,md}`。
3. ✅ **`replay/ai_ablation.py`（已完成，2026-06-17）**——combined AI conviction = Σ(direction×confidence)，
   leave-one-out 重算 rank IC 得每层 `marginal_ic_of_layer`（full − drop_layer），外加 factor-only 与
   AI+factor（rank 合成）IC 做 AI-vs-因子对照。第一版用已落盘 signal、不重跑历史 AI。CLI
   `analytics ai-ablation` → `ai_ablation.{json,md}`。两者均只读、可注入 loader 离线测；408 测试通过。

**防作弊（照搬 ChatGPT，且地基已在）**：asof_date 必填（normalizer 用 run_date、validator 强制）、输出不可
事后覆盖、prompt/model/config hash 入 manifest（`run_manifest` 已记 git_commit+config_hash）、历史重跑不联网、
不用最终 PnL 单独判 AI。

**Feature flag——实际未用（重要说明）**：roadmap 原计划用 `ENABLE_AI_STRUCTURED_SIGNALS` 是**假设走「改 AI
prompt 让模型原生吐结构化字段」（热路径）**的路线。实现时改走 **normalizer 路线**：不动任何 LLM prompt 契约，
只读各层**已有输出**派生标准信封、写一份**新的只写 advisory 文件**`ai_signals.json`，**不进 champion 打分/
risk/decisions**。因此和 H2 因子层最终形态、以及 H1/E4/E3 一样——**没有碰热路径，不需要 feature flag**（中间任何
状态都不影响已有系统运行：开不开这层都只是多落一份文件）。后续若要让 LLM **原生**吐结构化字段（更忠实于模型
推理），那才是 prompt-contract 改动、届时再按热路径上 flag；normalizer 信封可直接复用、schema 不变。

**验收（step 1）**：✅ 三层都归一成带 asof_date/confidence/direction/reason_codes/warning_codes 的信封且全部
过校验；✅ 缺产物降级空层不 crash；✅ 不改交易行为（write-only advisory）。

**验收（step 2，2026-06-17）**：✅ `analytics ai-signal-study` 产出按层的 confidence 桶（mean/hit）、directional
accuracy、confidence IC、reason/warning code lift；✅ 只读、不改交易行为；✅ 数据不足空层不 crash。

**验收（step 3，2026-06-17）**：✅ `analytics ai-ablation` 产出 full AI / drop-each-layer 的 rank IC +
`marginal_ic_of_layer`，外加 factor-only 与 AI+factor 对照；✅ 只读、读已落盘 signal 不重跑历史 AI；✅ 空数据
不 crash。**H3 三步全部完成，无需 flag（全程 normalizer 路线 + 只读 replay）。408 个测试通过。**

---

## H4 — factor/analyzer/setup shadow 策略（ChatGPT Phase 4 增量）— ⏳ 依赖 H2

**现状**：shadow runner（G6）+ 隔离 paper 账本（G9）已就绪，但当前只支持**scoring 阈值类** challenger
（复用 champion premarket 产物）。ChatGPT 要的 `baseline_v1_plus_price_factors_shadow` /
`no_kronos_shadow` / `pullback_only_shadow` 改的是**因子权重 / analyzer 开关 / setup 开关**——这些影响
premarket 打分，需要 shadow runner 支持**按 challenger 配置重跑 premarket 打分**（G6 当年标注的「贵路径」）。

**具体**：扩 `experiment`/`strategy_registry` 的 changes 表达力（factor_alpha_weight / analyzer.enabled /
setups.*.enabled）；shadow runner 对这类 challenger 用其配置重算 scoring + risk_overlay（复用
`planner/scoring.py` + `risk_overlay.py`）再跑隔离账本。

**Feature flag（`ENABLE_SHADOW_RESCORE`，默认 0）**：重打分路径在 flag 后面建——flag 关时 shadow runner
按现状只跑阈值类 challenger（既有行为/测试不变）；重打分路径做完测试绿后才翻默认。整条 shadow 本就只写
`experiments/<id>/`、不碰 champion，双重隔离。

**验收**：flag=0 时 shadow 行为逐字不变；flag=1 时 champion 输出仍零变化；challenger 在 `experiments/<id>/`
有独立账本；dashboard 能比较；缺 forward returns / shadow equity 时不能 promote（G7 已强制）。

---

## H5 — dashboard calibration 子视图扩展（ChatGPT Phase 5 增量）— ✅ 已完成（2026-06-17）

主 Calibration Tab（C3 第 8 个）已在。本轮在该 tab 下增量加了：
- ✅ **多 horizon Rank IC + t-stat**（H1 `ic_summary`）表，接进 `calibration_view`。
- ✅ **Fill quality（E4）子视图**：mean realized slippage、按 spread/流动性分桶、保守成交敏感性场景。
- ✅ **AI signal study（H3 step 2）子视图**：按层 confidence calibration 桶、directional accuracy、
  confidence IC、reason/warning code lift。
- ✅ **AI layer ablation（H3 step 3）子视图**：full AI / drop-each-layer 的 IC + `marginal_ic_of_layer`
  + factor-only / AI+factor 对照。
- 既有：setup outcomes / near-miss / 桶收益（含 H1 `mean_excess_return` 列）/ factor_alpha（Candidates tab）/
  champion-vs-challenger 已在。

三个新 query（`fill_quality_report` / `ai_signal_study` / `ai_ablation`）+ 三个新 chart view，全只读、缺
报告时显示「运行哪个命令生成」的 info，不改 YAML、不触发交易；headless `AppTest` 渲染验证覆盖空态与有数据态
（仍 8 个 tab）。413 个测试通过。

> 仍可继续增量的子视图（数据足够后）：factor coverage / factor values 时间序列、AI confidence 的逐 bin 命中率
> 曲线、factor IC 趋势——优先级低，等 paper 数据积累。

---

## H6 — self-growth 用 calibration/factor/AI evidence 生成 proposal（ChatGPT Phase 6）— 🟡 evidence gate 已建（2026-06-17）

让 `growth propose` **引用证据**。**已完成(核心 evidence gate)**：`growth/evidence.py`——
- `gather_evidence(agent_root)`：读 `calibration_report`（near_miss + component IC）+ `weight_suggestion`，
  组成 evidence bundle（缺报告降级空、不 crash）。
- `evidence_for_proposal(proposal, evidence)`：按 proposal 改的 module/field 匹配支撑证据
  （`trade_threshold` ← near_miss「门槛是否太严」；`scoring.*` ← component IC）。
- `apply_evidence_gate(proposals, evidence)`：给每条 proposal 附 `evidence` 列表，**没 evidence 的直接丢弃**。
- 接进 `build_proposals`：`ENABLE_EVIDENCE_PROPOSALS=1` 时启用 gate。validator 红线不变、promote 仍只出草稿、
  whitelist 不变——gate **只让 propose 更严，绝不更松**。

**Feature flag（`ENABLE_EVIDENCE_PROPOSALS`，默认 0，doctor 回显）**：flag 关时 `growth propose` 逐字按现状
（规则注册表）生成；flag 开时要求 evidence 才生成。`growth propose` 本就只写文件、不启用，天然隔离。

**剩余（增量，待数据/后续）**：更多 evidence-based observation 类型（`factor_has_positive_ic` /
`ai_warning_effective` / `ai_confidence_not_calibrated` / `setup_underperforming` 等）+ 把 factor/ai_study
evidence 也接进 `evidence_for_proposal`——机器已就位，加一类 evidence = 加一个匹配分支，攒够数据后增量加。

**verify gate（照搬 ChatGPT，已与 G7 一致）**：promote 需同时满足 min_shadow_days≥10 / min_trading_days≥8 /
shadow_orders+equity 可用 / forward returns 可用 / benchmark 对照可用 / factor attribution 可用 / 无 safety
violation / 人工最终批准。

---

## H7 — fundamental quality 层（ChatGPT Phase 7）— ⛔ 故意推后

profitability / margin / FCF quality / debt / asset growth / accruals 等。**不作买入信号**，只做 quality
filter / sizing modifier / watchlist 优先级 / holding quality / risk overlay warning。数据更复杂，等 H2/H3
稳定后再做；先接 dashboard，再接 shadow。

## H8 — earnings / analyst revision 事件层（ChatGPT Phase 8）— ⛔ 故意推后

earnings surprise / 分析师与 estimate 修正 / guidance / PEAD / news sentiment 一致性。只**增强 catalyst**、
不独立下单。最后做。

---

## H 段推荐执行顺序（我的优先级）

> 贯穿原则同前：**先建产数据的代码、让积累立刻开始；吃数据的分析等数据到位。**

1. ✅ **H2 价量因子层（第一版只落盘 + 进 calibration）**——已完成上线（2026-06-16），无条件每天 premarket 落盘。
2. ✅ **H1 校准补强**（21/63d horizon + 逐候选超额 + 多 horizon Rank IC/t-stat）——已完成（2026-06-17）；因子
   一落盘就能被多 horizon IC + 逐候选超额校准。**下一个代码任务 = E4 成交质量**。
3. **H3 第一步：AI 输出标准化 schema**（confidence/reason_codes/warning_codes/asof_date）——尽早接以攒数据；
   归因/ablation/confidence-calibration 的「吃数据」部分随后。
4. （持续）每天跑 paper，攒 ≥15–30 交易日；定期 `analytics calibrate` 看 factor/AI 的 bucket 单调性 + IC。
5. **H4 factor/analyzer/setup shadow 策略**（需 premarket re-score 路径）——有了因子 + 校准证据后。
6. **H6 self-growth 用 evidence 提 proposal** + **H5 dashboard 子视图**——随证据落地增量。
7. **H7/H8 fundamental / events**——最后，数据更复杂。

---

# I 阶段 · 运维与自动化（每天一份分析 + 趋势功能 + dashboard 可视化）

> 用户三条硬需求，拆成独立可交付子项，互不依赖、各自可单独验收：
> **I1** 每天自动跑分析（cron）· **I2** 每天留一份分析快照（每天一份）· **I3** 拿到趋势的功能 ·
> **I4** dashboard 可视化（每天结果 + 趋势）。**已全部实现（2026-06-17）。**
>
> **现状**：cron/launchd 只调度了交易生命周期（premarket 05:30 / intraday 06:45–12:45 每 30 分 /
> postmarket 13:10，工作日）。分析与自成长命令（`analytics build/calibrate`、`growth
> observe/propose/shadow/evaluate`、`replay`）**全是手动**；且 `calibration_report.json` /
> `growth_observations.json` / `experiment_report.json` / `analytics.db` 都**覆盖成单份最新**（proposal /
> shadow 账本本就按天存）——所以既不自动刷新、也不留逐天历史。

---

## I1 — 夜间分析/自成长自动化 cron — ✅ 已完成（2026-06-17）

**目标**：每天收盘后自动把这套**只读 / shadow-only** 的分析批处理跑一遍，让产物每天刷新。

**具体**：
1. 新增 entrypoint `src/scripts/entrypoints/run_nightly_analysis.sh`，**按序、best-effort**（单步失败不阻断
   后续、各步包 try/log）跑：`analytics build` → `analytics calibrate`（需联网 yfinance）→ `growth observe`
   → `growth propose` + `growth validate` → `growth shadow`（跑 active_shadow，无则 no-op）→ `growth
   evaluate`；整段输出写 `runtime/logs/runs/<date>/nightly/analysis.log`。
2. `cron.example` / `launchd/*.plist.example` 加一条**工作日夜间**调度（建议 ~20:00 PT——晚于收盘，确保
   yfinance 当日日线已结算，forward returns 能含当天）：`0 20 * * 1-5 .../run_nightly_analysis.sh`。
3. 开关 `ENABLE_NIGHTLY_ANALYSIS`（默认 1，`runtime.env.local` 可关）+ `doctor` 回显。

**安全（守红线）**：整批**只读历史 + 写新分析产物 + shadow-only**——不下单、不动 `TRADING_MODE`/
`RISK_TIER`/`KILL_SWITCH`、不写 champion `paper/`、不改 registry；**不 approve、不 promote**（`growth
shadow` 只跑人工已 approve 的实验，proposal 只写文件，promote 永远人工）。"自动跑改进命令" ≠ "自动改策略"。

**验收**：cron 装上后每晚自动重建 analytics.db + 刷新 calibration/growth 产物；单步失败不阻断其余；全程不
下单、不改 champion、不 approve/promote；`ENABLE_NIGHTLY_ANALYSIS=0` 可整段关。

---

## I2 — 每天一份分析快照（"每天一份"）— ✅ 已完成（2026-06-17）

**目标**：让**每个交易日都有一份可回看的分析结果**，而不是只有一份被不断覆盖的最新报告。

**具体**：
- 新增 `analytics snapshot [--date]` 子命令（也由 I1 的夜间批处理在跑完后调用）：把当晚关键报告**归档一份
  带日期的快照**到 `runtime/analytics/history/<date>/`——`calibration_report.json/.md`、
  `growth_observations.json`、`experiment_report.json`、`promotion_recommendation.md`。
- 同时写 `runtime/analytics/history/<date>/nightly_summary.json`：当晚 headline 指标（fill rate /
  no-trade rate / top component IC（各 horizon）/ proposal 数 / active_shadow 数 / champion vs challenger
  关键差），作为 I3 趋势的数据源（小而稳定的 schema）。
- **语义澄清**：分析是**累积到当天**的（forward returns / IC 需历史样本），所以"每天一份"= "当晚为止的
  **累积演变快照**"，不是"只看当天孤立一天的数据"。

**验收**：每跑一次 `analytics snapshot`，`history/<date>/` 下有完整一份当日快照 + `nightly_summary.json`；
重复跑同一天幂等覆盖该天；不改任何"最新"产物的现有行为（加法式）。

---

## I3 — 拿到趋势的功能（"一个功能可以拿到这个趋势"）— ✅ 已完成（2026-06-17）

**目标**：一个**明确的功能**，把 I2 攒下的逐日快照聚合成**时间序列趋势**，可编程取用（不只在 dashboard 看）。

**具体**：
- 新增 `analytics trend [--metric ...] [--since --until] [--output]` 子命令：扫 `history/*/nightly_summary.json`，
  输出关键指标随日期的时间序列（默认 JSON；可 `--output` 写文件）。指标至少含：每个分量/因子的 Rank IC
  （按 horizon）、no-trade rate、fill rate、proposal 数、active_shadow 数、champion 与各 challenger 的
  fill/drawdown/PnL。
- 纯函数 `build_trend(agent_root, *, since, until) -> dict`（读 history 快照、聚合），供 CLI 和 dashboard
  （I4）复用——**一处计算，两处用**。
- 缺历史/缺指标时返回 `insufficient_data`，不报错。

**验收**：`analytics trend` 能输出关键指标的逐日序列；`build_trend` 有单测（mock 几天 history 快照）；纯读、
不改交易行为。

---

## I4 — dashboard 可视化（每天结果 + 趋势）— ✅ 已完成（2026-06-17）

**目标**：在 dashboard 里**可视化** I2 的每日结果和 I3 的趋势——用户明确要求"dashboard 里要能可视化这些"。

**具体（在现有 Calibration / Self-Growth tab 内或新增一个「Trends」tab）**：
1. **数据新鲜度条**：读各 artifact `generated_at` + 当天有没有跑过 nightly，显示"最近一次夜间分析：<时间>"。
2. **分析日期选择器**：从 `runtime/analytics/history/<date>/` 选某一晚，回看那天的完整分析快照（calibration /
   observations / experiment_report）。
3. **趋势折线**：调 I3 的 `build_trend` 把关键指标按日期画折线——分量/因子 IC 随周演变、no-trade rate /
   fill rate 趋势、champion vs challenger 的 fill/drawdown/PnL 曲线。
4. `dashboard/queries.py` 加 `analysis_history_dates()` / `analysis_snapshot(date)` / `trend(...)` 只读
   query；`charts.py` 加趋势折线组件；`app.py` 接入。沿用 headless AppTest 渲染验证。

**安全**：只读 `runtime/analytics/history/*`，不写 YAML、不触发交易、不改 champion。

**验收**：dashboard 能①显示数据新鲜度②按日期回看每天的分析结果③画出关键指标的趋势折线；缺数据显示
`insufficient_data` 不 crash；headless render test 通过。

---

> **与 H 阶段的关系**：H2/H3（因子层 / AI 校准）落地后，夜间批处理与快照**命令不变、产物更丰富**——
> 新因子/AI 的 IC 自动进 `nightly_summary.json`，I3 趋势、I4 dashboard 自动多出对应曲线，无需改 cron/快照逻辑。
> 所以 I1–I4 现在就能先把"每天一份 + 趋势 + 可视化"的骨架定下来，H 阶段数据一上线就自动接入。

---

# J 阶段 · 评审驱动的修正（2026-06-16 外部评审）

> 一次外部评审确认了方向（paper-only、安全边界、H2 为下一步都对），并指出几处该收敛/修正的地方。
> 评审的「优先级要收敛、别急 live、别再堆 fancy 自成长」与本 roadmap 的当前焦点一致。下面是评审驱动的
> 两个新增修正项（E4 上调、H2 flag 澄清已并入各自条目）。

## J1 — 止损/退出逻辑校正 + strategy.md 一致性 — 🟡 兜底硬止损 + doc 一致已做（2026-06-17）

**已完成（2026-06-17）**：
- ✅ **兜底硬止损（safety net）**：`policy/sell.py::_evaluate_hard_stop`——任何持仓相对 average cost 的
  亏损（按实时 quote 计）超过 `HARD_STOP_LOSS_PCT`（默认 8%）就**全量自动卖出**，**独立于** allowed_actions、
  **独立于** technical levels（填补「缺 levels 就无止损」的缺口）。在 allowed_actions 早退**之前**运行，
  `reason_codes=["catastrophic_stop"]`、`setup_type="hard_stop"`。`HARD_STOP_LOSS_PCT=0` 可禁用；doctor 回显。
  broker 把 `catastrophic_stop` 计入 stop 统计。
- ✅ **doc/code 一致**：`strategy.md` 删掉「down >3% → 只 alert」的错误描述，改成准确的自动退出说明
  （technical invalidation 全平 + 8% 兜底硬止损，均 paper-only、review/live 仍人工）。
- ✅ **测试锁定**：缺 levels 时大亏损仍自动止损、阈值内不触发、`=0` 可禁用；既有 average-down block 测试
  调整持仓使亏损<8% 以保留原本意。432 测试通过。
- ✅ **守边界**：只改 paper 决策逻辑，不接 live 下单（live 仍 F2 人工解锁）。

**剩余（产品决策，待人工）**：`risk_exit` 分级减仓（0.5/0.75/1.0）当前仍未启用（`risk_overlay` 不把 `risk_exit`
放进 `allowed_actions`）——代码保留但不触发。是否启用分级减仓是个**策略选择**，留给人工决定后再让 risk_overlay
在合适条件放开；兜底硬止损已保证「任何持仓都有自动止损」这条安全底线。

<details><summary>原问题记录（存档）</summary>

**问题（已核实）**：
- **doc/code 不一致**：`src/config/strategy.md:94` 写「down >3% → do not sell automatically; log an alert
  only」；但 `policy/sell.py` 实际在 `quote.price <= invalidation_below` 时 `full_invalidation_exit`
  **全量自动卖出**。两者矛盾，会误导 Codex 和你自己。
- **分级减仓事实失效**：`sell.py` 的 `risk_exit`（0.5/0.75/1.0 分级减仓）只有当 `"risk_exit" in
  allowed_actions` 才触发，而 `planner/risk_overlay.py` 永远只给 `["small_limit_buy",
  "partial_take_profit"]`——所以分级防御退出**从不触发**，唯一的自动退出是「跌破技术 invalidation 全清」。
- **无兜底硬止损**：若某持仓缺 `invalidation_below`（technical levels 缺失），则**没有任何自动止损**。

**为何重要**：paper 研究阶段「靠人工处理亏损」尚可，但 **live 会变成亏损无人自动兜底**——这是上 live 前
必须解决的安全项。诚实的 paper 校准也受影响（退出规则不一致会让胜率/收益失真）。

**具体步骤**：
1. 定策略：是否在技术 invalidation 之外，加**一道固定百分比兜底硬止损**（如 −X%）作为 safety net（尤其
   technical levels 缺失时）；是否启用 `risk_exit` 分级减仓（需让 risk_overlay 在合适条件把 `risk_exit`
   放进 `allowed_actions`）。
2. 让 `strategy.md` / `risk.md` 与 `policy/sell.py` **完全一致**（删掉「只 log alert」或改成实际行为）。
3. 补测试覆盖：缺 technical levels 时仍有自动止损；分级减仓按预期触发。
4. **仍守安全边界**：这些只改 paper 决策逻辑，不接 live 下单（live 仍由 F2 人工解锁）。

**涉及文件**：`policy/sell.py`、`planner/risk_overlay.py`、`src/config/strategy.md`、`src/config/risk.md`、测试。

**验收**：doc 与 code 一致；任何持仓都有自动止损路径（含缺 technical levels 的兜底）；既有 paper 行为变化
有测试锁定 + 记为一次可追溯改动（必要时新 strategy version）。

</details>

## J2 — Codex-facing 文档旧路径统一 — ✅ 已完成（2026-06-16）

**问题（已核实）**：多个 Codex-facing config 仍写**旧的扁平路径**（`runtime/state/today_allowlist.txt`、
`daily_plan.json`、`dsa_signals.json`、`daily_usage.json`），而系统实际用**按日期的 run folder**。这些是
premarket Codex prompt 会读的 config，旧路径会误导 Codex（和人）。

**实现记录**：
- `risk.md` / `strategy.md`：把 `runtime/state/<flat>` 全部改成 **runtime block 注入的变量名**
  （`TODAY_ALLOWLIST_PATH` / `DAILY_PLAN_PATH` / `DSA_SIGNALS_PATH` / `DAILY_USAGE_PATH`，运行时解析为
  dated run folder），并在文件顶部加了「Path note」说明这一约定（**以后不会再写死路径而再次过时**）。
- `universe.txt` / `allowlist.txt`：注释里的旧路径改成 `runtime/state/runs/<date>/planner/today_allowlist.txt`。
- `dsa_strategy_weights.json` 的 `output_contract.file` 改成 `DSA_SIGNALS_PATH`。
- 全 `src/config/` 旧扁平路径清零；358 测试通过（纯文档/契约改动，无代码风险）。

**未改（有意保留）**：`docs/superpowers/specs|plans/*` 里的旧路径是**历史设计文档**（point-in-time 记录），
保留原样。

**验收**：✅ `src/config/` 不再出现旧 `runtime/state/<flat>` 路径；与 `RuntimePaths` / runtime block / README 一致。
