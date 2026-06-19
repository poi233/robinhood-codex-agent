# 未来工作清单（Roadmap · 全局合并版）

> 最后更新：2026-06-19
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
| H4 shadow re-score | `ENABLE_SHADOW_RESCORE` | shadow runner 的 challenger 重打分路径 | 🟡 **多权重 re-score 已建（2026-06-17，默认 0）**：challenger 可重配多分量权重重打分（E2 shadow 验证路径）；analyzer/setup/factor 纳入打分的「贵路径」待后续 |
| H6 evidence-based proposals | `ENABLE_EVIDENCE_PROPOSALS` | growth propose 的证据校验 | ✅ **gate 已建（2026-06-17，默认 0）**：开时 proposal 必须带 calibration/weight evidence 才生成；更多 evidence 类型增量加后翻默认 |
| M1–M5 intraday advisory overlay | `ENABLE_INTRADAY_ADVISORY_OVERLAY` | intraday 排序/仓位/风控 overlay | 🟡 **M1–M5 核心已完成（2026-06-18，默认 0）**：loader/normalizer + H2/H3 rank_delta 排序 + K1/K2 风控/仓位收紧 + rankings/order/email/dashboard audit + forward-return/growth evidence + overlay mutation 安全白名单已建；自动 proposal rule 仍待；flag 关时 champion 完全保持旧行为 |
| O1 每周 Serenity 自动选股 | `ENABLE_WEEKLY_SCREENER` | 周度 cron 自动写 `universe.txt` + `universe_meta.json` | 🟡 **规划中（2026-06-19，默认 0）**：Codex + vendored `serenity-supply-chain` skill 发现池外上游瓶颈股 → 因子验证 → **自动增改 universe（只增不删 + 重排，无需人工确认）**。flag 关时 cron 只产报告不改 config；翻默认门槛=auto-apply 路径有「只增不删」单测护栏 + 备份/回滚 + 落审计 |
| O2 每日动态选 active | `ENABLE_DYNAMIC_ACTIVE` | premarket 贵分析层（Kronos/technical/market_feed）的 active 集来源 | 🟡 **规划中（2026-06-19，默认 0）**：active 集由写死 `active_watchlist.txt` 改为「pin 锚 ∪ 全 universe 便宜预排 top-N」。flag 关时＝完全现状（仍读 active_watchlist.txt） |

> 注：纯手动命令（`analytics calibrate`、`growth observe/propose`）和 shadow-only 路径**天然隔离**（不在热
> 路径、不动 champion），可以不强制 flag；**强制 flag 的是会接进 premarket/intraday 热路径的模块**。
> 当前未完成的热路径接入主要是 H4 与 M；H2/H3 已改成 write-only normalizer/落盘路线，无需热路径 flag。
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
| | C4 | Dashboard v3（高级化重设计：中文化 + 深色主题/卡片 + 11→5 主区 + 四种指引） | 用户新增（2026-06-18） | ✅ **已完成（2026-06-18）**：只读不变；中文为主、深色高级主题、KPI 卡片、11 标签合并为 5 主区、每类数据带「好坏判定 / 基准对比 / 同比变化 / 行动建议」；headless AppTest 渲染 5 主区全绿（33 dashboard 测试通过） |
| | C5 | Dashboard K线复盘（每只股票的日K + 各策略买卖点 + 均线/量/MACD） | 用户新增（2026-06-18） | ✅ **已完成 + 专业版升级（2026-06-18）**：第 6 主区「📉 K线复盘」——Plotly 4 面板（日K+SMA20/50/200+布林(20,2) · 成交量+量MA20 · RSI(14) · MACD），叠加 champion 与各挑战者买卖点；每笔订单画 **止损/目标位线 + 持仓期阴影 + 买→卖盈亏连线**；FIFO 配对回合 → 每策略 **已实现盈亏/胜率/均R/持仓浮动** 卡片对比；区间按钮(1M/3M/6M/全部)+十字光标+右轴+周末 rangebreaks；plotly 进 [dashboard] extra；只读 |
| **D 工程优化 · 不阻塞** | D1 | DSA/Technical token 优化 | design doc | ✅ **已完成**（2026-06-15，见下方实现记录） |
| | D2 | market_feed 跨日缓存 / batch | 旧 R4 | 🟡 缓存（2026-06-15）+ batch 拉取能力（2026-06-17：`fetch_live_rows_batch` 一次 `yf.download` 多 ticker + 分发纯函数 + 测试）已建；采集主流程逐步采用 |
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
| | ~~H4~~ | factor/analyzer/setup shadow 策略（ChatGPT Phase 4 增量） | ChatGPT | ✅ **已完成（2026-06-18）**：`ENABLE_SHADOW_RESCORE` 下 challenger 可重配多分量权重 + **贵路径重打分**：`analyzer.<name>.enabled=false` 禁用分量（no_kronos）、`<comp>_weight` 重配、`factor.factor_alpha_weight` 把 H2 因子纳入 challenger 打分（baseline+factors）；`rescore_candidate_scores` 复用 champion 已落盘 per-component 诊断，point-in-time 安全、不重跑 analyzer、不碰 champion |
| | ~~H5~~ | dashboard calibration 子视图扩展（ChatGPT Phase 5 增量） | ChatGPT | ✅ **已完成（2026-06-17）**：Calibration tab 加 fill-quality（E4）+ AI signal study + AI ablation（H3）+ 多 horizon Rank IC/t-stat（H1）子视图；只读、headless 渲染验证 |
| | ~~H6~~ | self-growth 用 calibration/factor/AI evidence 生成 proposal（ChatGPT Phase 6） | ChatGPT | ✅ **已完成（2026-06-18）**：evidence gate + M5 overlay proposal rules + 三种新 evidence 类型（factor_positive_ic / ai_calibration / setup_outcomes）；`evidence_for_proposal` 覆盖 scoring.component_weights / setups / policy.price_setup_weight |
| | ~~H7~~ | fundamental quality 层（ChatGPT Phase 7） | ChatGPT | ✅ **已完成（2026-06-18）**：骨架 + normalizer 已建（2026-06-17）+ **接入 premarket advisory（2026-06-18）**：`run_fundamental_layer` advisory stage，write-only → `fundamental_snapshot.json`，失败不破坏 premarket |
| | ~~H8~~ | earnings / analyst revision 事件层（ChatGPT Phase 8） | ChatGPT | ✅ **已完成（2026-06-18）**：骨架 + normalizer 已建（2026-06-17）+ **接入 premarket advisory（2026-06-18）**：`run_event_layer` advisory stage，write-only → `event_snapshot.json`，失败不破坏 premarket |
| **I 运维与自动化** | ~~I1~~ | 夜间分析/自成长自动化 cron（收盘后自动跑 analytics/calibrate/growth） | 用户新增 | ✅ **已完成（2026-06-17）**：`run_nightly_analysis.sh` best-effort 批处理 + cron/launchd 示例 + `ENABLE_NIGHTLY_ANALYSIS`（doctor 回显） |
| | ~~I2~~ | 每天一份分析快照（`history/<date>/` + nightly_summary.json） | 用户新增 | ✅ **已完成（2026-06-17）**：`analytics snapshot`，幂等归档 + headline summary |
| | ~~I3~~ | 拿到趋势的功能（`analytics trend` + `build_trend` 纯函数） | 用户新增 | ✅ **已完成（2026-06-17）**：`analytics trend` + `build_trend` 纯函数，逐日时间序列 |
| | ~~I4~~ | dashboard 可视化（新鲜度 + 日期回看每天结果 + 趋势折线） | 用户新增 | ✅ **已完成（2026-06-17）**：第 9 个 Trends tab（新鲜度 + 日期回看 + 趋势折线） |
| **J 评审驱动修正（2026-06-16 外部评审）** | ~~J1~~ | 止损/退出逻辑校正 + strategy.md 一致性 | 评审 | ✅ **兜底硬止损 + doc 一致已做（2026-06-17）**；剩 `risk_exit` 分级减仓启用待人工策略决定 |
| | ~~J2~~ | Codex-facing 文档旧路径统一 | 评审 | ✅ **已完成（2026-06-16）** |
| **K 组合与归因（评审一·真缺口）** | K1 | **Portfolio Layer**（cash/theme exposure + 单仓上限目标） | 评审一 | 🟡 **第一版已建（2026-06-17）**：`portfolio/target.py` 算当前组合 cash/单仓/主题敞口 vs 目标上限 + 超限 flag，premarket advisory 落 `portfolio_target.json`，dashboard Themes tab 显示；write-only、绝不加买入、只能收紧。第二版接 sizing 上限待校准 |
| | K2 | **量化 Market Regime 引擎**（Bull/Neutral/RiskOff/Panic + 仓位乘子） | 评审一 | 🟡 **第一版 + VIX 自动接入已完成（2026-06-18）**：`regime/engine.py` 确定性分类（SPY/QQQ 趋势 + **自动拉 ^VIX** → bull/neutral/risk_off/panic + 乘子 1.2/1.0/0.5/0.0），premarket advisory 落 `regime_state.json`，dashboard Today tab banner；接 sizing 已由 M3 overlay 实现（只降风险）。breadth/treasury indicator + 接 champion sizing 待校准 |
| | K3 | **Thesis Tracker**（交易绑主题标签 → 主题级胜率归因） | 评审一 | 🟡 **第一版已建（2026-06-17）** + **thesis tags 落盘（2026-06-18）**：`replay/thesis.py` + `analytics thesis`——thesis 标签（universe_meta theme + DSA primary_theme/strategy_matches）join E1 forward returns，按 thesis 出胜率/均值；接进夜间批 + I2 快照；`OrderIntent.thesis_tags` 已落盘（2026-06-18），逐单归因无需事后重建。统计意义待数据 |
| **M Advisory Overlay 接线（用户 D 方案）** | ~~M1~~ | intraday 读取 advisory artifacts + overlay 归一化 | 用户新增 | ✅ **已完成（2026-06-18）**：`policy/advisory_overlay.py` + `PolicyInputs.advisory_overlay` + loader flag；读取 `factor_alpha`/`ai_signals`/`portfolio_target`/`regime_state`，输出空影响 overlay |
| | ~~M2~~ | H2/H3 进入排序，不做硬拦 | 用户新增 | ✅ **已完成（2026-06-18）**：`factor_alpha` + AI envelopes 只生成小幅 `rank_delta` 并调整 `trade_readiness_score`；不直接 block buy、不改 sizing |
| | ~~M3~~ | K1/K2 进入风控/仓位，只收紧 | 用户新增 | ✅ **已完成（2026-06-18）**：regime risk_off/panic 和 portfolio breach 可 block new buy；size multiplier clamp `<=1.0`，只能降仓位 |
| | ~~M4~~ | 决策日志和 dashboard 显示每个因子如何影响最终决策 | 用户新增 | ✅ **核心已完成（2026-06-18）**：`intraday_rankings.jsonl`、proposed order、email、dashboard Decision Overlay 已落 `advisory_overlay`；后续可继续美化/趋势化 |
| | ~~M5~~ | growth 分析 overlay 效果并提出 paper-only 改进建议 | 用户新增 | ✅ **已完成（2026-06-17）**：forward returns/calibration 自动纳入 overlay components，growth evidence 能读取 overlay IC，`growth_policy`/validator 允许 bounded paper-only overlay mutation；自动 proposal rule 已建（2026-06-18）：`factor_alpha`/`ai_composite` 正 IC → 自动建议 bump `overlay.factor_weight/ai_weight` |
| **L 收口与验证（评审二·P0）** | L1 | 文档权威源收敛 | 评审二 | 🟢 **进行中（2026-06-17）**：project-status 漂移已修（顶部 point-in-time 约定 + 状态表更正）；README 已重写 |
| | ~~L2~~ | 完整 smoke checklist → `docs/smoke-test.md` | 评审二 | ✅ **已完成（2026-06-17）**：`src/scripts/smoke/run_smoke.sh`（doctor/safety/analytics/growth 一条龙 + PASS/FAIL 汇总；网络/lifecycle 步骤 opt-in）；实跑 13/13 本地命令 PASS；`docs/smoke-test.md` |
| | ~~L3~~ | H2 factor **benchmark coverage 审计** | 评审二 | ✅ **已完成（2026-06-17）**：market_feed 永远采 `BENCHMARK_SYMBOLS`（SPY/QQQ/SMH/IWM）；factor_panel/alpha 报告 coverage%（多少 active_symbol 有 bars + benchmark 是否齐）；dashboard 显示 |
| | ~~L4~~ | **nightly health / freshness** | 评审二 | ✅ **已完成（2026-06-17）**：`analytics nightly-health` → `nightly_health.json`（报告新鲜度 + 失败步骤）；nightly 脚本记 step_results + 末步调 health；dashboard Trends tab 顶部 🟢/🔴 banner |
| | ~~L5~~ | premarket factor-failure advisory 测试 | 评审二 | ✅ **已完成（2026-06-17）**：测试锁定 advisory 信号层抛异常时 premarket 仍完成、candidate_scoring/risk_overlay/final_planner 仍跑；该 stage 在 stage-log 记 `failed`、`_run_advisory` 吞异常使 pipeline 继续 |
| | L6 | **冻结 alpha 接线 + 跑 paper 15–30 天** | 评审二 | ⏳ **纪律项**：H7/H8 保持 skeleton-only 不接 scoring；M overlay 只能默认关闭 + shadow/audit 先行 |
| **N 数据存储强化（空数据期红利）** | ~~N1~~ | analytics.db schema 漂移修复（补全新落盘字段 + 新表） | 用户新增（2026-06-18） | ✅ **已完成（2026-06-18）**：orders 补 E4 spread/slippage + setup levels；decisions 补 per_candidate_blocks/advisory_overlay/thesis_tags；intraday_rankings 补 base score/rank_delta/overlay；新增 factor_alpha/regime_state/portfolio_target 表 |
| | ~~N2~~ | analytics.db 索引 | 用户新增（2026-06-18） | ✅ **已完成（2026-06-18）**：`INDEX_DDL` 给 candidates/decisions/orders/intraday_rankings/paper_equity/blocked_reasons/factor_alpha 常用过滤列建索引，随表重建 |
| | ~~N3~~ | build 数据校验 + `analytics validate` | 用户新增（2026-06-18） | ✅ **已完成（2026-06-18）**：`analytics validate` 只读扫 decisions/orders/equity/rankings 的 JSONL，报告坏 JSON 行 + 缺关键字段行（per-source + per-run），写 `validate_report.{json,md}`；接进夜间批（build 之后）；改不动任何数据 |
| | ~~N4~~ | 数据保留 / 归档策略 | 用户新增（2026-06-18） | ✅ **已完成（2026-06-18）**：`analytics retention [--keep-days N] [--apply]`——对超过保留窗的旧 run 只 prune `market_feed/`（大输入快照，分析不读），保留全部分析输入小 JSON；默认 dry-run、`--apply` 才删；写 `retention_report.{json,md}` |
| **O 选股层升级（每周自动发现 + 每日动态选）** | O0 | vendor Serenity 供应链 skill + 接入安装/校验脚本 | 用户新增（2026-06-19） | ✅ **已完成（2026-06-19）**：`muxuuu/serenity-skill`（MIT，~2.5k★）vendor 进 `.agents/skills/serenity-supply-chain/`，加进 `install_repo_skills.sh`/`verify_repo_skills.sh` 的 SKILLS 列表 |
| | O1 | **每周 cron 自动改 universe**（Serenity 发现 + 因子验证 → 自动增改标的与排名） | 用户新增（2026-06-19） | 🟡 **规划中（2026-06-19，`ENABLE_WEEKLY_SCREENER` 默认 0）**：自动 **只增不删 + 重排**，无需人工确认；`screen` 命令 + Codex discover prompt + 因子验证 + auto-apply writer + 周度 cron 待建 |
| | O2 | 每日 premarket 动态选 active（pin 锚 ∪ 全 universe 预排 top-N） | 用户新增（2026-06-19） | 🟡 **规划中（2026-06-19，`ENABLE_DYNAMIC_ACTIVE` 默认 0）**：贵分析输入由写死 `active_watchlist.txt` 改为每日动态预排；flag 关时＝现状 |

> **新旧编号对照**：R1→E1（增 benchmark returns）、R2→E2、R3→A3、R4→D2、R5→D3、R6→D4、R7→F2；
> token 优化设计→D1；docx 的 run_manifest→B1、registry→B2、analytics.db→B3、changelog→B4、
> dashboard→C1、theme 诊断→C2、forward/benchmark/attribution→E1、near-miss→E3、bid/ask/spread→E4、
> strategy compare→F1、config editor→F3。

---

## 已完成项详细记录 → 见归档文件

> A/B/C 三阶段、D1/D3/D4、E1/E3、F1、G 阶段（G-pre–G9）、B5 **全部已完成**；其详细实现记录已移到
> [`roadmap-archive.md`](./roadmap-archive.md)，本文件不再展开。**本文件保留**：优先级总表 + 各贯穿原则/
> 约定 + 当前焦点 + **未完成/规划项**（D2 adoption、E2、F2/F3、H4/H6/H7/H8、K1/K2 第二版、M、L6）的详细内容。状态以上方总表为准。

---

## 立即可做的建议顺序（无数据依赖期）

数据校准（E 阶段）仍阻塞于 2–3 周 paper 积累；A/B/C/G/I/L 大部分基建已完成，历史推荐顺序不再重复展开。
当前执行顺序以「当前焦点」和全局优先级总览为准。历史阶段细节见 [`roadmap-archive.md`](./roadmap-archive.md)。

---

## 🎯 当前焦点（2026-06-18 · Advisory Overlay 规划 + 收口纪律）：默认冻结 champion，受控接 M

> **进度（2026-06-17 收口轮）**：✅ **L1–L5 收口/验证全部完成**（文档权威源收敛 + smoke 脚本 + factor benchmark
> coverage 审计 + nightly health + advisory-failure 测试）；✅ **K1–K3 第一版全部完成**（Portfolio Layer /
> 量化 Regime 引擎 / Thesis Tracker——均 advisory/只读、绝不加买入、不接 sizing）。**现在进入 L6：默认 champion
> 继续冻结、跑 paper 15–30 天**；用户新增的 **M 阶段**只作为 flag 默认 0 + shadow/audit 先行的受控接线计划，
> 不直接打开新 alpha 或污染 baseline。

> 系统已从 paper bot 长成**策略实验平台**（E1 校准 / H2 因子 / H3 AI 归因+ablation / H4 shadow 重打分 /
> H5 dashboard / H6 evidence proposal / I1–I4 夜间自动化 / E2 权重建议 / J1 兜底硬止损 / H7–H8 骨架 /
> K1–K3 组合·regime·thesis）。
> 两份评审的共识：**现在不缺功能，缺的是 (a) 文档收口——已经开始漂移、会误导喂进来的 AI；(b) 15–30 个
> 交易日的真实 paper 样本来证明哪些信号真赚钱**。第二份评审还明确点出：**别再叠加 alpha 信号进 scoring 热
> 路径**——H2+H3+H7+H8 若同时进打分，attribution 将无法判断谁真有贡献。

**按优先级（整合两份评审）：**

1. **P0 · 收口（立即，docs/低风险）** — 文档权威源收敛（`project-status.md` 漂移已修：顶部加 point-in-time
   约定 + 状态表 J1/I1/dashboard 9 Tab 已更正）；补一份完整 **smoke checklist**。见 **L 阶段（L1/L2）**。
2. **P1 · 数据覆盖与健康审计** — H2 factor **benchmark coverage**（保证 SPY/QQQ/SMH/IWM 永远在 market_feed，
   别依赖 active_watchlist 恰好含 SPY）+ **nightly health / freshness**（`nightly_health.json` + dashboard 顶部
   醒目显示最近一次成功/失败步骤）。见 **L3/L4**。
3. **P2 · 冻结跑 paper 15–30 天** — 不调 champion 权重/阈值（否则样本不可比），自成长只 `observe`+`propose`；
   M1–M5 核心已完成；下一步是 paper/shadow 数据积累 + 可选补 M5 自动 proposal rule。`ENABLE_INTRADAY_ADVISORY_OVERLAY=0` 时必须完全不改变 intraday 行为。
4. **数据积累期可并行（非 alpha 热路径，不污染 attribution）** — K 阶段继续积累组合/regime/thesis 证据；M 阶段
   只把 K1/K2 作为风控/仓位收紧层，不能放大仓位，不能绕过 hard risk。
5. **暂停** — H7/H8 **保持 skeleton-only、不接 scoring/premarket 热路径**（见 **L6**）；别同时把多个新 alpha
   开进 shadow。
6. **数据到位后** — 用 E1/E2/H3/M5 结果选第一个真 challenger；E2 权重重标定与 M overlay 调参都走 shadow →
   人工 promote。

> **两份评审的调和点（关键）**：第一份要加 Portfolio/Regime/Thesis，第二份要「别再加功能」——其实不矛盾。
> Portfolio Layer 与 Regime 引擎**不是又一个 alpha 信号，而是组合/风控层**（改善收益曲线、不进 alpha
> attribution）；Thesis Tracker 是**归因工具**（正好服务「证明哪些主题赚钱」）。真正要暂停的是 H7/H8 这类
> **新 alpha 进 scoring**。所以「收口 + 跑数据」与「做 K 阶段组合层」可以并行，互不冲突。

---

> 2026-06-16 的旧焦点已被 2026-06-17 收口轮覆盖，不再在本文重复保留。核心纪律仍是：冻结 baseline
> → 一次一个实验 → 只用数据 promote（≥10 shadow 日、fill rate / drawdown / forward return 不劣于
> champion、无 safety violation、人工 approve）。

---

# O 阶段 · 选股层升级（每周自动发现 + 每日动态选 active · 🟡 规划中 2026-06-19）

> **背景（用户 2026-06-19）**：现在的"选股"分两层但都**手工静态**——`universe.txt`（~88，最大候选池）和
> `active_watchlist.txt`（≤30，跑贵分析的精选池）都是人工编辑的纯文本，playbook 写明 active watchlist 是
> "每月手工更新"。每天的 AI/因子精筛（DSA + Kronos + technical + factor + 5 分量打分 → risk_overlay →
> daily_plan）只在这个**固定池子里排序**，没有任何自动流程去回答"池子里该不该换、池外有没有更值得看的票"。
>
> **用户的两层诉求**：
> 1. **每周**从更大的市场自动找到好的标的，放进 universe（供每天 premarket review）；
> 2. **每天** premarket 从 universe 里挑"最需要 review"的标的做贵分析。
>
> **用户的关键决策（2026-06-19）**：
> - 发现来源＝**Codex AI 搜索**（结合主题/新闻发现池外新票，再用因子验证），用 GitHub 上的 **Serenity
>   供应链卡点 skill**（`muxuuu/serenity-skill`）当发现大脑。
> - 每日 active 选择＝**动态选 + 少量 pin**（保留 SPY/QQQ/NVDA 等长期锚，其余名额每日由预排动态填）。
> - **每周由 cron 自动改 universe，只增加标的 + 改排名（不删除），无需人工确认。** ← 明确要求 auto-apply，
>   覆盖仓库默认的"propose, never auto-apply"哲学。

## 安全定位（为什么 auto-apply 在这里可接受）

O 阶段全程只动**选股层（universe / 排名 / active 选择）**，这正是自成长白名单里**允许改动**的维度
（`watchlist`），**绝不触碰**仓位/风险维度（`TRADING_MODE` / `RISK_TIER` / `KILL_SWITCH` /
`per_trade_risk_pct` / `max_daily_risk_pct` / `max_single_stock_weight` / 真实下单——这些永久禁改）。

把 auto-apply 的爆炸半径限制住的三道护栏：
1. **只增不删 + 只重排**：cron 永不删除现有标的，最坏情况只是多了一只低排名的 `watch` 候选；不会让正在
   持仓/观察的票凭空消失。
2. **下游闸门不变**：universe 只是"允许被看"的最大集合。新加的票要真正被交易，仍要过每天的
   candidate_scoring → risk_overlay（regime / 集中度 / tradable 闸）→ price/size gate → 兜底硬止损。
   选股层放宽 ≠ 放宽风控。
3. **可回滚 + 审计**：每次 auto-apply 前备份旧 `universe.txt`/`universe_meta.json`，把"加了哪些、为什么、
   因子分多少、排名怎么变"落到 `runtime/screener/<date>/` 审计，随时可人工回退。

> O0/O1 是**周度独立命令**（不在 premarket/intraday 运行时热路径），但因为 O1 会自动改选股输入，按仓库约定
> 仍用 `ENABLE_WEEKLY_SCREENER`（默认 0）门控：关时 cron 只产报告、不改 config；做完 + 测试 + 护栏齐备后才
> 翻默认（或人工开）。O2 直接接 premarket 热路径 → `ENABLE_DYNAMIC_ACTIVE`（默认 0），关时一字不变＝现状。

## O0 — vendor Serenity 供应链 skill + 接入安装脚本 — ✅ 已完成（2026-06-19）

- `muxuuu/serenity-skill`（MIT，~2.5k★，含 `SKILL.md` + `references/scripts/agents/evals`）vendor 进
  `.agents/skills/serenity-supply-chain/`；脚本（`serenity_scorecard.py` 纯本地 JSON→打分、`validate_skill.py`
  仅 re/sys/pathlib）已审无网络/子进程/写盘副作用。
- 加进 `src/scripts/skills/install_repo_skills.sh` 与 `verify_repo_skills.sh` 的 `SKILLS` 列表，安装后
  premarket/weekly 跑的 Codex（`codex exec`，workspace-write 沙箱）可加载它。

## O1 — 每周 cron 自动发现 + 自动改 universe（🟡 规划中）

**目标**：每周一次，从大市场自动发现池外上游瓶颈股，因子验证后**自动**写进 `universe.txt` +
`universe_meta.json`（只增 + 重排，不删），无需人工确认。

**具体步骤**：
1. **CLI `screen`**（`cli.py` + 新建 `src/trading_agent/screener/`）。
2. **Codex 发现**（新 prompt `src/prompts/screener/discover.txt`）：点名用 `serenity-supply-chain` skill 的
   卡点方法，从主题/新闻逆向映射供应链找池外候选（排除已在 universe 的），输出
   `runtime/screener/<date>/discovered.json`（每只带 theme / thesis / 证据 / 初判）。用 `runtime_overrides`
   把输出路径注入 prompt（不改 `runtime_block.py` 公共代码）。**Codex 联网已获用户授权（2026-06-19）**：发现步
   用 Serenity 在线研究全流程（实时新闻 / 公告 / 财报 / web 检索）作主路径；网络/数据不可用时仍 fail-closed
   （宁可这周不进货，也不写半成品、绝不删东西）。
3. **因子验证（严门槛）**（复用 `signals/dsa_metrics.py::build_dsa_metrics`，喂候选列表而非 universe）：批量拉
   OHLCV 算动量/相对强弱/趋势/量能/ATR，给每只 `factor_score`。**严格 fail-closed 过滤**（任一不过即丢弃）：
   ① 数据质量 ok（足够 bar）；② 流动性下限（dollar volume ≥ `SCREEN_MIN_DOLLAR_VOL`）；③ 趋势门槛
   （在 SMA200 上方 / 不在破位）；④ 标的合规（long 普通股/ETF，排除杠杆/反向 ETF、期权、加密——沿用
   `universe.txt` 头部规则）。
4. **auto-apply writer**（`ENABLE_WEEKLY_SCREENER=1` 时）：
   - 备份旧 `universe.txt` / `universe_meta.json` 到 `runtime/screener/<date>/backup/`；
   - **只增（限速）**：本周通过验证的新票按 `factor_score` 取前 `SCREEN_MAX_ADDS_PER_WEEK`（默认 5）append 到
     `universe.txt`，并补 `universe_meta.json`（`tier:"watch"` + theme + liquidity + `source:"serenity_screen"` +
     `added_date`）；
   - **重排（只写 meta）**：把 `screen_score` / `screen_rank` 写进 `universe_meta.json` 供 O2 每日预排消费；
     **`universe.txt` 只 append、永不重排**（diff 干净、易审计）；
   - **上限降级**：universe 超过 `UNIVERSE_MAX`（默认 120）时，把 `screen_rank` 最低的现有票降为
     `tier:"passive"`（从 AI 层排除，但**仍留在文件里＝不算删**），保证成本/噪声可控；
   - **绝不删除**任何现有标的（降级≠删除）；
   - 落 `runtime/screener/<date>/universe_change.{json,md}`（加了谁、为什么、因子分、谁被降级）做审计。
   - flag 关时：同样跑发现+验证，但**只写报告不碰 config**（dry-run 形态）。
5. **周度调度**：`cron.example` 加一条（如周日盘后 `0 14 * * 0`）；launchd 同理可加一个 weekly 模板。

> **锁定的设计参数（2026-06-19 用户确认）**：增长控制＝**限速 + 上限降级**（`SCREEN_MAX_ADDS_PER_WEEK=5` /
> `UNIVERSE_MAX=120`，满了降级最低排名为 passive，不删）；因子门槛＝**严**（流动性 + 数据质量 + 趋势三闸）；
> 重排＝**只写 `universe_meta.json` 的 `screen_score/screen_rank`，`universe.txt` 只 append 不重排**。

**涉及文件**：新增 `src/trading_agent/screener/`（discover 调度 + factor 验证 + writer）、
`src/prompts/screener/discover.txt`、`tests/trading_agent/screener/*`；改动 `cli.py`、`cron.example`、
`config/runtime.env`（加 `ENABLE_WEEKLY_SCREENER` + doctor 回显）、README/playbook。

**验收**：✅ `screen` flag 关时只产报告、universe 零改动；✅ flag 开时只增不删（单测断言旧标的全部保留）+
限速（≤`SCREEN_MAX_ADDS_PER_WEEK`）+ 上限降级（超 `UNIVERSE_MAX` 把最低排名降 passive、文件仍含该票）+ 严
门槛过滤 + 只写 meta 分数（`universe.txt` 不重排）+ 备份 + 审计；✅ Codex/网络不可用或因子数据不足时
fail-closed（不写半成品、不删东西）；✅ `CODEX_EXEC_DRY_RUN=1` 可离线跑通骨架。

## O2 — 每日 premarket 动态选 active（+ 少量 pin）（🟡 规划中）

**目标**：贵分析（Kronos / technical / market_feed）的输入从写死的 `active_watchlist.txt` 改为**每日从全
universe 动态选**最该 review 的一批。

**具体步骤**：
1. premarket 开头用便宜信号对全 universe 预排：复用 `build_dsa_metrics`（已在 premarket 算）+ O1 写进
   `universe_meta.json` 的 `screen_score`，合成 `review_priority`。
2. `active_watchlist.txt` 语义改为 **pin 锚名单**（始终纳入，如 SPY/QQQ/NVDA）；当天 active 集 =
   pins ∪ 预排 top-N（补到 `ACTIVE_MAX`，默认 30）。
3. 把 `orchestration/premarket.py` 里 `active_symbols` 的来源（约 line 189/257/293）换成这个动态集；落
   `runtime/state/runs/<date>/planner/active_selection.json` 留痕（谁因为什么被选）。
4. `ENABLE_DYNAMIC_ACTIVE`（默认 0）+ `ACTIVE_MAX`（默认 30）；**flag 关时仍读 `active_watchlist.txt`＝完全现状**，零回归。

**涉及文件**：`orchestration/premarket.py`、`data/universe.py`（pin/动态选 helper）、`core/context.py`
（`active_selection.json` 路径）、`cli.py`（doctor 回显 flag）、`config/runtime.env`、对应测试。

**验收**：✅ flag 关时 premarket 既有测试逐字全绿、active 集＝`active_watchlist.txt`；✅ flag 开时 active 集 =
pins ∪ top-N、写 `active_selection.json`、benchmark（SPY 等）仍在 market_feed；✅ universe/数据缺失时
fail-closed 退回 pin 锚。

> **建议实施顺序**：O0（✅ 已完成）→ O1（周度、独立、低耦合）→ O2（动每日热路径，带 flag 默认关）。
> **后续可增量**：把 O1 的 thesis/证据接进 K3 Thesis Tracker 做"发现来源命中率"归因；universe 体检报告进
> dashboard；O1 发现的票自动补 `universe_meta` 的 `supply_chain`/`risk_tags`。

---

# C4 阶段 · Dashboard v3 高级化重设计（只读不变 · ✅ 已完成 2026-06-18）

> **背景**：用户反馈现有 dashboard「太丑陋、看不懂、缺指引、对比弱」。v1/v2（C1/C3）功能齐了，但 UI 大量是
> `st.dataframe` / `st.json` 原始数据倾倒、内部代号（H2/H3/K1/K2/E1/E4/L4…）和裸字段名（`no_trade_rate_pct`/
> `factor_alpha_score`/`advisory_rank_delta`）直接暴露在界面上。C4 是一次**纯只读的可读性/视觉重设计**，
> 不改任何查询语义、不写任何交易参数。

**用户确定的四个方向（2026-06-18）**：
1. **语言**：中文为主（标题/指标名/解读说明全中文，去掉内部代号）。
2. **视觉**：高级深色主题 + 卡片化（自定义主题 + KPI 卡 + 统一图表风格）。
3. **信息架构**：11 标签合并为 **5 主区**。
4. **每类数据的指引**：四种全要 ——「**好坏判定**（阈值色标）/ **基准对比**（vs SPY/champion）/
   **同比变化**（vs 上一交易日/上一快照 delta）/ **行动建议**（规则化一句话）」。

**新信息架构（11 → 5）**：
| 新主区 | 合并自 | 解决 |
|---|---|---|
| 📊 今日驾驶舱 | ① Today + K2 Regime + L4 Nightly Health + K1 组合集中度 | 今天能不能交易、为什么、风险状态 |
| 🎯 选股与决策 | ② Candidates + H2 因子 + ④ 决策叠加 + ③ 决策/拦截 | 候选股 打分→因子→最终决策 全链路 |
| 💰 业绩与对比 | ⑤ Paper + ⑥ 策略对比 + vs SPY 基准 | 赚没赚、跑赢大盘没、哪个版本更好 |
| 🔬 校准与归因 | ⑦ Calibration + ⑪ Thesis + ⑨ Themes | 打分/逻辑灵不灵、哪类主题真赚钱 |
| 🌱 成长与趋势 | ⑧ Self-Growth + ⑩ Trends | 实验进展 + 指标随时间走向 |

**实现拆解（每步独立 commit + 更新本文档）**：
- **C4.1 UI 工具层**：新增 `dashboard/ui.py`——`kpi_card`（值+同比 delta+好坏色条+悬停说明）、
  `verdict`（阈值→🟢/🟡/🔴+文案）、`guidance_box`（这是什么/怎么看/建议做什么）、`pretty_table`
  （中文列名 + 红绿着色，基于 `st.column_config`）、`vs_benchmark`、`delta_vs_prev`；阈值集中在 `THRESHOLDS`。
- **C4.2 主题**：`.streamlit/config.toml` 深色高级主题 + 一次性 CSS（卡片样式）+ 统一 Altair 主题。
- **C4.3 数据层补充**（`queries.py`，仍只读）：`overview_with_delta`（当前日 vs 上一交易日）、权益曲线对齐
  SPY 基准；其余复用现有查询。
- **C4.4 主区重构**：`charts.py` 用 ui 工具重写各 view；`app.py` 11 tab → 5 主区，每主区内分小节 + 顶部 guidance。
- **C4.5 配套**：`test_app_smoke.py` 断言 11→5 + 新中文 header；`README.md` 的「11 tabs」改为 5 主区说明。

**红线（不变）**：纯只读；不新增运行时必需依赖（主题/CSS 为 Streamlit 内置）；不碰 scoring/risk/paper/decision
任何行为；既有非 dashboard 测试逐字不变。

**验收**：`pip install -e ".[dashboard]"` 后 `AppTest` 渲染 5 主区全部无异常（空态 + 有数据态）；界面无内部
代号、关键指标带好坏色/同比/基准/建议四类指引。

**实现记录（2026-06-18，全部完成）**：C4.1–C4.5 已落地——`dashboard/ui.py`（verdict/THRESHOLDS、KPI 卡片
带同比 delta + 好坏色、guidance_box、中文列名 + pretty_table、vs_benchmark、delta_vs_prev、一次性 CSS +
Altair 深色主题，兼容 altair≥5.5 的新 `alt.theme` API）+ `.streamlit/config.toml` 深色主题；`queries.py` 加
`overview_with_delta` + `equity_with_benchmark`（本地 market_feed SPY 日线归一化，纯只读）；`charts.py`/`app.py`
重写为 5 主区（今日驾驶舱 / 选股与决策 / 业绩与对比 / 校准与归因 / 成长与趋势）每区带 guidance；
`dashboard` CLI 现尊重 `AGENT_ROOT`（cwd 仍忽略）。smoke test 改断言 5 主区 + 中文 header 并设 `AGENT_ROOT`
真正喂入 seed 数据。**33 个 dashboard 测试通过、全套 606 通过**（仅 2 个 kronos setup-script 测试因需联网
pip 安装假包而失败，与本改动无关）。README「11 tabs」段落 + nightly-health/overlay 指向已同步更新。

---

# C5 阶段 · Dashboard K线复盘（只读 · ✅ 已完成 2026-06-18）

> **背景**：用户希望「能显示 K 线，告诉我每只股票我是怎么买的、不同 Strategy 会怎样」（参考一张
> TradingView/QuantView 风格的截图）。本仓库已具备所需全部只读数据：`market_feed/ohlcv/<symbol>/daily.json`
> 提供日 OHLCV；champion 成交在 `<run>/paper/orders.jsonl`；每个挑战者的隔离 G9 账本在
> `<run>/experiments/<strategy_id>/paper/orders.jsonl`。

**实现（2026-06-18，全部完成）**：
- `dashboard/kline.py`：纯 Python 算 SMA/EMA/MACD + Plotly 图（`make_subplots` 三行：日K+均线+买卖点 /
  成交量 / MACD）；上涨绿、下跌红；▲=买入、▼=卖出，**按策略着色**（champion 蓝、挑战者各色），hover 显示
  策略/方向/价/量/理由；深色主题、关闭 rangeslider、category 轴跳过周末。
- `queries.py`（只读）：`available_kline_symbols` / `ohlcv_daily`（取最新运行日 market_feed）+
  `trades_for_symbol`（跨运行日聚合 champion + 各挑战者的 filled 成交）。
- `charts.kline_view`：渲染图 + 「各策略成交明细 / 对比」——每策略给均买价、现价、浮动盈亏（好坏色）。
- `app.py`：新增第 6 主区「📉 K线复盘」，标的下拉 + 策略多选（默认全部叠加）；顶部 guidance。
- `pyproject.toml`：`plotly>=5.18` 进 `[dashboard]` extra；`charts.kline_view` 守护 import，缺 plotly 时给安装提示。
- smoke test：seed 补 NVDA/SPY 日线 + 一个挑战者隔离账本（不同买点），断言 6 主区含「K线复盘」。

**红线（不变）**：纯只读；plotly 仅 dashboard 用、可选 extra；不碰任何交易路径。

**验收**：✅ AppTest 渲染 6 主区无异常（33 dashboard 测试通过、全套 606 通过）；✅ 图含 K线/SMA20/SMA50/
champion 买点/challenger 买点/成交量/MACD（DIF/DEA/柱）共 9 条 trace；✅ 缺数据降级为 info 不报错。

**专业版升级（2026-06-18，同日）**：按用户「太简陋了，按专业的来」要求加深——
- 指标：SMA20/50/200 + 布林(20,2) 带 + 成交量MA20 + RSI(14)（70/30 辅助线）+ MACD(12/26/9)，共 4 个堆叠面板。
- 交易计划可视化：每笔买单从 `orders` 表的 `stop_price`/`target_1`/`target_2` 画止损（红虚线）/目标（绿虚线）线段，
  持仓期用半透明阴影标出，买→卖用按回合盈亏着色的连线连起来。
- `summarize_strategy_trades`：FIFO 配对买卖成回合，算每策略 **已实现盈亏 / 胜率 / 均 R / 持仓浮动盈亏**，做成对比卡片。
- 交互：周末 rangebreaks（去空档）、1M/3M/6M/全部 区间按钮、十字光标 spike、右侧 y 轴。
- `queries.trades_for_symbol` 透传 `setup_type/stop/target/reward_risk/slippage_bps`，明细表展示完整交易计划。
- 测试 seed 补 stop/target + 一笔卖出（成一个闭合回合），图实测 21 条 trace；33 dashboard 测试通过。

**跨策略行为对比 + 权益重放（2026-06-18，同日，按用户「不同策略的行为 / 动态看信息」要求）**：
- **策略行为对比**（业绩与对比 + K线复盘两处）：`queries.strategy_behavior` 把 champion 决策（decisions 表）与各挑战者
  `shadow_decisions.jsonl` 按当天决策序号对齐，并排出 trade/no-trade 表 + ⚠️ 分歧高亮 + 每挑战者「与冠军分歧处数 /
  出手次数」汇总卡；`queries.decisions_for_symbol` 在 K线复盘给「各策略对该标的的决策」（含未成交的 would_trade /
  被拦截原因）。直接回答「同一天各策略为什么出手/空仓、分歧在哪」。
- **挑战者权益重放**（业绩与对比）：`queries.strategy_equity_curves` 取 champion（主账本）+ 各挑战者
  （`experiments/<id>/paper/equity_curve.jsonl`）权益，归一化到 100 叠加成曲线 + 累计收益/最大回撤对比表（⭐标最优）——
  「换成这个策略整段会怎样」。
- 三个新 query + 三个新 chart view（`strategy_equity_replay_view` / `strategy_behavior_view` / `symbol_behavior_view`），
  全只读；smoke seed 补挑战者 equity_curve + 一条与冠军分歧的 shadow_decision；33 dashboard 测试通过。

> **后续可增量**：intraday 分钟级 K 线（需分钟 OHLCV 采集）、画扇形/斐波那契等手绘工具、把 entry/stop/target 接
> technical_levels（非成交票也显示计划）、行为分歧的全局热力图（哪些票分歧最多）。

---

# D 阶段 · 工程优化（不阻塞，边等数据边做）

## D2 — market_feed 跨日缓存 / batch（旧 R4） — 🟡 缓存 + batch 能力已建，主流程逐步采用

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
- **batch 拉取能力（已建，2026-06-17）**：`market_context.fetch_live_rows_batch()` 用一次
  `yf.download(tickers=[...], group_by="ticker")` 拉多 ticker，并用纯函数分发到 per-symbol rows。测试覆盖
  多 ticker frame / 单 ticker frame / 空 symbol / 缺列降级。主采集流程仍可逐步迁移，避免一次性改动数据路径。

**涉及文件**：新增 `data/ohlcv_cache.py`、`tests/trading_agent/data/test_ohlcv_cache.py`；改动
`data/market_context.py`、`core/context.py`、`orchestration/premarket.py`、`cli.py`、`runtime.env`、
对应测试文件。

**验收**：✅ 跨日缓存场景下 yfinance 请求次数显著下降（增量 period 远小于全量 period）；✅ batch 下载能力
可单测验证；data_status 逻辑不变，仍准确（缓存/批量失败应降级或回退）。剩余是让更多采集主路径采用 batch，
而不是能力缺失。

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
| **Phase 2 价量因子层** | ✅ **已完成** | H2 已落 `factor_panel.json` / `factor_alpha.json`，无条件 premarket 落盘但不进 champion 打分 |
| **Phase 3 AI signal study** | ✅ **已完成** | 标准化 AI schema + 校验 + normalizer + `ai_signals.json`（step 1）；`analytics ai-signal-study` confidence calibration / 方向准确率 / code lift（step 2）；`analytics ai-ablation` 每层 marginal IC + AI-vs-因子（step 3）。全 2026-06-17 落地，normalizer + 只读 replay 路线无需 flag |
| **Phase 4 shadow strategy** | 🟢 **基建已做** | shadow runner（G6）+ challenger **隔离 paper 账本**（G9：shadow_orders/equity/account/positions 已落 `experiments/<id>/paper/`）+ evaluator 读真实 fill/drawdown/PnL 全在。**新增的是**支持 factor/analyzer/setup 类 challenger（需 premarket re-score 路径），见 **H4** |
| **Phase 5 dashboard calibration tab** | ✅ **已完成** | C3 第 8 个 Tab「Calibration」+ 本轮（2026-06-17）增 fill-quality / AI signal study / AI ablation / 多 horizon Rank IC 子视图，见 **H5** |
| **Phase 6 self-growth 用 evidence** | 🟡 **部分完成** | H6 evidence gate 已建；更多 factor/AI/regime/portfolio evidence 类型待增量接入 |
| **Phase 7/8 fundamental / events** | ⛔ **故意推后** | 同 ChatGPT 判断，见 **H7/H8** |

**ChatGPT 计划里需要修正/强调的几点（我的判断）**：
1. **不要重建 Phase 1**——它已存在。把 ChatGPT 的 Phase 1 当作「补强现有模块」（H1），不是从零写。
2. **Phase 2（价量因子层）已完成**：它是唯一真正缺失的「可验证、非 AI 的 alpha」腿，现已每天落盘；
   `factor_alpha_score` 会被 `bucket_returns` / `component_attribution` 自动分桶 + 算 IC。
3. **⚠️「现在采集、否则永远丢失」原则已落实到 H2/H3**：H2 的 `factor_panel.json` / `factor_alpha.json`
   和 H3 的 `ai_signals.json` 都已作为 premarket advisory 产物落盘；第一版不参与 champion 打分，只为
   point-in-time 数据积累和后续校准服务。
4. **数据现实贯穿全程**：H 段几乎所有**洞察**（IC 显著性、factor 有没有 alpha、AI ablation、promote
   决策）都需要 15–30 个交易日。所以策略是：**现在建「产数据」的代码（因子面板、AI schema、H1 的
   horizon 扩展），让积累立刻开始；「吃数据」的分析（显著性、ablation、promote）等数据到位。**
5. **point-in-time / 防作弊**：ChatGPT 的「asof_date、不联网重跑、config_hash 入 manifest、不能只用最终
   PnL 判 AI」都对——而且 `run_manifest.json` 已经记了 `git_commit` + `config_hash`，地基已在。forward
   returns 用 yfinance 历史价（point-in-time 安全）；AI signal study 用已落盘的 per-run 输出（也安全）。
6. **factor 不直接进 champion**——ChatGPT 说得对，和现有 shadow-only 纪律一致：factor 先进
   dashboard/calibration；若要影响 champion，必须走 M 阶段受控 overlay + shadow/人工验证。

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

## H2 — 价量因子层（ChatGPT Phase 2）— ✅ 已完成并上线（2026-06-16，flag 已清除）

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

> 原 H2 计划已由上方实现记录覆盖，不再重复保留。仍未完成的是 **factor 权重/overlay 如何进入交易决策**，
> 这不属于 H2 本身，统一放到 **M 阶段** 规划。

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

## H4 — factor/analyzer/setup shadow 策略（ChatGPT Phase 4 增量）— 🟡 多权重 re-score 已建（2026-06-17）

**已完成（多权重 scoring re-score，flag 后面）**：`shadow_runner._challenger_scoring_profile` 在
`ENABLE_SHADOW_RESCORE=1` 时额外应用 experiment 的 `changes` 列表（多个 scoring-module 数值覆盖），不再只支持
G3 的单个阈值 mutation。所以 challenger 现在能**一次性重配多个分量权重**（dsa/technical/kronos/quote/catalyst）
并经 `build_challenger_risk_overlay` 在隔离账本重打分——**正好是 E2 权重建议的 shadow 验证路径**。flag 关时
逐字按现状（单 mutation），flag 默认 0、doctor 回显。整条 shadow 仍只写 `experiments/<id>/`、不碰 champion（双重隔离）。

**剩余（贵路径，标注后续）**：`no_kronos_shadow`（analyzer 开关）/ `pullback_only_shadow`（setup 开关）/
`baseline_v1_plus_price_factors_shadow`（把 H2 因子**纳入** challenger 打分）——这些要**按 challenger 配置重跑
premarket analyzer/打分**（含让 factor 选择性进 challenger 评分，而 champion 仍 write-only 不进）。是「贵路径」，
机器骨架（多 change 表达力 + flag）已就位，重跑 premarket 那层留作后续增量。

<details><summary>原现状记录（存档）</summary>

**现状**：shadow runner（G6）+ 隔离 paper 账本（G9）已就绪，但当前只支持**scoring 阈值类** challenger
（复用 champion premarket 产物）。ChatGPT 要的 `baseline_v1_plus_price_factors_shadow` /
`no_kronos_shadow` / `pullback_only_shadow` 改的是**因子权重 / analyzer 开关 / setup 开关**——这些影响
premarket 打分，需要 shadow runner 支持**按 challenger 配置重跑 premarket 打分**（G6 当年标注的「贵路径」）。
</details>

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
报告时显示「运行哪个命令生成」的 info，不改 YAML、不触发交易；headless `AppTest` 渲染验证覆盖空态与有数据态。
当时 dashboard 仍是 8 个 tab；I4 完成后已增至 9 个 tab。413 个测试通过。

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

## H7 — fundamental quality 层（ChatGPT Phase 7）— 🟡 骨架 + normalizer 已建（2026-06-17）

profitability / margin / FCF quality / debt 等。**不作买入信号**，只做 quality filter / sizing modifier /
watchlist 优先级 / holding quality / risk overlay warning。

**已完成（骨架，安全）**：`analyzers/fundamental.py`——`FundamentalSnapshot` schema（profit/operating margin、
ROE、revenue growth、debt/equity、current ratio，全 optional）+ `normalize_fundamental` +
`quality_flags`（unprofitable / negative_roe / revenue_declining / high_leverage / weak_liquidity——
**全是 quality warning，绝非买入信号**）+ best-effort `yfinance_fundamentals` provider（可注入、无网络返回空）
+ `build_and_write_fundamental_layer`（write-only advisory，不进 champion 打分，同 H2 因子层）。纯函数有测试。

**剩余（接入，待数据成熟）**：把 `fundamental_snapshot.json` 接进 premarket（advisory 落盘）→ dashboard 子视图
→ 作为 quality filter / sizing modifier / risk-overlay warning。骨架可扩展（加一个比率 = 加一行 `_FIELD_MAP`
+ 一条 flag 规则），数据源（yfinance.info best-effort，或更丰富的源）接入即用。

## H8 — earnings / analyst revision 事件层（ChatGPT Phase 8）— 🟡 骨架 + normalizer 已建（2026-06-17）

earnings surprise / 分析师与 estimate 修正 / guidance / PEAD 等。只**增强 catalyst**、不独立下单。

**已完成（骨架，安全）**：`analyzers/events.py`——`EventSnapshot` schema（next_earnings_date、days_to_earnings、
analyst recommendation mean/count、earnings surprise、estimate revision，全 optional）+ `normalize_event` +
`event_flags`（earnings_imminent / analyst_bullish|bearish / estimate_revised_up|down——**只作 catalyst
上下文，绝不独立下单**）+ best-effort `yfinance_events` provider（info + calendar，可注入）+
`build_and_write_event_layer`（write-only advisory）。纯函数有测试。

**剩余（接入，待数据成熟）**：把 `event_snapshot.json` 接进 premarket → 增强 catalyst 层 / earnings 临近时
风险提示。骨架可扩展（加一类事件 = 加一条 flag 规则）。

---

## H 段推荐执行顺序（我的优先级）

> 贯穿原则同前：**先建产数据的代码、让积累立刻开始；吃数据的分析等数据到位。**

1. ✅ **H2 价量因子层（第一版只落盘 + 进 calibration）**——已完成上线（2026-06-16），无条件每天 premarket 落盘。
2. ✅ **H1 校准补强**（21/63d horizon + 逐候选超额 + 多 horizon Rank IC/t-stat）——已完成（2026-06-17）；因子
   一落盘就能被多 horizon IC + 逐候选超额校准。
3. ✅ **H3 AI 输出标准化 + study + ablation**——已完成（2026-06-17）；现在开始每天积累
   confidence/reason/warning/code-lift 与 AI-vs-factor 对照数据。
4. ✅ **E4 成交质量 + H5 dashboard 子视图 + H6 evidence gate**——已完成核心机器；更多 evidence 类型随数据增量。
5. **M 阶段 advisory overlay**——按用户 D 方案，把 H2/H3/K1/K2 受控接入 intraday：H2/H3 只影响排序，
   K1/K2 只收紧仓位/风控。必须用 feature flag + shadow + audit，避免一次性把多个 alpha 混进 champion。
6. （持续）每天跑 paper，攒 ≥15–30 交易日；定期 `analytics calibrate` / `analytics ai-signal-study` /
   `analytics ai-ablation` 看 factor/AI 的 bucket 单调性 + IC。
7. **H4 factor/analyzer/setup shadow 策略**——M 阶段产生足够证据后，再做更贵的 premarket re-score challenger。
8. **H7/H8 fundamental / events**——最后，数据更复杂；继续 skeleton-only，避免污染当前 attribution。

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

---

# K 阶段 · 组合与归因（外部评审一 · 真缺口，2026-06-17）

> 评审一的核心判断：项目已过「玩具」阶段，现在主要是 **AI Opinion** 而非 **组合管理**。下面三项**不是新的
> alpha 信号**（不进 scoring 热路径、不污染 H2/H3 attribution），而是**组合 / 风控 / 归因层**，可在
> 数据积累期与「收口」并行做。**先建产数据/产配置的代码，吃数据的判断等样本到位。**

## K1 — Portfolio Layer（最大缺失）— 🟡 第一版已建（2026-06-17）

**问题**：现在 `MRVL / AVGO / ANET / NVDA / VRT` 看着是 5 个标的，实际**全是一笔 AI-infra 交易**。系统有
单票 concentration cap 和 theme exposure **诊断**（C2，只读），但没有一个**主动输出组合目标**的层。

**已完成（第一版，advisory）**：`portfolio/target.py`——
- `build_portfolio_target(positions, cash, theme_map, *, cash_target=0.20, max_position_size=0.08, theme_cap=0.35)`
  纯函数：按持仓市值算 total_equity / cash_weight / 单仓权重 / 主题敞口（theme_map 来自 `universe_meta.json`），
  标 `breaches`（below_cash_target / oversize_positions / overexposed_themes）。
- `build_and_write_portfolio_target`：读 paper ledger（positions+cash）+ theme map → 落 `portfolio_target.json`。
- premarket **advisory stage**（`run_portfolio_target`，`_run_advisory` 包裹，write-only，不进 scoring/risk/sizing）。
- dashboard **Themes tab** 显示：cash/单仓/主题敞口 vs 上限 + 超限 ⚠️。
- **红线（已内建 + 测试）**：notes 写明「never a buy signal；接 sizing 后只能收紧、不放大」。

**剩余（第二版，待校准 + 人工）**：把 caps 作为 sizing 的**上限约束**（只收紧）——已由 M3 overlay 在
`ENABLE_INTRADAY_ADVISORY_OVERLAY` 后实现（block/降仓位，只收紧）；**sector_exposure 已完成（2026-06-18）**：
`load_sector_map` 从 universe_meta `sector` 字段读、`build_portfolio_target` 算 sector 敞口 + `sector_cap`
（默认 0.40）+ `overexposed_sectors` breach（unknown 不计），dashboard 显示——sector 数据可增量填、代码已就位；
cash_target 随 K2 regime 动态化待校准 + 接 champion sizing。

<details><summary>原计划（存档）</summary>

**具体**：新增 `portfolio/` 模块，纯函数读 candidate_scores / risk_overlay / theme 映射 / 当前持仓，输出一个
**advisory 组合目标**（write-only，先不强制进 sizing，像 H2 因子层那样先落盘攒数据）：
```json
{ "cash_target": 0.20,
  "theme_exposure":  { "AI_INFRA": 0.35, "DEFENSE": 0.10, ... },
  "sector_exposure": { ... },
  "max_position_size": 0.08 }
```
**接入分两步**（守纪律）：① 第一版只落盘 + 进 dashboard（不改 sizing）；② 校准后再作为 sizing 的**上限约束**
（只收紧、不放大），登记为新 strategy version 走 shadow。**红线**：portfolio 层只能**降低**集中度/敞口，绝不
新增买入信号。

**验收**：✅ 每个 run 产 `portfolio_target.json`；✅ theme 敞口与单仓上限可在 dashboard 看；✅ 第一版不改交易行为
（advisory write-only）。465 测试通过。

</details>

## K2 — 量化 Market Regime 引擎 — 🟡 第一版已建（2026-06-17）

**问题**：当前 `market_regime` 是 **LLM 在 `final_planner` 里定**的（opinion）。缺一个**确定性、可回测**的量化引擎。

**已完成（第一版，advisory）**：`regime/engine.py`——
- `classify_regime(indicators)` 纯函数：`vix` / `spy_return_20d` / `spy_above_sma200` / `qqq_return_20d`
  （任一可缺、降级）→ `bull / neutral / risk_off / panic / unknown` + multiplier `1.2 / 1.0 / 0.5 / 0.0 / 1.0`
  + `applied_multiplier = min(1.0, multiplier)` + reasons。
- `indicators_from_market_feed`：从 market_feed 的 SPY/QQQ daily bars 算 20d 收益 + SMA200（L3 已保证 SPY/QQQ
  恒在 feed）；**VIX 自动接入已完成（2026-06-18）**：`fetch_vix_level()` best-effort 拉 `^VIX`（可注入、失败返回
  None），`ENABLE_REGIME_VIX_FETCH`（默认 1，doctor 回显）控制，panic/risk_off 的 VIX 阈值现在能触发。
- `build_and_write_regime_state` → `regime_state.json`；premarket **advisory stage**（write-only）；
  dashboard **Today tab banner**（risk_off/panic 黄色警示）。
- **红线（已内建 + 测试）**：multiplier 只在 sizing 边界以 `min(1.0,·)` 应用——**只降风险、绝不引入杠杆**；
  接 sizing 已由 M3 overlay 在 `ENABLE_INTRADAY_ADVISORY_OVERLAY` 后实现（只收紧）。

**剩余（第二版，待校准 + 人工）**：breadth/dollar/treasury 等更多 indicator；与 forward returns 对照验证
regime 是否真改善收益曲线；校准后把 regime 接 champion sizing（当前只在 M overlay paper/shadow 路径），登记新 strategy version 走 shadow。

<details><summary>原计划（存档）</summary>

输出**离散 regime + 仓位乘子**：`Bull 1.2x · Neutral 1.0x · RiskOff 0.5x · Panic 0.0x`。**红线**：multiplier
接 sizing 时只能 ≤ 现状（降风险方向），不引入杠杆。
</details>

**验收**：每个 run 产 `regime_state.json`；regime × forward-return 对照可看；第一版不改交易行为。

## K3 — Thesis Tracker（主题级归因）— 🟡 第一版已建（2026-06-17）

**问题**：现在只能（部分）回答「哪只票赚钱」，不能回答「**哪些 thesis/主题真赚钱**」。

**已完成（第一版，只读）**：`replay/thesis.py` + `analytics thesis`——
- `thesis_tags_for(symbol, dsa_signal, theme_map)`：thesis 标签 = universe_meta theme ∪ DSA primary_theme ∪
  DSA strategy_matches（标准化大写、去重，如 `AI_SEMICONDUCTOR / AI_INFRA / MOMENTUM`）。**从已落盘产物派生**，
  无需新捕获。
- `thesis_attribution`：把标签 join E1 forward returns，按 thesis 聚合 **win_rate / mean_return / count**
  （`min_count` 过滤小样本），按胜率排序。`analytics thesis` → `thesis_attribution.{json,md}`。
- 接进夜间批处理 + I2 快照归档；天然隔离、只读、无需 flag。

**已完成（2026-06-18）**：`OrderIntent` 新增 `thesis_tags` 字段（universe_meta theme + DSA primary_theme/strategy_matches），买入时点落盘在 `decisions.jsonl`，不再需要事后重建 DSA 归档；`PolicyInputs` 加 `theme_map` 字段由 loader 从 `universe_meta.json` 读取。551 测试通过。factor 触发并入标签 + dashboard thesis 视图待后续。

**验收**：✅ `analytics thesis` 输出各 thesis 胜率/均值（如 `AI_INFRA 胜率 61% · CPO 68% · NUCLEAR 39%`）；
✅ 只读不改交易行为。476 测试通过。

---

# M 阶段 · Advisory Overlay 接线（用户 D 方案，2026-06-18）

> 目标：把已经落盘但原本 write-only 的 H2/H3/K1/K2 advisory 产物，**分权限、可审计、可回放**地接进
> intraday 决策。核心纪律：`factor_alpha` / `ai_signals` 只影响排序；`regime_state` / `portfolio_target`
> 只收紧风控和仓位；任何接入默认在 `ENABLE_INTRADAY_ADVISORY_OVERLAY=0` 后面建设，flag 关时 champion 行为
> 完全不变。M 阶段是 L6「冻结 alpha 接线」的受控例外：先建 shadow/audit 能力，不直接污染 baseline。

## M0 — 决策影响总览（先写清楚，再实现）

| 来源 | 当前产物 | 已有影响 | M 阶段新增影响 | 权限边界 |
|---|---|---|---|---|
| DSA | `signals/dsa_signals.json` | 候选池 + `candidate_score` 25% | 不新增直接影响；继续通过已有评分链路 | 不直接下单 |
| Kronos | `signals/kronos_signals.json` | 候选池 + `candidate_score` 15% | 不新增直接影响；继续通过已有评分链路 | 不直接下单 |
| Technical | `signals/technical_signals*.json` + `trader_watch_levels.json` | 候选池 + `candidate_score` 30% + intraday 入场/止损/止盈硬门槛 | 不改权限，只把 overlay reason 与 technical reason 一起落盘解释 | 仍是执行地图 |
| Catalyst | `planner/catalyst_snapshot.json` | `candidate_score` 20% + intraday 小权重排序 | 不新增硬门槛 | 不直接下单 |
| Quote | `quote_snapshot_*` + live quotes | 盘前 quote 10%；intraday 强制刷新 live quote | 不变 | 旧报价不执行 |
| H2 price factors | `factor_panel.json` / `factor_alpha.json` | calibration/dashboard，write-only | `factor_alpha_score` 与单因子 rank 形成 `rank_delta` | 只调排序，不 block |
| H3 AI signals | `signals/ai_signals.json` | AI study/ablation，write-only | layer confidence / direction 形成 `rank_delta` | 只调排序，不 block |
| K2 regime | `planner/regime_state.json` | dashboard banner，write-only | `risk_off/panic` 可 block new buy；弱 regime 降 sizing multiplier | 只降风险，不放大 |
| K1 portfolio | `planner/portfolio_target.json` | theme/position exposure dashboard，write-only | 超限 block 增仓；接近上限降 sizing multiplier | 只收紧集中度 |

## ~~M1 — Intraday advisory overlay loader + 归一化~~ — ✅ 已完成（2026-06-18）

**目标**：新增一个清晰边界的 overlay 模块，把 advisory artifacts 读成统一结构，供排序、风控、sizing、日志复用。

**具体**：
1. 新增 `policy/advisory_overlay.py`，定义纯函数：
   - `load_advisory_artifacts(paths) -> dict`
   - `build_advisory_overlay(inputs, artifacts) -> AdvisoryOverlay`
   - `overlay_for_symbol(overlay, symbol) -> SymbolOverlay`
2. `SymbolOverlay` 至少含：
   - `rank_delta`
   - `size_multiplier`
   - `block_buy`
   - `blocked_reasons`
   - `reason_codes`
   - `components`（factor/AI/regime/portfolio 的贡献明细）
3. `policy/loaders.py` 在 `ENABLE_INTRADAY_ADVISORY_OVERLAY=1` 时读取：
   - `paths.factor_alpha_path`
   - `paths.ai_signals_path`
   - `planner/regime_state.json`
   - `planner/portfolio_target.json`
4. 缺文件、日期不匹配、schema 不完整时降级为空 overlay，不得影响旧逻辑。

**涉及文件**：`policy/advisory_overlay.py`、`policy/models.py`、`policy/loaders.py`、`core/context.py`（如需补路径）、
`cli.py` doctor 输出、`src/config/runtime.env`。

**验收**：flag=0 时 `load_policy_inputs()` 与现状等价；flag=1 且文件缺失时也不 crash；每个 overlay 字段都有纯函数单测。

**实现记录（2026-06-18）**：
- 新增 `policy/advisory_overlay.py`：`AdvisoryOverlay` / `SymbolOverlay`、`load_advisory_artifacts()`、
  `build_advisory_overlay()`、`overlay_for_symbol()`。
- `PolicyInputs` 新增 `advisory_overlay` 字段；`policy/loaders.py` 仅在
  `ENABLE_INTRADAY_ADVISORY_OVERLAY=1` 时读取 H2/H3/K1/K2 advisory artifacts。
- 缺文件、stale date、坏 JSON、非 dict payload 都降级为空；M1 输出的 `rank_delta=0`、`size_multiplier=1`、
  `block_buy=False`，不改变排序、sizing 或 hard block。
- `runtime.env` 默认 `ENABLE_INTRADAY_ADVISORY_OVERLAY=0`，`doctor` 回显该 flag。
- 测试：`tests/trading_agent/policy/test_advisory_overlay.py` + loader flag 测试；M1 目标测试通过。

**后续**：M2/M3/M4 已继续完成；下一步是 M5 growth overlay evidence。

## ~~M2 — H2/H3 只进入 intraday 排序~~ — ✅ 已完成（2026-06-18）

**目标**：让 `factor_alpha` 和 `ai_signals` 影响候选顺序，但不成为硬拦截。

**具体**：
1. 在 `policy/candidate_selector.py` 的 `rank_candidates()` 中，在原 `trade_readiness_score` 计算后应用
   `rank_delta`，例如 `final_trade_readiness_score = clamp(base + rank_delta, 0, 100)`。
2. `factor_alpha` 规则：
   - `factor_alpha_score >= 80` 小幅加分；
   - `factor_alpha_score <= 30` 小幅扣分；
   - 单个因子只进 `components` 和 reason，不单独 block。
3. `ai_signals` 规则：
   - long + high confidence 小幅加分；
   - short/negative/avoid 小幅扣分；
   - warning code 只扣分或写 reason，不 block。
4. 把 `rank_delta`、`base_trade_readiness_score`、`final_trade_readiness_score`、overlay reason 写入
   `intraday_rankings.jsonl`，否则 growth 无法回放。

**涉及文件**：`policy/candidate_selector.py`、`orchestration/intraday.py`（rankings 落盘字段）、`policy/models.py`、
`tests/trading_agent/policy/test_advisory_overlay.py`、`tests/trading_agent/orchestration/test_intraday_policy_integration.py`。

**验收**：factor/AI 能改变排序；同样输入下不会产生新的 hard block；flag=0 的排序分和原来逐字一致。

**实现记录（2026-06-18）**：
- `build_advisory_overlay()` 根据 H2/H3 生成受限 `rank_delta`：`factor_alpha_score >= 80` 加 3，
  `<= 30` 扣 3；AI layer 只有 `confidence >= 0.70` 时才按方向加/扣 2；总 delta clamp 在 `[-5, +5]`。
- `rank_candidates()` 保留 `base_trade_readiness_score`、应用 `advisory_rank_delta` 后得到最终
  `trade_readiness_score`，并写 `advisory_overlay_rank_delta` reason。
- `_append_intraday_rankings()` 同步落 `base_trade_readiness_score` 与 `advisory_rank_delta`，后续 dashboard/growth 可回放。
- 不新增 hard block、不改 sizing；flag 关闭时没有 overlay，排序维持旧行为。
- 测试：overlay 正/负 delta、ranking 顺序变化但 `blocked == {}`、M4 audit 仍带 overlay。

**下一步**：M3，把 K1/K2 作为只收紧的 hard block / size multiplier 层。

## ~~M3 — K1/K2 只收紧风控和仓位~~ — ✅ 已完成（2026-06-18）

**目标**：让 regime/portfolio 成为 intraday 风险层，而不是 alpha 层。

**具体**：
1. `regime_state`：
   - `panic` 或 `applied_multiplier == 0`：block new buy；
   - `risk_off`：默认 block new buy，或先以 `size_multiplier=0` 实现等价行为；
   - `neutral/weak`：降低 `size_multiplier`；
   - `bull` 的 raw multiplier 即使 >1，也必须 `min(1.0, multiplier)`，不放大仓位。
2. `portfolio_target`：
   - symbol 已超单仓上限：block 对该 symbol 增仓；
   - theme 已超上限：block 该 theme 新买入或增仓；
   - 接近上限但未超限：降低 `size_multiplier`；
   - 不触发卖出，卖出仍由 existing sell policy/technical/hard-stop 负责。
3. `candidate_selector.hard_block_reasons()` 接入 overlay blocked reasons。
4. `sizing_policy.decide_size()` 在原 notional caps 之后乘 `size_multiplier`，且 multiplier 只能 `<=1.0`。

**涉及文件**：`policy/candidate_selector.py`、`policy/sizing_policy.py`、`policy/risk.py`（如需 helper）、
`portfolio/target.py`、`regime/engine.py`、测试。

**验收**：regime risk_off/panic 能阻止新买入；portfolio 超限能阻止对应 symbol/theme 增仓；任何 overlay 都不能把
仓位放大到旧逻辑以上。

**实现记录（2026-06-18）**：
- `build_advisory_overlay()` 根据 K2 `regime_state` 生成风险收紧：`risk_off` / `panic` block new buy；
  `applied_multiplier` 被 clamp 到 `[0, 1]`，只可能降低 size。
- K1 `portfolio_target` 的 `oversize_positions` / `overexposed_themes` 转为 `portfolio_oversize_position` /
  `portfolio_overexposed_theme` hard block。
- `candidate_selector.hard_block_reasons()` 接 `overlay.block_buy`；`sizing_policy.decide_size()` 在旧 sizing
  之后乘 `advisory_overlay` multiplier，并写入 `applied_multipliers` / reason code。
- 测试：regime/portfolio block、size multiplier 只降低 notional、H2/H3 ranking 仍不产生 hard block。

**下一步**：补 M4 dashboard/email 可解释性，把已落盘 overlay 变成可读的一屏解释。

## M4 — 决策可解释性 + dashboard 总览

**目标**：用户能看到「每个因子如何影响这次决策」，而不是只看到最终 blocked/would_trade。

**Dashboard 现状判断（2026-06-18，已补核心视图）**：
- M4 前 dashboard 已有 9 个 tab：Today / Candidates / Decisions / Paper / Strategy Comparison / Calibration /
  Self-Growth / Themes / Trends。
- 已能分散展示 H2 `factor_alpha`、H3 AI study/ablation、K2 regime banner、K1 portfolio target。
- M4 已新增第 10 个 `Decision Overlay` tab，读 `intraday_rankings.jsonl` 展示 base score → overlay rank_delta
  → final score、size multiplier、block reason，以及 factor/AI/regime/portfolio 各自贡献。

**具体**：
1. `PolicyDecision` / `OrderIntent` / `intraday_rankings.jsonl` 增 `advisory_overlay` 字段：
   - per-symbol rank delta；
   - size multiplier；
   - block reason；
   - factor/AI/regime/portfolio contribution。
2. `build_intraday_trade_email_body()` 增中文解释：哪些 overlay 加分、扣分、降仓位、block。
3. dashboard 增只读 **Decision Overlay** 视图（优先作为第 10 个 tab；若后续视觉上过重，可并入 Today/Candidates）：
   - 当前 run 每个候选的 base score / final score / rank_delta；
   - factor_alpha 与单因子贡献；
   - AI layer 贡献；
   - regime/portfolio block 或 multiplier。
4. `dashboard/queries.py` 增 `advisory_overlay_summary(agent_root, run_date)`：
   - 优先读 `intraday_rankings.jsonl` 里的 `advisory_overlay`；
   - join latest decision / order intent，显示最终是否 would_trade / blocked / size changed；
   - 缺 `advisory_overlay` 字段时返回空态，不解析失败。
5. `dashboard/charts.py` 增 overlay table + contribution breakdown：
   - 每个 symbol 一行：base score、final score、rank_delta、size_multiplier、block_buy、blocked_reasons；
   - 展开或子表显示 `components`（factor/AI/regime/portfolio）；
   - 对 `block_buy=true`、`size_multiplier<1`、`rank_delta<0` 做醒目标记。
6. `tests/trading_agent/dashboard/test_queries.py` / `test_app_smoke.py` 增空态 + 有 overlay 字段两条用例；headless
   `AppTest` 必须覆盖新 tab/视图。

**涉及文件**：`policy/models.py`、`orchestration/intraday.py`、`notifications/trade_email_reports.py`、
`dashboard/{queries,charts,app}.py`、`analytics/loaders.py`。

**验收**：任一 intraday run 可回放“为什么这个 symbol 排到前面/为什么被 block/为什么仓位变小”；dashboard 缺字段时空态不 crash；
现有 tab 继续正常渲染，新 overlay 视图仍只读、不写 YAML、不触发交易。

**已完成（2026-06-18）**：
- `OrderIntent.to_json_dict()` 增 `advisory_overlay` 字段；buy intent 从 `PolicyInputs.advisory_overlay` 把当前 symbol
  的 overlay 原样带入 proposed order。
- `_append_intraday_rankings()` 写入 ranked rows 和 blocked rows 的 per-symbol `advisory_overlay`，便于 replay/dashboard
  后续读取。
- `build_intraday_trade_email_body()` 增 overlay 中文解释：排序调整、仓位乘数、factor/AI/regime/portfolio 摘要。
- dashboard 新增第 10 个 `Decision Overlay` tab：`advisory_overlay_summary()` 直接读 rankings JSONL，空态不 crash。
- 测试：intraday ranked/blocked overlay audit、dashboard query、email overlay 段；dashboard AppTest 在无 streamlit 环境自动 skip。

**仍可增量**：更漂亮的 contribution breakdown、按日期趋势化、join latest order fill/slippage。

## M5 — Growth 分析 advisory overlay 效果

**目标**：growth 不只看旧的 DSA/Kronos/Technical/Catalyst/Quote，也能评估 M 阶段 overlay 是否真正改善结果。

**具体**：
1. `replay/forward_returns.py` 把 `advisory_overlay.components` 纳入 `ForwardReturnRecord.components`：
   - `factor_alpha`
   - 单个 price factor rank
   - `ai_composite`
   - `regime_multiplier`
   - `portfolio_multiplier`
   - `final_rank_delta`
2. `calibration_report` 自动给这些组件出 bucket / IC；复用已有动态 components 机制。
3. `growth/evidence.py` 增 evidence 类型：
   - `factor_overlay_positive_ic`
   - `ai_overlay_confidence_calibrated`
   - `regime_block_reduced_loss`
   - `portfolio_block_reduced_concentration`
4. `growth_policy.json` 增允许 mutation，但仍 paper-only：
   - `overlay.factor_weight`
   - `overlay.ai_weight`
   - `overlay.regime_size_multiplier`
   - `overlay.portfolio_near_cap_multiplier`
   - 每项有 min/max/max_delta；禁止触碰 `TRADING_MODE` / real order / risk tier。
5. proposal 只写 `runtime/strategy_proposals/<date>/`，进入 shadow 后才可验证，人工才可 promote。

**涉及文件**：`replay/forward_returns.py`、`replay/calibration.py`、`growth/evidence.py`、`growth/proposals.py`、
`growth/validator.py`、`src/config/growth_policy.json`、`analytics/snapshot.py`、`analytics/trend.py`。

**验收**：growth 能回答「factor/AI overlay 是否提升 forward return」「regime/portfolio block 是否减少坏交易」；
proposal 有证据、过 validator、仍不改 champion。

**已完成（2026-06-18，core）**：
- `replay/forward_returns.py` 从 `intraday_rankings.jsonl.advisory_overlay` 自动折出 components：
  `final_rank_delta`、`advisory_size_multiplier`、`factor_alpha`、`ai_composite`、`regime_multiplier`、
  `portfolio_position_weight`。
- 既有 calibration 动态分桶/IC 机制会自动覆盖这些新 components，无需新增固定字段。
- `growth/evidence.py` 从 `calibration_report.attribution` 抽取 overlay component IC，形成
  `calibration.overlay_component_ic` evidence。
- `growth_policy.json` 新增 bounded paper-only overlay mutation 白名单：`factor_weight`、`ai_weight`、
  `regime_size_multiplier`、`portfolio_near_cap_multiplier`；现有 validator 负责 range/max_delta/paper_only 校验。
- 测试：forward returns overlay pickup、growth evidence overlay IC、overlay mutation validator。

**仍待做**：proposal rule 自动基于 overlay evidence 生成 paper-only 调参建议；当前只完成 evidence 与安全边界。

**M 阶段总验收**：
- `ENABLE_INTRADAY_ADVISORY_OVERLAY=0`：现有所有 intraday 逻辑、排序、sizing、decision 输出保持旧行为。
- `ENABLE_INTRADAY_ADVISORY_OVERLAY=1`：H2/H3 只改排序；K1/K2 只 block/降仓位；所有影响写进 audit。
- review/live 仍不接真实下单；paper/shadow 先跑 15–30 个交易日再考虑人工 promote。

---

# L 阶段 · 收口与验证（外部评审二 · P0，2026-06-17）

> 评审二的核心判断：最近改动方向对、但节奏快、**文档开始漂移**，现在最该做的不是加功能，而是**收口 + 验证 +
> 跑数据**。

## L1 — 文档权威源收敛 — 🟢 进行中（2026-06-17）

**已做**：`project-status.md` 顶部加 **point-in-time 约定**（第二/三节为当前事实源，历史段的「未做」不代表现状）+
更正状态表（J1 兜底硬止损 ✅、I1 夜间自动化 ✅、dashboard **9 Tab**、E1 机器已建）；README 已按三时段重写
（premarket DAG + strategy 决策流程图）。**职责划分**：README=怎么跑 · project-status=当前状态 · roadmap=下一步 ·
strategy.md=策略理念/规则 · playbook=每天操作。**每次功能完成只更对应两份，别到处重复写。**

**剩余**：第四节「明确未做」与各 P5 历史段里仍有零散过期断言——已用顶部 point-in-time 约定统一兜底，逐条精修优先级低。

## L2 — 完整 smoke checklist → `docs/smoke-test.md` — ✅ 已完成（2026-06-17）

`src/scripts/smoke/run_smoke.sh`：一条龙集成验证 + PASS/FAIL 汇总。
- **必跑（本地、确定性）**：`doctor` · `safety/check_safety.sh` · `analytics build/fill-quality/weight-suggestion/
  snapshot/trend/nightly-health` · `replay` · `growth observe/propose/shadow/evaluate`——任一失败则 smoke exit≠0。
- **opt-in**：`SMOKE_INCLUDE_NETWORK=1` 加 yfinance 类（calibrate/ai-signal-study/ai-ablation）；
  `SMOKE_INCLUDE_LIFECYCLE=1` 加 premarket/intraday/postmarket 干跑（需 Codex/MCP）——这些失败标 `FAIL(opt)`、不挂 smoke。
- 文档 `docs/smoke-test.md`（用法 + 各步含义 + 「unit tests 证逻辑 / smoke 证接线」）。pytest 锁定脚本存在 + 语法。

**验收**：✅ 一键跑通、失败步骤清晰可见（实跑 13/13 本地命令 PASS，exit 0）。证逻辑用 `pytest`、证接线用 smoke。

## L3 — H2 factor benchmark coverage 审计 — ✅ 已完成（2026-06-17）

**问题（已核实）**：premarket `collect_market_context(symbols=active_symbols)` 只采 active_watchlist；而 factor
层读 `load_daily_bars(market_feed_dir, "SPY")`。若某 strategy watchlist 不含 SPY，则 benchmark bars 缺失，
beta/residual/relative 因子**静默全 None**。

**已做**：
- `factor_store.BENCHMARK_SYMBOLS = (SPY, QQQ, SMH, IWM)`；premarket 把它 **union 进 market_feed 采集 symbols**
  （`feed_symbols = active_symbols ∪ BENCHMARK_SYMBOLS`），benchmark 只为取 bars、**不进**评分/technical 集。
- `compute_coverage()`：报告 active 数 / 有 daily bars 数 / coverage% / missing_symbols / benchmark bar 数 /
  `benchmark_available`（≥60 bars）。写进 `factor_panel.json` 与 `factor_alpha.json` 的 `coverage` 字段。
- dashboard `factor_view` 顶部显示 coverage%（多少 symbol 有 bars + benchmark 是否齐 ✅/⚠️）。

**验收**：✅ benchmark bars 恒被采；✅ coverage% + benchmark 可用性可见（json + dashboard）；✅ 数据缺失不 crash
（标低 coverage）。450 测试通过。

## L4 — nightly health / freshness — ✅ 已完成（2026-06-17）

I1 夜间批处理是 best-effort（单步失败被吞），有「以为健康、实际某步一直失败」的风险。**已做**：
- `analytics/nightly_health.py` + CLI `analytics nightly-health`：`build_nightly_health` 检查各预期报告的
  **新鲜度**（generated_at age > 30h 或缺失 → stale）+ 读最近一次 nightly 的 **step_results.jsonl** 拿失败步骤；
  `status` 仅在「无 stale + 无失败」时为 `ok`，否则 `attention`。写 `nightly_health.json`。
- `run_nightly_analysis.sh`：每步 `run_step` 写一行 `step_results.jsonl`（ok/fail + exit_code），末步调
  `analytics nightly-health` 汇总。
- dashboard Trends tab **顶部 banner**：🟢 OK / 🔴 ATTENTION（列出失败步骤 + stale/缺失报告），静默失败一眼可见。

**评审二另建议**（留作人工决定）：是否把 `ENABLE_NIGHTLY_ANALYSIS` 默认改 0 / 要求手动装调度——**未改默认**
（保持 1）；health 文件已先把静默失败暴露出来，默认值是产品取舍，留给人工。**验收**：✅ 报告 stale / 步骤失败
都进 `status=attention` + dashboard 红 banner；纯只读。457 测试通过。

## L5 — premarket factor-failure advisory 测试 — ✅ 已完成（2026-06-17）

测试 `test_advisory_signal_failure_does_not_break_pipeline`：注入抛异常的 advisory stage（H2 因子层），断言
`pipeline.run()` 不抛、确定性 score/plan 尾段（candidate_scoring → risk_overlay → final_planner → archive）
仍跑、另一 advisory stage（ai_signals）也仍跑。**实现细节（已核实）**：`run_stage` 异常时在 stage-log 记
`failed`（非 `advisory_failed`），`_run_advisory` 吞掉异常让 pipeline 继续——两层共同保证 advisory 失败不阻断
premarket。**验收**：✅ 测试通过（450 → 451）。

## L6 — 冻结 alpha 接线 + 跑 paper 15–30 天 — ⏳ 纪律项（非代码）

**H7/H8 保持 skeleton-only，1–2 周内不接 scoring / premarket 热路径**；别同时把多个新 alpha 开进 shadow（否则
attribution 无法判断谁有贡献）。先让 H2 因子 / H3 AI 归因 / E1 校准 / E2 建议 / nightly snapshot/trend / J1 硬止损
跑稳、攒够 15–30 个交易日，再用 E1/E2/H3/M5 结果选第一个真 challenger。

**M 阶段是受控例外，不是解除冻结**：允许实现 loader、overlay、audit、dashboard、growth 分析，但默认 flag 必须为
0；即使打开，也只能先 paper/shadow，H2/H3 只改排序，K1/K2 只 block/降仓位。任何 champion 权重、阈值或真实交易
影响，都必须等 15–30 个交易日证据 + 人工 approve。**这是当前阶段价值最高的纪律项。**

---

# N 阶段 · 数据存储强化（空数据期红利，2026-06-18）

> 来源：用户在「现在还没有真实 paper 数据」时提的问题——趁 `analytics.db` 的表都还是空的，把存储管道
> 打磨好，避免攒了 15–30 天数据后才发现 schema 有坑、改了要重 build + 验证。
>
> **现状架构（已核实）**：真源（source of truth）是 `runtime/state/runs/<date>/` 和
> `runtime/logs/runs/<date>/audit/` 下的 JSON/JSONL 文件；`analytics.db` 是 `analytics build`
> **drop + recreate** 出来的派生视图（幂等、可随时重建）。dashboard 的 Today/Candidates/Decisions/Paper
> 等核心 tab 查 db；calibration/growth/thesis 直接读 JSON。`schema.py` 定义 6 张表 DDL，`loaders.py`
> 从文件抽字段，`build_db.py` 落库。
>
> **贯穿原则**：这些都是**手动命令 / 离线分析路径**（不接 premarket/intraday 热路径），天然隔离、
> **不需要 feature flag**（同 calibration/growth）。db 是派生视图、可重建，所以 schema 改动**无需 migration**——
> 重 build 即生效。改动只需保证 dashboard 现有 SQL 查询不破。

## N1 — analytics.db schema 漂移修复 — ✅ 已完成（2026-06-18）

**实现记录**：`orders` 表补 `setup_type/stop_price/target_1/target_2/reward_risk/confidence`（E1 setup
outcomes）+ `bid/ask/mid_price/spread_bps/slippage_bps`（E4 成交质量）；`decisions` 表补
`per_candidate_blocks/advisory_overlay/thesis_tags`（E3/M4/K3，存 JSON 字符串）；`intraday_rankings` 补
`base_trade_readiness_score/advisory_rank_delta/advisory_overlay`（M2/M4）；新增 `factor_alpha`（H2，逐
run_date×symbol）/`regime_state`（K2，逐 run_date）/`portfolio_target`（K1，逐 run_date，含 sector）三张表 +
对应 `load_factor_alpha/load_regime_state/load_portfolio_target`。实跑 `analytics build` 出 10 表（含新 3 表），
空数据 0 行不报错；既有 dashboard 查询全保持可用。

<details><summary>原计划（存档）</summary>

**目标**：让 `analytics.db` 的 schema + loaders 跟上这几轮新增的所有落盘字段，并为新 advisory 产物补表，
让数据进来后能直接用 SQL join/聚合/趋势分析，而不是只能从零散 JSON 翻。

**问题（已核实，按表）**：
- `orders` 表缺：`bid` / `ask` / `mid_price` / `spread_bps` / `slippage_bps`（E4 成交质量已落进
  `orders.jsonl`，但没进 db）、`thesis_tags`（K3）、`advisory_overlay`（M4）。
- `decisions` 表缺：`per_candidate_blocks`（E3 near-miss 逐候选 block）、`advisory_overlay`（M4）、
  proposed_order 里的 `thesis_tags`。
- `intraday_rankings` 表缺：`base_trade_readiness_score` / `advisory_rank_delta` / `advisory_overlay`
  （M2/M4 已落进 `intraday_rankings.jsonl`）。
- **完全没有的表**：`factor_alpha`（H2 每日落盘）、`regime_state`（K2）、`portfolio_target`（K1，含 sector）、
  `thesis_attribution`（K3）、`fundamental_snapshot`（H7）、`event_snapshot`（H8）。这些现在只有 JSON，
  没进 db，无法跨 run 用 SQL 看趋势。

**具体步骤**：
1. `schema.py`：给 `orders` / `decisions` / `intraday_rankings` 补上述列；新增 `factor_alpha` /
   `regime_state` / `portfolio_target` 表（thesis/fundamental/event 可后置——它们已有专门 JSON 报告 +
   dashboard，进 db 优先级略低）。复杂嵌套字段（`advisory_overlay` / `per_candidate_blocks`）按既有
   `blocked_reasons` / `reason_codes` 的惯例存 `json.dumps` 字符串。
2. `loaders.py`：对应 `load_orders` / `load_decisions` / `load_intraday_rankings` 补抽字段；新增
   `load_factor_alpha` / `load_regime_state` / `load_portfolio_target`（从 `factor_alpha_path` /
   `planner/regime_state.json` / `planner/portfolio_target.json` 读，缺文件返回空，不报错）。
3. `build_db.py`：把新表加进 `table_rows`（drop+recreate 逻辑无需改）。
4. dashboard：现有查询全部保持可用（只增列不删列）；可选给新维度加只读查询/视图（增量）。
5. 测试：每个新 loader 有单测（mock run 产物 → 断言抽出的行）；`build_analytics_db` 在含新字段的
   mock run 上断言新表/列被填充；空数据下不报错。

**涉及文件**：`analytics/schema.py`、`analytics/loaders.py`、`analytics/build_db.py`、
`dashboard/queries.py`（可选新查询）、对应测试。

**验收**：`analytics build` 后 `orders`/`decisions`/`intraday_rankings` 含新列；`factor_alpha`/`regime_state`/
`portfolio_target` 表存在且在有数据时被填；dashboard 现有 tab 全部正常；空数据下 build 不报错。

</details>

> **剩余（增量，优先级低）**：thesis_attribution / fundamental_snapshot / event_snapshot 进 db——它们已有专门
> JSON 报告 + dashboard，进 db 价值低，等需要跨 run SQL 分析时再加（加一张表 + 一个 loader）。

## N2 — analytics.db 索引 — ✅ 已完成（2026-06-18）

**实现记录**：`schema.py` 增 `INDEX_DDL`，`build_db.py` 建表 + 落数据后逐条建索引（随 drop table 隐式重建、零
维护）。覆盖 `candidates(run_date)` / `decisions(run_date)` / `orders(run_date,status)` /
`intraday_rankings(run_date,symbol)` / `paper_equity(run_date,timestamp)` / `blocked_reasons(run_date)` /
`factor_alpha(run_date,symbol)`。实跑 build 后 `sqlite_master` 含全部 7 个 `idx_*`。

<details><summary>原计划（存档）</summary>

**目标**：防数据增长后全表扫描。现状除 `runs`（PRIMARY KEY run_date）外无任何索引，所有
`WHERE run_date=?` / `ORDER BY timestamp` 都全表扫。几十交易日 × 几十候选 × 每天多次 intraday 后
`candidates` / `intraday_rankings` 会到几万行。

**具体步骤**：`build_db.py` 建表后对常用过滤/排序列建索引：
`candidates(run_date)`、`decisions(run_date)`、`orders(run_date, status)`、
`intraday_rankings(run_date, symbol)`、`paper_equity(run_date, timestamp)`、`blocked_reasons(run_date)`。
索引随 drop table 一起重建，零维护。

**涉及文件**：`analytics/build_db.py`（或 `schema.py` 增 `INDEX_DDL`）、测试（断言索引存在）。

**目标**：防数据增长后全表扫描。现状除 `runs`（PRIMARY KEY run_date）外无任何索引，所有
`WHERE run_date=?` / `ORDER BY timestamp` 都全表扫。几十交易日 × 几十候选 × 每天多次 intraday 后
`candidates` / `intraday_rankings` 会到几万行。

**具体步骤**：`build_db.py` 建表后对常用过滤/排序列建索引：
`candidates(run_date)`、`decisions(run_date)`、`orders(run_date, status)`、
`intraday_rankings(run_date, symbol)`、`paper_equity(run_date, timestamp)`、`blocked_reasons(run_date)`。
索引随 drop table 一起重建，零维护。

**涉及文件**：`analytics/build_db.py`（或 `schema.py` 增 `INDEX_DDL`）、测试（断言索引存在）。

**验收**：build 后 `sqlite_master` 含上述索引；既有查询结果不变；大行数下 `EXPLAIN QUERY PLAN` 走索引。

</details>

## N3 — build 数据校验 + `analytics validate` — ✅ 已完成（2026-06-18）

**目标**：build 当前用 `.get()` 静默吞缺失/坏字段——一行格式错的 JSONL 会无声变成一行 NULL。需要能一眼看到
「多少行坏 / 缺关键字段」，否则脏数据会污染 calibration/IC 而不自知。

**实现记录**：新增 `analytics/validate.py` + CLI `analytics validate [--since --until]`——只读扫每个 run 的 4 个
JSONL 源（decisions / orders / paper_equity / intraday_rankings），逐源逐 run 统计 `lines/parsed/malformed`
（坏 JSON 或非 dict）/`missing_key`（缺该源必填字段，如 decision 缺 `timestamp`/`decision`、order 缺
`order_id`/`symbol`/`status`），含 `missing_key_detail`（哪个字段缺了几次）。写 `validate_report.{json,md}`，
markdown 只列「有问题的 run date」保持简短；`status` 仅在无坏行无缺字段时为 `ok`，否则 `attention`。接进夜间
批（`analytics build` 之后立即跑）。**纯只读、改不动任何数据**；空数据 status=ok 不报错。

> 设计取舍：未改 `build_analytics_db` 的返回签名（保持 `{table: count}` 契约、不破坏既有测试）——校验做成
> 独立命令而非塞进 build。孤儿引用检查（order ↔ decision 弱关联）未做，避免误报，优先级低、留作后续增量。

**涉及文件**：新增 `analytics/validate.py` + `tests/.../test_validate.py`；`cli.py`（命令 + 回显）；
`run_nightly_analysis.sh`（接进批处理）。

**验收**：✅ `analytics validate` 在故意注入坏行/缺字段的 mock run 上准确报告（per-source + per-run）；
✅ 纯只读不改数据；✅ 空数据不报错（实跑 3 个 run date status=ok）。601 测试通过。

## N4 — 数据保留 / 归档策略 — ✅ 已完成（2026-06-18）

**目标**：`runtime/state/runs/*` 随每个交易日无限增长，最大占用是 `market_feed/`（全 universe 的 OHLCV JSON +
charts PNG + news）——一个 premarket **输入快照**，post-hoc 分析都不读（calibration 用 yfinance 拉 forward
returns，replay/build 读小 JSON）。所以对超过保留窗的旧 run 只 prune 这类大产物、保留全部分析输入。

**实现记录**：新增 `analytics/retention.py` + CLI `analytics retention [--keep-days N] [--apply]`——
`plan_retention` 列出比 `today - keep_days`（默认 60 天）更老的 run，统计其 `market_feed/` 大小（默认仅 prune
`market_feed`，列表可扩展）；`apply_retention` 仅在 `--apply` 时 `rmtree`；写 `retention_report.{json,md}`
（dry-run 标 `DRY-RUN`、列可 prune 的 run + 释放 MB）。

**红线（已内建 + 测试）**：默认 **dry-run、不删任何东西**；绝不碰保留窗内的 run；**只删配置的 prune 目录
（默认 market_feed）、绝不删分析输入小 JSON**（candidate_scores/decisions/orders/run_manifest 全保留→
calibration/replay 仍可跑）；绝不碰 src/config / KILL_SWITCH / runs 目录外的东西。已 prune 的 run 不再重复列出。

**涉及文件**：新增 `analytics/retention.py` + `tests/.../test_retention.py`；`cli.py`（命令 + 回显）。

**验收**：✅ 旧 run 的 market_feed 被列/删、窗内 run 不动；✅ apply 后分析输入小 JSON 仍在（calibration 可降级
运行）；✅ 默认 dry-run 不删；✅ 已 prune 的 run 不重复列。608 测试通过。

## N 段推荐执行顺序（全部已完成 2026-06-18）

1. ✅ **N1 schema 漂移**——价值最高、趁空数据做。
2. ✅ **N2 索引**——和 N1 一起做。
3. ✅ **N3 校验**——`analytics validate`，真数据进来前就位。
4. ✅ **N4 保留策略**——`analytics retention`，代码先就位（默认 dry-run，数月后目录变大时 `--apply`）。
