# 设计：DSA / Technical 两层 Token 优化实现方案

> 创建：2026-06-15
> 目标：在**不降低（甚至提升）AI 可用信息量**的前提下，大幅降低 DSA 与 Technical 两个 Codex 层的
> token 消耗。核心做法：**确定性测量交给 Python 预计算成紧凑特征文件,AI 只读特征 + 做判断。**
>
> 关键原则:代码负责「测量」,AI 负责「判断」。原始图表/K线数组「又贵又稀」,计算后的指标
> 「又便宜又密」——AI 反而看到更多决策相关信息,却读更少 token。

---

## 0. 必须保持不变的下游契约（红线）

改动只动**输入**(喂给 prompt 的数据),**输出 schema 必须保持一致**,否则打断 scoring/risk_overlay。

**DSA 输出**(`DSA_SIGNALS_PATH`,被 `planner/scoring.py` 与 `contracts/dsa.py` 消费):
- 顶层:`date`/`generated_at`/`source`/`data_status`/`market_phase`/`selected_candidates`/
  `blocked_symbols`/`symbol_signals`/`notes`
- `symbol_signals[SYM]`:至少 `dsa_score`(或 `score`)、`suggested_premarket_use`(或 `action`)、
  `setup`、`strategy_matches`、`bias` —— scoring 读这些

**Technical 输出**(`TECHNICAL_SIGNALS_PATH`,被 `scoring.py`、`reporting/trader_watch_levels.py`、
`contracts/technical.py` 消费):
- 顶层:`symbols` mapping
- 每标的:`technical_action`(映射到 TECHNICAL_ACTION_SCORES)、`key_levels`、`long_setup`、
  `short_setup`、`no_trade_zone`、`confidence`(+ chan/brooks/fundamentals/decision_rationale)

> 这两个 schema 一个字段都不删。我们只是把「AI 自己费力得到的输入」换成「Python 算好的紧凑输入」。

---

## 1. 新增模块 A:`planner/technical_features.py`

**职责**:从已采集的 market_feed OHLCV(active watchlist),为每个标的算指标特征包,写
`signals/technical_features.json`。**纯函数,零网络,完全可单测。**

### 1.1 纯计算函数(无外部 TA 库,用标准库 / 已有 numpy)

```
sma(closes, period) -> float | None
ema(closes, period) -> float | None
rsi(closes, period=14) -> float | None
macd(closes, fast=12, slow=26, signal=9) -> {macd, signal, hist}
atr(highs, lows, closes, period=14) -> float | None
find_swing_points(highs, lows, left=2, right=2) -> {swing_highs:[...], swing_lows:[...]}
pct_return(closes, n) -> float | None
trend_label(close, sma50, sma200) -> "up" | "down" | "sideways"
detect_flags(rows) -> ["inside_bar","gap_up","gap_down","pullback_to_sma20","range_breakout",...]
```

### 1.2 每标的特征包 schema

```jsonc
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601",
  "benchmark": "SPY",
  "recent_bars_count": 30,
  "symbols": {
    "NVDA": {
      "data_quality": "ok|partial",
      "timeframes": {
        "daily": {
          "last_close": 0,
          "sma": {"20": 0, "50": 0, "200": 0},
          "ema": {"9": 0, "21": 0},
          "price_vs_sma": {"20": "above|below", "50": "...", "200": "..."},
          "rsi_14": 0,
          "macd": {"macd": 0, "signal": 0, "hist": 0},
          "atr_14": 0,
          "atr_pct": 0,
          "range_20d": {"high": 0, "low": 0},
          "high_recent": 0, "low_recent": 0,
          "dist_from_recent_high_pct": 0,
          "avg_volume_20": 0, "volume_surge_ratio": 0,
          "swing_highs": [0, 0], "swing_lows": [0, 0],
          "trend": "up|down|sideways",
          "flags": ["pullback_to_sma20"],
          "recent_bars": [
            {"t":"...","o":0,"h":0,"l":0,"c":0,"v":0}  // 仅最近 TECHNICAL_RECENT_BARS 根(日线)
          ]
        },
        "weekly": { /* 同结构,但不含 recent_bars,只含指标 */ },
        "hourly": { /* 指标 only */ },
        "intraday_15m": { /* 指标 only */ }
      },
      "multi_timeframe": {
        "alignment": "bullish|bearish|mixed",
        "rel_strength_vs_spy": {"5d": 0, "20d": 0, "60d": 0}
      }
    }
  }
}
```

设计要点:
- **只有日线带 `recent_bars`**(给缠论/Brooks 读结构),其它周期只给指标 → 控制体积。
- `swing_highs/lows` 就是**支撑/阻力候选**,AI 不必从图上估。
- `rel_strength_vs_spy` 用 SPY 的日线(SPY 在 active watchlist,数据已在)。
- 单标的缺某周期 → 该周期省略,`data_quality="partial"`,不报错。

### 1.3 入口

```
build_technical_features(market_feed_dir, active_symbols, run_date,
                         recent_bars=30, benchmark="SPY") -> dict
```
读 `market_feed_dir/ohlcv/<SYM>/<label>.json`(label: weekly/daily/hourly/intraday_15m)。

---

## 2. 新增模块 B:`signals/dsa_metrics.py`

**职责**:对**全 universe(88)**做一次批量 yfinance 下载(仅日线,~180 天),算横截面指标 +
主题聚合,写 `signals/dsa_metrics.json`。让 DSA prompt 读现成横截面表,**不再自己逐标的抓数据**。

### 2.1 计算

- 一次 `yf.download(tickers=universe, period="6mo", interval="1d", group_by="ticker")`。
- 每标的:`return{1d,5d,20d,60d}`、`rel_strength_vs_spy{5d,20d,60d}`、`above_sma50/200`、
  `trend`、`dist_from_20d_high_pct`、`dist_from_52w_high_pct`(数据够时)、`volume_surge_ratio`、
  `atr_pct`。
- 主题来自 `universe_meta.json`(已确定性,无需 AI 推断)。
- 主题聚合:每个 theme 的 `avg_rel_strength_20d`、`pct_uptrend`、`member_count`、`leaders`(rel
  strength 前 N)。
- 市场广度:`pct_above_sma50`、`pct_above_sma200`、advancers/decliners。

### 2.2 schema

```jsonc
{
  "date": "YYYY-MM-DD", "generated_at": "ISO-8601",
  "benchmark": "SPY",
  "data_status": "ok|partial|failed",
  "market_breadth": {"pct_above_sma50": 0, "pct_above_sma200": 0, "adv_dec_ratio": 0},
  "theme_metrics": {
    "ai_semiconductor": {"avg_rel_strength_20d": 0, "pct_uptrend": 0,
                          "member_count": 13, "leaders": ["NVDA","AVGO"]}
  },
  "symbols": {
    "NVDA": {
      "theme": "ai_semiconductor", "liquidity": 1, "last_close": 0,
      "return": {"1d":0,"5d":0,"20d":0,"60d":0},
      "rel_strength_vs_spy": {"5d":0,"20d":0,"60d":0},
      "trend": "up|down|sideways", "above_sma50": true, "above_sma200": true,
      "dist_from_20d_high_pct": 0, "dist_from_52w_high_pct": 0,
      "volume_surge_ratio": 0, "atr_pct": 0,
      "data_quality": "ok|partial|failed"
    }
  }
}
```

### 2.3 入口

```
build_dsa_metrics(universe_file, meta_file, run_date,
                  lookback_days=180, benchmark="SPY",
                  mock=False, downloader=<injectable>) -> dict
```
`downloader` 可注入 → 测试用 mock,不联网。

---

## 3. 集成进 premarket 流水线（`orchestration/premarket.py`）

当前顺序:account → capital → collect_context(active) → **并行组[dsa,kronos,technical,calendar,
core_quotes]** → trader_watch_levels → ...

改动:把两个预计算放在**对应 prompt 之前**,保持并行结构。

- `run_dsa()`:先 `build_dsa_metrics(...)` 写 `dsa_metrics.json`(它自带全 universe 下载,
  在并行组里与 kronos/technical 同时跑),再跑 DSA prompt。失败 → 写 fail-closed metrics 并继续
  (prompt 端读不到就标 partial)。
- `run_technical()`:在现有 manifest 检查后,`build_technical_features(...)` 写
  `technical_features.json`(纯计算,无网络),再跑 technical prompt。

flag 控制(默认开,可回退旧行为):
- `ENABLE_TECHNICAL_FEATURES_PRECOMPUTE=1`
- `ENABLE_DSA_METRICS_PRECOMPUTE=1`

---

## 4. 路径与 runtime block

`core/context.py` 的 `RuntimePaths` 增:
- `technical_features_path = signals/technical_features.json`
- `dsa_metrics_path = signals/dsa_metrics.json`

`prompts/runtime_block.py` 增注入(prompt 用占位符引用):
- `TECHNICAL_FEATURES_PATH`
- `DSA_METRICS_PATH`

新增 env(写入 `runtime.env` + doctor 回显):
- `TECHNICAL_RECENT_BARS=30`
- `DSA_METRICS_LOOKBACK_DAYS=180`
- 两个 `ENABLE_*_PRECOMPUTE`

---

## 5. Prompt 重写

### 5.1 `technical/research.txt`

**删**:
- `read MARKET_FEED_DIR/charts/`(图表不再喂模型 —— 最大单项节省)
- `read MARKET_FEED_DIR/ohlcv/`(原始全量 K 线数组)

**改为**:
- `read TECHNICAL_FEATURES_PATH`:已含 SMA/EMA/RSI/MACD/ATR、支撑阻力(swing)、相对强度、
  多周期一致性,以及日线最近 N 根 `recent_bars`。
- 明确指示:「这些指标已算好,**不要重算**,直接引用;用 `recent_bars` 读缠论/Brooks 结构」。
- 保留:skills 框架读取、news 读取、**完整输出 schema**。

### 5.2 `signals/dsa_scan.txt`

**删**:
- 「自己为 universe.txt 全部 88 个抓 quote/news/historical」的逐标的取数。

**改为**:
- `read DSA_METRICS_PATH`:全 universe 横截面表(相对强度/趋势/收益/放量/主题/广度)。
- DSA 只做**判断**:promote/demote/block、crowding、macro_sensitivity、theme 取舍。
- 催化剂保持「轻」:只对**即将 promote 的少数**标的用 web 查催化可信度(而非全 88),省 token。
- 保留:hard-block 规则、**完整输出 schema**、subagent 段(现在可降到很少甚至单次,因为不再逐标的取数)。

---

## 6. 测试

- `tests/.../planner/test_technical_features.py`:
  - 指标数学:已知序列 → 已知 SMA/EMA/RSI/MACD/ATR 值
  - swing 检测:构造高低点序列验证 pivots
  - 全量:fixture OHLCV 目录 → 校验 schema、recent_bars 截断、partial 处理
- `tests/.../signals/test_dsa_metrics.py`:
  - 注入 mock downloader → 校验 return/rel_strength/trend/主题聚合/广度
  - 缺标的/缺数据 → partial/failed 标记
- 回归:scoring 在新 technical/dsa 输出 schema 下仍正常(已有测试覆盖契约)。

---

## 7. 预期 token 影响（粗估，28 active / 88 universe）

| 项 | 现在 | 改后 | 说明 |
|---|---|---|---|
| Technical 图表 | 112 张 PNG(视觉 token,最贵) | 0 | 图表仍生成供人看,不喂模型 |
| Technical OHLCV | 112 个全量 K 线数组 | 紧凑特征包 + 仅日线最近 30 根 | ~10–20× 文本缩减 |
| DSA 取数 | 88× 工具往返(quote/news/hist) | 读 1 张预算表 | 去掉绝大部分往返 |
| DSA 催化剂 | 潜在全 88 查新闻 | 仅 promote 候选少数 | 大降 |

净效果:两层 token 大幅下降,**且 AI 拿到的决策信息更多更一致**(精确指标 + 横截面对比)。

---

## 8. 实施顺序（建议）

1. `planner/technical_features.py` + 测试(纯函数,先让你看特征包长相)。
2. 接 `run_technical()` + 路径 + runtime block + 改 `technical/research.txt`。
3. `signals/dsa_metrics.py` + 测试(注入 mock downloader)。
4. 接 `run_dsa()` + 路径 + runtime block + 改 `signals/dsa_scan.txt`。
5. env flag + doctor 回显 + README/项目文档更新。
6. 每步 `pytest` 全绿 → commit + push。

每一步都可独立回退(flag 关闭即走旧行为),互不阻塞。
