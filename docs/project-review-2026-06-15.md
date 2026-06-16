# 交易系统全局审查（基于真实代码逐条核对）

> 日期：2026-06-15
> 范围：`src/trading_agent/` 全量（约 6000 行 Python）+ 配置/编排/入口
> 方法：把一份外部（ChatGPT）分析里的每条代码断言都落到真实文件 `file:line` 上验证，纠正其中不准/错误的部分，并补充其遗漏的更关键问题。
> 修订：2026-06-15 收到对本审查的二次评审，已并入 5 处细化并保留 1 处技术性分歧，详见第四部分。

---

## 第一部分：先纠正外部分析

方向感不错，但有几处是**猜测**（原文自承"搜索没看到"），还漏了几个比它列出的 P0 更要命的问题。

### ✅ 说对的（已逐条在代码里确认）

| 断言 | 证据 | 结论 |
|---|---|---|
| `market_context` 串行逐 symbol + 每天 `rmtree` 全量重建 | `data/market_context.py:173-174, 184` | 属实 |
| `candidates` 直接读 `universe.txt`，最后 `selected[:20]` | `planner/candidates.py:43, 78` | 属实 |
| `rank_candidates()` 重复计分 | `policy/candidate_selector.py:118-125`，`candidate_total` 占 0.35+0.15=**0.50** | 属实，且比原文说的更严重 |
| `_quote_symbols()` 含全 universe | `policy/loaders.py:198` | 属实 |
| paper fill 价 = limit，无滑点/部分成交/撤单 | `paper/broker.py:211, 439` | 属实 |
| scoring 用 normalized effective-weight，不是 missing=0 | `planner/scoring.py:468-470` | 属实，这块写得好 |
| DSA/Technical subagents = 10、codex timeout=3600 | `src/config/runtime.env:17,46`、`prompts/codex.py:57` | 属实 |
| 无 replay/calibration、无 `watchlist_curator.py`/`watchlist_universe.yaml` | CLI 只有 premarket/intraday/postmarket/dsa | 属实 |

### ⚠️ 说得不准 / 需要修正的

1. **"universe 太大" → 实际只有 88 个**（`universe.txt`）。问题不是"多到处理不了"，而是这 88 个**全部**进了：Kronos 本地推理 + market_feed（4 timeframe × 88 = 352 次 yfinance + 串行画图）+ DSA/technical 全量 AI。瓶颈是**串行 I/O 和本地模型推理**，不是"标的数量爆炸"。分层值得做，但要按 88 这个量级设计，别照搬"core 120 / active 30"。

2. **"intraday 拉全 universe quote" → 是一次 batched `yf.download(threads=True)`**（`data/live_quotes.py:16-24`），不是 88 次独立请求。仍然浪费，但严重程度低一个量级。

3. **"final planner 会重新做深度分析" → prompt 已约束它"只 copy 不重算"**（`prompts/premarket/final_research.txt:77-78` 明确要求从 `RISK_OVERLAY_PATH` 复制 regime/watchlist/actions，只补叙述）。担心已部分被规避。**但要点是：真正的护栏是 `normalize_daily_plan_state()` 这个确定性 normalize，不是 prompt 本身**——prompt 约束只降低概率，normalize 才是保证。且该 normalize 覆盖 `daily_plan.json`（state/watchlist/actions），**不覆盖 `today_allowlist.txt`**，所以见 🔴 第 4 条的 allowlist 兜底仍然必须。

4. **"price policy 只 block/pass 没分数" → 它其实产出了 `reward_risk` 和 `risk_per_share`**（`policy/price_policy.py:68-71`）。真正的问题是**排序发生在定价之前**，价格 setup 质量没能反哺排序。

### 🔴 完全漏掉的（这几条比它的 P0 更该先修）

1. **`runtime.env` 根本不被 Python 入口加载。** `core/config.py:16-24` 只读 `os.environ`，没有 dotenv 逻辑。只有 shell 脚本（`src/scripts/lib/common.sh:67-76`）会 `source` 它。后果：
   - 按 README 跑 `python3 -m trading_agent premarket`（README 第 12、311 行主推）→ 拿到**代码默认值**：`RISK_TIER=0`、Kronos 默认开等。
   - 走 cron 的 `run_premarket.sh` → source 了 runtime.env → `RISK_TIER=3`。
   - **同一套代码，两个入口，跑出两套配置**，结果不可复现。

2. **`RISK_TIER` 代码默认 0 = micro_test = 单笔 $10 / 日 $25**（`risk_tiers.json:2-8`）。`risk_overlay.py:158-162` 里 `max_single = min(tier_cap, buying_power)`，sizing 又 `min(..., symbol_cap)`（`sizing_policy.py:124-133`）。即**只要没 source runtime.env，所有 paper 买单都会被压到 $10**，整套 risk-budget / weight-cap 机制全部被架空。即便 source 了（tier 3=$5000），$5000/$400k≈1.25% 权重，和 `per_trade_risk_pct=0.5%` 之间没有一致性校验。

3. **`live_quotes.py` 把 `previous_close` 直接设成 `price`**（`data/live_quotes.py:40, 61`）→ 下游 `change_pct` 恒为 0。目前 intraday 主要用 `quote.price`，没炸，但是埋着的脏数据。

4. **`today_allowlist.txt` 完全由 AI final planner 写，没有确定性兜底。** intraday 交易闸门是 `eligible = today_watchlist ∩ universe ∩ today_allowlist`（`policy/risk.py:21-24`），而 `today_allowlist.txt` 只在 `final_research.txt:82` 由 Codex 写。`today_watchlist` 是确定性的（被 `normalize_daily_plan_state` 从 risk_overlay 覆盖），**但 allowlist 不是**。final planner 失败/dry-run/AI 写空 → allowlist 缺失 → intraday 静默不交易。

5. **`scoring.py` 每个 symbol 重复读 4 个 JSON 文件**（`planner/scoring.py:514-523`）→ 20 候选 = 80 次磁盘读，本该 4 次。

6. **pending paper order 永不过期、永不撤单**——`record_paper_day_end`（`paper/broker.py:144-153`）不处理 pending。

7. **Kronos 对全 88 个跑本地推理**（`orchestration/premarket.py:123`）。很可能是 premarket **真正最慢**的一环（本地模型，不是 AI token），优化手段与 token 优化完全不同。

---

## 第二部分：逐模块审查与改进

按数据流顺序，每块给「现状 → 问题 → 怎么改」。

### 1. 配置与入口层（最该先修）
**现状**：`runtime.env`（RISK_TIER=3, PAPER_STARTING_CASH=400000）只被 shell 脚本 source；`python -m trading_agent` 走代码默认值。

**改进**：
- `core/config.py` 加轻量 env 文件加载：启动时按 **`runtime.env` → `runtime.env.local`（local 覆盖）** 顺序解析进 `os.environ`，**两者都不覆盖已 export 的 shell env**（显式 export 仍最高优先）。二三十行手写解析即可，不引第三方。
- 加 `trading_agent doctor` 子命令：打印**生效值**——`TRADING_MODE` / `RISK_TIER` / `PAPER_RISK_TIER` / `POLICY_PROFILE` / `SCORING_PROFILE` / `KILL_SWITCH` / `PAPER_FILL_MODEL` / 各 `ENABLE_*` 开关 / `MARKET_FEED_TIMEFRAMES` / `DSA_MAX_SUBAGENTS` / `TECHNICAL_MAX_SUBAGENTS` / **effective `max_single_order_notional` 与 `max_daily_notional`**。
- **解耦 paper sizing 与 live 晋升 tier**：paper 别用 `RISK_TIER=0` 的 $10 上限去测。引入 **`PAPER_RISK_TIER` / `LIVE_RISK_TIER` 显式拆分**（或 `TRADING_MODE=paper` 时走 paper caps，review/live 时走 live caps），让 paper 真正按 `per_trade_risk_pct` 跑出有意义仓位。

### 2. Universe / 选股池（`data/universe.py`, `planner/candidates.py`）
**现状**：88 个静态 `universe.txt` → 全量喂上游 → candidates 取信号交集后 `[:20]`。

**改进**（分层方向对，但按 88 量级裁剪）：
- 不必急着搞 `watchlist_universe.yaml` 那一大套。先给 `universe.txt` 加 **tier 标记**（注释段或并行 `universe_meta.json`：`tier`、`theme`、`liquidity`）。
- 引入 **`active_watchlist`（≤30）**，**只让重活（Kronos、technical AI、market_feed 4 timeframe）跑 active**，core 其余降级为"仅 quote + 轻量扫描"。直接砍掉 Kronos/market_feed 约 2/3 工作量。
- `selected[:20]` 魔数提到 scoring_profile 配置化。

### 3. Market feed（`data/market_context.py`）
**现状**：`rmtree` 全删 → 串行 88×4，每个 yfinance history + 画 PNG。

**改进**：
- **去掉每天 `rmtree`**，按 `(symbol, timeframe, date)` 增量缓存，同日重跑复用。
- 历史价用 **`yf.download` 批量**（`live_quotes.py` 已有此能力，复用过来），news/filings 用 `ThreadPoolExecutor` 并发。
- **确认图表 PNG 给谁看**——如果 technical 的 Codex 读 JSON 数值而非看图，PNG 纯浪费，直接砍或只给 active 画。

### 4. 信号层（DSA / Kronos / technical）
**现状**：DSA/technical subagents=10，全 universe；Kronos 全 88 本地推理。

**改进**：
- subagents 默认降到 **3**，周末/手动深研再开 8。
- **Kronos 只跑 active_watchlist + 持仓**，省时间（本地推理）收益最大。
- technical/DSA 输入改成 **compact JSON 摘要**（trend / 距均线 / ATR% / 量比 / 支撑阻力 / 新闻条数），别让 AI 读原始 chart/news 文件。

### 5. 打分（`planner/scoring.py`）— 整体质量最高
**现状**：effective-weight 归一化、coverage、score_status、catalyst fallback、technical action 映射都到位。

**改进**（小修）：
- 修那 80 次重复读文件（4 个 JSON 提到推导式外读一次）。
- `MIN_EFFECTIVE_COVERAGE` 常量（36 行）和 profile 值统一来源。

### 6. 候选排序（`policy/candidate_selector.py`）— 有真 bug
**现状**（118-125 行）：
```python
trade_readiness = 0.35*candidate_total + 0.25*technical + 0.10*liquidity
               + 0.10*research + 0.05*catalyst + 0.15*candidate_total
```
`candidate_total` 出现两次（=0.50），且它内部**已含** technical(0.30)、catalyst(0.20)。technical/catalyst 被重复加权，`0.15*candidate_total` 几乎肯定是复制粘贴残留。

**改进**：删掉 `0.15*candidate_total`，把权重重分配给**排序当下缺失的维度**——price-setup 质量和 reward/risk（需先解决"排序在定价之前"，见第 7 节）。**注意**：新权重不要写死成另一组魔数，先用 replay 的 component attribution 验证（见 P2）。

### 7. 定价与排序的结构问题（`price_policy.py` + `candidate_selector.py`）
**现状**：`rank_candidates` 先排序，`evaluate_buy` 再逐个 `decide_buy_price`。reward/risk、是否在 entry zone、是否要追高——这些**最能决定"今天该不该买它"的信息没参与排序**。

**改进**：改成单趟逐候选评估再排序——
```
for each eligible candidate:
    hard gate → candidate_score → price_policy(reward_risk, setup, 距 entry zone)
             → sizing feasibility → compute trade_readiness
sort by trade_readiness
```
把 `decide_buy_price` 的产出折成 `price_setup_score` / `reward_risk_score`，**纳入 trade_readiness**。排第一的应是"既高分又恰好到位"的票，而不是"分高但已追不进去"的票。**策略质量单点收益最大的改动。** 但权重（如 0.30/0.25/0.20/…）是起点，不是结论——必须用 replay 校准后再固化（见 P2）。

### 8. 风险覆盖（`planner/risk_overlay.py`）— 写得好
watchlist/tradable 分层、observe_only/no_trade 区分都对。小点：`today_watchlist = watchlist_candidates` 在三分支重复（171/177/183），可提取。功能无问题。

### 9. Sizing（`policy/sizing_policy.py`）— 逻辑完整但被配置架空
逻辑本身（risk budget → 各 cap 取 min → 乘 multiplier）正经。问题在第 1 节：被 `RISK_TIER` notional cap 架空，先修配置才测得出。另：`final_notional *= profile_multiplier`（134 行）在 cap 取完 min **之后**乘——multiplier 只会买更少不会破 cap，语义正确，确认这是预期。

### 10. Paper broker（`paper/broker.py`）— 下一步重点
**现状**：conservative 模型（限价没到 pending），fill 价 = limit。

**改进**（叠加在现有 `_can_fill` 成交闸门之上，闸门已保证 buy 仅当现价≤limit、sell 仅当现价≥limit 才成交）：
- fill 价精确化：买 `fill = min(limit, 当前价*(1+slippage))`、卖 `fill = max(limit, 当前价*(1-slippage))`。注：当前模型固定成交在 `limit`，对**买单偏悲观**（真实会在 limit 之下成交、有价格改善），这个改动同时让买入成本更真实。
- 加 `PAPER_PENDING_MAX_AGE_MINUTES` + `PAPER_CANCEL_PENDING_AT_DAY_END`：在 `record_paper_day_end` 里把当天未成交 pending 标 `pending_canceled`（写 `reason: day_end_expired`）。
- 目的：让 paper 成交统计接近真实——这是 calibration 的输入。

### 11. Intraday（`orchestration/intraday.py` + `loaders.py`）
**改进**：
- `_quote_symbols` 砍掉 `inputs.universe`（`loaders.py:198`），改成 `持仓 ∪ 挂单 ∪ tradable_candidates ∪ today_watchlist[:8]`。
- 修 `previous_close=price` 脏数据。
- `today_allowlist` 加确定性兜底：final planner 没写/写空时用 `risk_overlay.tradable_candidates` 兜底。

### 12. Postmarket（`orchestration/postmarket.py`）— 缺校准
**现状**：有 paper PnL/成交汇总（好），但没有"分数桶 vs 未来收益"的回看。
**改进**：见路线图 P2，晋升 live 前最该补的能力。

---

## 第三部分：校准过的优先级路线图

目标是**在 paper 里跑出可信、可复现、可校准的结果，再考虑 live**。universe 才 88 个，系统能跑；真正卡"可信度"的是配置漂移、脏数据和没有校准数据。所以优先级与外部分析不同：

### P0 — 正确性与一致性（不修这些，后面优化都建在流沙上）
1. Python 入口加载 `runtime.env` →（`runtime.env.local` 覆盖，均不覆盖已 export 的 shell env）+ 加 `doctor` 子命令（§1）
2. paper sizing 与 live tier 解耦：`PAPER_RISK_TIER` / `LIVE_RISK_TIER`，让 paper 按 `per_trade_risk_pct` 跑出有意义仓位（§1）
3. 修 `previous_close=price`（§11）
4. `today_allowlist` 确定性兜底（§11）
5. 删 `candidate_selector` 重复计分（§6）+ scoring 重复读文件（§5）

### P1 — 校准能力 + 选股池分层（两条独立轨道，可并行）
**轨道 A：校准（用数据调参，而非拍脑袋）**
6. 新增 `replay` 子命令：score 桶 vs 未来 1/3/5 日收益、entry-zone 命中率、breakout 成功率、paper 成交率、blocked 原因分布、**component attribution**。**从"凭感觉"到"凭数据"的分水岭。**
   - ✅ **paper broker v2 完成**：滑点（`PAPER_SLIPPAGE_BPS=10`）+ 日终撤 pending（`PAPER_CANCEL_PENDING_AT_DAY_END=1`）`6754d41`
   - ⏳ **replay 子命令 — 待做，阻塞于数据积累**：
     - fill rate + blocked reason distribution（本地可计算，不依赖外部数据，待实现）
     - score bucket vs 1/3/5d forward return（需要 yfinance 历史 + 多个 run date 的 candidate_scores.json；当前只有 1 个 run date，先跑数据再实现）
     - 建议：等积累 2–3 周 paper runs 后再回来实现这块

**轨道 B：active_watchlist（独立、低风险，可与轨道 A 并行）**
8. 建 `active_watchlist.txt`（≤30）+ `universe_meta.json`（先手动从 `universe.txt` 现有 theme 分组 bootstrap，不必一上来搞 ETF holdings 自动构建），**只让重活（Kronos、technical AI、market_feed 4 timeframe）跑 active**；DSA 可扫全 universe 但只输出 top N（§2、§4）。
   - ✅ **轨道 B 完成** `96a5a8f`：
     - `src/config/active_watchlist.txt`（28 个高优先级 symbol）
     - `src/config/universe_meta.json`（88 symbol，tier/theme/liquidity 标注）
     - `universe.py`: `parse_active_watchlist()` + fallback
     - `market_context.py`: 新增 `symbols=` 覆盖参数
     - `premarket.py`: Kronos + market_feed 均按 active_watchlist 运行；DSA 仍扫全 universe.txt
   - **理由更正**：上调它的优先级是为了**降延迟/成本（尤其 Kronos 本地推理）+ 候选来源质量**，**不是**"防止 replay 被大池子污染"——评分漏斗本就已收敛到 `selected[:20]` 打分 / `watchlist[:8]`（`candidates.py:78`、`risk_overlay.py:143-150`），replay 看不到全 88。

### P2 — 策略质量
9. price_setup_score / reward_risk_score 纳入排序（§7）——单点收益最大。**新权重是起点不是结论，必须先用轨道 A 的 component attribution 校准，别用一组魔数换另一组。**

### P3 — 成本与速度（系统能跑，这些是优化不是救火）
10. market_feed 去 rmtree + 批量 + 并发（§3）
11. intraday quote 去全 universe（§11）
12. compact JSON prompt 输入 + subagents 降到 3（§4）

---

## P0 执行清单（含验收标准）

下面 5 项是立即要做的批次，彼此有耦合（env 加载顺序 → tier 取值 → sizing 测试），按序做。每项流程：**先补/写测试 → 改 → `pytest` 全绿 → 用 `doctor` 或 dry-run 验证生效**。

| # | 状态 | 改动 | 主要文件 | commit |
|---|---|---|---|---|
| 1 | ✅ 完成 | env 加载 + `doctor` | `core/config.py`, `cli.py` | `7b5d8d3` |
| 2 | ✅ 完成 | paper/live tier 解耦 | `core/config.py`, `risk_tiers.json`, orchestration | `9d53047`, `f0cc272` |
| 3 | ✅ 完成 | 修 `previous_close=price` | `data/live_quotes.py` | `88a838b` |
| 4 | ✅ 完成 | `today_allowlist` 兜底 | `policy/loaders.py` | `3011bad` |
| 5 | ✅ 完成 | 删重复计分 + scoring 重复读 | `policy/candidate_selector.py`, `planner/scoring.py` | `3b80d72`, `f35b947` |

**验收标准（P0.1-2 完成后）**：`python -m trading_agent doctor` 与 `run_premarket.sh` 打印生效值一致；`TRADING_MODE=paper` 下单笔 notional 由 `PAPER_RISK_TIER`/`per_trade_risk_pct` 决定，不再被 $10 cap 掐死。

---

## 总评（基于真实代码）

- **核心交易引擎**：已成型，price/sizing/sell/paper 链路完整，安全边界（execution_not_wired、KILL_SWITCH、fail-closed）扎实。
- **真实成熟度比外部打分低一点**，因为它没看到配置漂移和脏数据——这些让"paper 结果可信度"打了折。
- **一句话**：别急着加策略或砍 universe。**先把"配置统一 + 数据干净 + 能回看校准"三件事做了**，你才知道现在这套值不值得往 live 推。

---

## 第四部分：决策记录（已吸收的细化与理由）

本审查已整合两轮评审中所有站得住的点。关键决策与理由留档：

1. **env 加载 + paper/live tier 拆分**：采纳 `PAPER_RISK_TIER` / `LIVE_RISK_TIER`，已并入 P0.1–P0.2。
2. **`doctor` 打印生效值**：完整字段表见 §1。
3. **final planner 的护栏是确定性 `normalize_daily_plan_state()` 而非 prompt**；且 normalize 覆盖 `daily_plan.json` 但**不覆盖 `today_allowlist.txt`**，所以 allowlist 兜底（P0.4）必须保留。
4. **paper broker fill 价公式**：买 `min(limit, 现价*(1+slip))` / 卖 `max(limit, 现价*(1-slip))`，叠加在 `_can_fill` 闸门上；当前固定成交在 limit 对买单偏悲观，修后更真实。
5. **active_watchlist 上调到 P1（轨道 B）**：理由是**降本（Kronos 本地推理）+ 候选来源质量**，**不是**"防 replay 污染"——评分漏斗已收敛到 ≤20 打分 / ≤8 watchlist（`candidates.py:78`、`risk_overlay.py:143-150`），replay 看不到全 88。结论（早做）对，理由要对。
6. **别用魔数换魔数**：新排序权重必须先经 replay 的 component attribution 校准再固化（P2），否则只是把"凭感觉"换了个位置。
