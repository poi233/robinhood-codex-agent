# 每日策略优化操作手册（Daily Strategy Playbook）

> 配套 [`roadmap.md`](./roadmap.md) 的「🎯 当前焦点」。这份文档回答一个问题：**为了让投资策略真正变强，
> 我每天 / 每周 / 每月该做点什么。**
>
> 一句话原则：**你的策略变强，不靠多几个 AI 分析器，而靠知道——哪个信号真有用、哪个 setup 真能赚、
> 哪些 blocked reason 是保护、哪些规则让你错过机会、challenger 是否真优于 baseline。**

---

## Step 0（只做一次）：写下你的策略假设 + 不交易规则

把策略写成**一句话**，之后所有改动都用来验证或证伪它：

> **Baseline thesis（草稿，按需改）**：在 AI / 半导体 / 基础设施等强主题中，选择**多信号确认**、价格
> 接近**可执行 setup**（pullback / breakout）、**风险收益比合格**的**高流动性**股票，用**低频 limit
> order** 交易，严格控制**主题集中度**与**单笔风险**。

然后写下**不交易规则**（比买入规则更重要，系统大部分已实现，后面只校准松紧）：
- 市场 risk-off → 不开新仓（只允许防守/卖出）
- 数据不完整 / quote 不新鲜 → 不买
- 价格追高（超过 do-not-chase）→ 不买
- 风险收益比不够（< `min_reward_risk`）→ 不买
- 主题过度集中（超 theme cap）→ 不买
- 已有 losing position → 不加仓（no average-down）

> 建议把上面两段固化到 `src/config/strategy.md`（已有该文件）。每次实验前回看：这个改动是在验证 thesis
> 的哪一条？

---

## 每天的固定动作（交易日）

**目标是积累数据、发现问题，不是调参。** 整套有 shell wrapper 自动跑（cron/launchd），手动等价命令：

```bash
# 1. 盘前（约 05:30 PT）
python3 -m trading_agent premarket

# 2. 盘中（06:45–12:45 PT，每 ~30 分钟一次）
python3 -m trading_agent intraday

# 3. 盘后（约 13:10 PT）
python3 -m trading_agent postmarket

# 4. 盘后复盘（只读，不改配置）
python3 -m trading_agent analytics build
python3 -m trading_agent replay
python3 -m trading_agent dashboard          # 浏览器看 localhost:8501

# 5. 让自成长「观察」——只看它发现什么，不要 approve
python3 -m trading_agent growth observe
```

**盘后花 5–10 分钟在 dashboard 上看这几样（按 Tab）**：
- **Today**：今天交易/没交易？原因合理吗（blocked_reasons）？
- **Decisions**：no-trade rate 高不高？哪个 blocked reason 最多（是保护还是错过）？
- **Paper**：权益曲线、当日 realized PnL、fill rate。
- **Self-Growth**：`growth observe` 报了什么（低交易频率 / blocked 过度集中 / pending cancel 率高 /
  theme 过度集中 / 缺 manifest）。
- **Themes**：主题集中度有没有超 cap。

**每天只记录、不调权重/阈值。** 一两天的表现不能说明任何问题。

---

## 每周的动作

1. **看趋势**（dashboard 跨日视图）：no-trade rate、fill rate、blocked reason 分布有没有系统性问题。
2. **让自成长提议，但先不 approve**：
   ```bash
   python3 -m trading_agent growth propose
   python3 -m trading_agent growth validate runtime/strategy_proposals/<date>/
   ```
   只判断 proposal 合不合理（它只会动白名单参数：threshold / 权重 / enabled setup / watchlist / entry
   zone）。**积累够 10+ 交易日之前不要进 active_shadow。**
3. **每周跑一次校准报告**（E1 已上线，需联网 yfinance），重点看 dashboard 的 **Calibration Tab**：
   ```bash
   python3 -m trading_agent analytics calibrate
   ```
   看：哪个分数桶最有效（桶单调吗）、哪个分量 IC 最高、哪个 setup 最容易成交/最赚、benchmark 对照。
   **注意**：样本 < 15 个 run date 时数字噪声很大，别据此调权重——E1 报告头部也会提醒。
4. **每周选股进货（O1 screener）**：周日盘后 cron 自动跑 `screen`（Serenity 卡点法发现池外票 + 因子严门槛
   验证）。默认只产报告——先人工看 `runtime/screener/<date>/universe_change.md`（加了谁/为什么/因子分/谁被降级）。
   想让它**自动改 universe（只增不删 + 重排，无需确认）**就在 `runtime.env.local` 设 `ENABLE_WEEKLY_SCREENER=1`。
   ```bash
   python3 -m trading_agent screen            # 跟随 flag（默认只报告）
   python3 -m trading_agent screen --apply    # 强制自动写 universe（手动试一次时用）
   python3 -m trading_agent screen --dry-run  # 强制只报告
   ```
   只动选股层（universe / 排名 / tier），绝不碰仓位/风险；新票仍要过每天的打分→risk_overlay→价格/仓位 gate
   才会被真正交易。

---

## 每月的动作

- **更新 active watchlist（不要每天乱变）**：根据主题强弱 + 流动性，调整 `active_watchlist.txt`；同步
  补 `universe_meta.json` 的 `theme` / `layer` / `risk_tags`。
- **决定要不要开实验**：只有当 E1 数据**明确指出**某个杠杆（如「technical IC 高、kronos 几乎为 0」）时，
  才创建**单变量** challenger 版本（见下方 Phase 4）。
- **回看纪律**：这个月有没有忍不住手动调过权重？（不应该。）

---

## 分阶段计划（与 roadmap 优先级对应）

| 阶段 | 做什么 | 何时进入下一阶段 |
|---|---|---|
| **Phase 1 · 积累（现在）** | 每天跑 paper，冻结 baseline_v1，自成长只 observe/propose | 攒满 10–15（最好 20–30）交易日 |
| **Phase 2 · 建 E1 校准（与 Phase 1 并行，现在就开始）** | 实现 forward/benchmark returns + attribution + setup outcomes + Calibration Tab（roadmap E1） | E1 机器跑通、报告可读 |
| **Phase 3 · 补 shadow 账本 + near-miss** | G9（challenger 隔离 paper 账本）+ E3（near-miss） | challenger 有真实 fill/drawdown/PnL；near-miss 有后续收益分布 |
| **Phase 4 · 策略版本化实验** | 用 E1 结论建**单变量** challenger，shadow 跑，dashboard 对比 | 有 ≥1 个 challenger 跑满 10 shadow 日且指标不劣于 champion |
| **Phase 5 · 数据 promote + E2 权重重校准** | 人工 `growth promote check` → 手改 registry；E2 用 IC 重分配权重登记新版本 | 持续迭代 |

> **关键修正**：Phase 2（建 E1）**不要等** Phase 1 攒满数据再开始。E1 的 forward returns 是用 yfinance
> 重算的、输入都已落盘，所以现在就能建——每积累一天立刻可消费，还能尽早抓数据管道 bug。

---

## 五个策略模块 · 每个看什么指标

策略可拆成 5 层，每层有自己的指标和改进方向（改进**只能靠数据**，不靠拍脑袋）：

1. **市场环境层（什么时候该交易）**：看 SPY/QQQ/SMH/IWM 趋势、breadth、pct above SMA50/200、波动率、
   主题强度 → 校准 risk-off/normal/risk-on/aggressive 的判定。系统已有 market regime + theme diagnostics，
   缺数据校准。
2. **选股层（看哪些股票）**：稳定维护 universe / active watchlist / candidates / tradable。下一步：watchlist
   按周/月更新（B5 resolver）、universe_meta 补 theme/layer/risk_tags、speculative bucket 单独限。
3. **信号层（哪个分析真有用）**：当前权重（DSA .25 / technical .30 / kronos .15 / quote .10 / catalyst
   .20）是**先验**。**等 E1 attribution**，按 IC 重分配（E2），不要手调。
4. **Setup 层（什么时候买）**：已有 pullback / breakout / entry zone / no-trade zone / do-not-chase /
   R:R / price_setup_score。校准：各 setup 胜率、entry-zone 命中率、target_1 先于 stop 的比例、
   outside_entry_zone 后是否错过、do_not_chase 是否真保护。
5. **风控/退出层（怎么活下来）**：已有 risk-budget sizing / cash buffer / caps / theme cap / cooldown /
   sell-first / partial TP / 部分成交模型。校准：止损是否太紧、target_1 是否太近、partial TP 是否过早、
   cooldown / max_new_positions 是否合理。

---

## 实验纪律（红线）

- **冻结 baseline**：积累期不动 champion 的任何权重/阈值，否则数据不可比。
- **一次只做一个实验**：A) price_setup 0.15→0.25；B) breakout 关闭；C) kronos 0.15→0.05；D) threshold
  50→55——**分开做**，否则不知道哪个有效。
- **只用数据 promote**，建议门槛：≥10 shadow 日 · ≥5 次有效 would_trade · fill rate 不低于 champion ·
  max drawdown 不差于 champion · forward-return 桶不差于 champion · blocked reason 更健康 · 无 safety
  violation · **人工 approve**。
- **自成长只能改筛选，不能改仓位/风险**：允许动 score weights / thresholds / enabled setup / watchlist /
  theme caps / entry zone。**永远禁止**（validator 已硬编码红线）：`per_trade_risk_pct` /
  `max_daily_risk_pct` / `RISK_TIER` / `PAPER_RISK_TIER` / position cap / `KILL_SWITCH` /
  `place_equity_order` / `TRADING_MODE`。
- **forward returns + shadow equity 没做完之前，不 promote 任何东西**（G7 也会自动拒绝）。

---

## promote 前检查清单（将来用）

```bash
python3 -m trading_agent growth recommend            # 看 evaluator 裁决
python3 -m trading_agent growth promote check <id>   # 生成 changelog + registry 草稿（不改 registry）
```

- [ ] challenger 跑满 ≥10 shadow 日
- [ ] fill rate / max drawdown / forward-return 桶都不劣于 champion
- [ ] blocked reason 分布更健康（不是靠少交易刷出来的）
- [ ] 无 safety violation
- [ ] 我**手动**改 `strategy_registry.yaml` 的 `active_strategy` + 写 `strategy-changelog.md`

> 系统**从不**自动 promote。最终切换永远是你手改 YAML。

---

## 一句话结论

下一步不是继续堆 agent，而是：**每天稳定跑 paper（冻结 baseline），并行把 E1 校准建起来**。把"AI 觉得
好"升级成"历史数据支持哪个分量、哪个 setup 真有用"——这才是策略真正变强的方向。
