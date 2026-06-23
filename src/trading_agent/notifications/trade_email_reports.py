from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from trading_agent.core.context import build_runtime_paths
from trading_agent.policy.models import PolicyDecision


def _read_json_or(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _money(value: Any) -> str:
    try:
        return f"${float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _number(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "0"
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.4f}".rstrip("0").rstrip(".")


def _join_or_none(values: list[Any] | tuple[Any, ...] | set[Any] | None) -> str:
    cleaned = [str(value) for value in values or [] if str(value).strip()]
    return "、".join(cleaned) if cleaned else "无"


def _section(title: str) -> list[str]:
    return ["", f"【{title}】"]


def _bullet(label: str, value: Any) -> str:
    return f"{label}：{value}"


def _clip_text(value: Any, *, limit: int = 96) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _compact_path(path: Path) -> str:
    parts = path.parts
    try:
        runtime_index = parts.index("runtime")
    except ValueError:
        return str(path)
    return "/".join(parts[runtime_index:])


def _status_zh(status: Any) -> str:
    return {
        "completed": "完成",
        "failed": "失败",
        "skipped": "跳过",
        "started": "开始",
    }.get(str(status), str(status or "未知"))


_LAYER_ZH = {
    "technical": "技术面",
    "dsa": "DSA动量",
    "catalyst": "催化",
    "kronos": "Kronos预测",
    "quote": "盘前报价",
    "factor_alpha": "量价因子",
    "ai": "AI信号",
}
_ACTION_TAKEN_ZH = {
    "paper_fill": "模拟成交",
    "paper_pending": "模拟挂单待成交",
    "live_order_submitted": "实盘下单已提交",
    "review_submitted": "审阅单已提交",
    "execute_failed": "执行失败",
    "none": "无操作",
}
_SETUP_ZH = {"breakout": "突破", "pullback": "回踩", "risk_reduction": "风险减仓", "none": "无", "": "无"}
_REGIME_ZH = {
    "aggressive_ok": "可积极",
    "normal": "正常",
    "observe_only": "仅观察",
    "risk_off": "避险",
    "no_trade": "暂停交易",
    "panic": "恐慌",
    "bull": "牛市",
    "neutral": "中性",
    "bearish": "偏空",
    "bullish": "偏多",
}
_PLAN_STATE_ZH = {"trade_ready": "可交易", "watch_only": "仅观察", "no_trade": "暂停交易", "fail_closed": "故障关闭"}
_DIRECTION_ZH = {
    "long": "看多", "bullish": "看多", "positive": "看多", "buy": "看多",
    "short": "看空", "bearish": "看空", "negative": "看空", "sell": "看空",
    "neutral": "中性", "none": "无",
}
_ACTION_ZH = {
    "strong_promote": "强力看多", "promote": "看多", "buy_bias": "偏多",
    "observe": "观察", "hold": "持有", "neutral": "中性",
    "reduce": "减仓", "sell_bias": "偏空", "avoid": "回避", "block": "阻断",
}
_ALLOWED_ACTION_ZH = {
    "small_limit_buy": "小额限价买入",
    "partial_take_profit": "分批止盈",
    "risk_exit": "风险减仓",
    "full_invalidation_exit": "失效退出",
    "hold": "持有",
    "no_new_buys": "暂停新买入",
}
_QUALITY_FLAG_ZH = {
    "unprofitable": "不盈利", "negative_roe": "ROE为负", "revenue_declining": "营收下滑",
    "high_leverage": "高杠杆", "weak_liquidity": "流动性弱",
}
_EVENT_FLAG_ZH = {
    "earnings_imminent": "临近财报", "analyst_bullish": "分析师看多", "analyst_bearish": "分析师看空",
    "estimate_revised_up": "预期上修", "estimate_revised_down": "预期下修",
}


def _zh(mapping: dict[str, str], key: Any, default: Any = None) -> str:
    raw = str(key or "").strip().lower()
    return mapping.get(raw, str(key) if (default is None and key) else (default or "未知"))


def _stage_summary_lines(agent_root: Path, run_date: str) -> list[str]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    rows = [row for row in _read_jsonl(paths.run_logs_dir / "pipeline" / "pipeline.jsonl") if row.get("status") != "started"]
    if not rows:
        return ["未找到模块运行日志。"]

    status_counts: dict[str, int] = {}
    slowest: list[tuple[float, str, str]] = []
    exceptions: list[str] = []
    for row in rows:
        stage = str(row.get("stage") or "unknown")
        raw_status = str(row.get("status") or "unknown")
        status = _status_zh(raw_status)
        status_counts[status] = status_counts.get(status, 0) + 1
        elapsed = row.get("elapsed_seconds")
        elapsed_seconds: float | None = None
        if elapsed is not None:
            try:
                elapsed_seconds = float(elapsed)
            except (TypeError, ValueError):
                elapsed_seconds = None
        if elapsed_seconds is not None:
            slowest.append((elapsed_seconds, stage, status))
        if raw_status in {"failed", "skipped"}:
            message = str(row.get("message") or "").strip()
            detail = _clip_text(message, limit=48)
            exceptions.append(f"{stage}：{status}" + (f"（{detail}）" if detail else ""))

    total = len(rows)
    ordered_status = "、".join(f"{status} {count}" for status, count in status_counts.items())
    lines = [f"模块数：{total}；{ordered_status}。"]
    if exceptions:
        lines.append("异常/跳过：" + "；".join(exceptions[:5]) + ("；…" if len(exceptions) > 5 else ""))
    else:
        lines.append("异常/跳过：无。")
    top_slowest = sorted(slowest, reverse=True)[:5]
    if top_slowest:
        lines.append("最耗时：" + "；".join(f"{stage} {elapsed:.1f}s" for elapsed, stage, _status in top_slowest) + "。")
    return lines


def _news_lines(agent_root: Path, run_date: str, symbols: list[str]) -> list[str]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    lines: list[str] = []
    shown = 0
    for symbol in symbols:
        if shown >= 8:
            break
        payload = _read_json_or(paths.market_feed_dir / "news" / f"{symbol}.json", {})
        headlines = payload.get("headlines") if isinstance(payload, dict) else None
        if not isinstance(headlines, list):
            continue
        for item in headlines[:2]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            source = str(item.get("source") or "").strip()
            if not title:
                continue
            source_text = f"（{source}）" if source else ""
            lines.append(f"{symbol}：{_clip_text(title)}{source_text}")
            shown += 1
            if shown >= 8:
                break
    return lines or ["未找到可用消息面摘要；以本地行情、候选评分和风控文件为准。"]


def _ai_layer_by_symbol(ai_signals: dict[str, Any], symbol: str) -> list[str]:
    """Per-symbol AI-signal directions across the canonical envelope lists."""
    out: list[str] = []
    layers = ai_signals.get("layers") if isinstance(ai_signals, dict) else {}
    if not isinstance(layers, dict):
        return out
    for layer_name, envelopes in layers.items():
        if not isinstance(envelopes, list):
            continue
        for env in envelopes:
            if isinstance(env, dict) and str(env.get("symbol") or "").upper() == symbol:
                direction = _zh(_DIRECTION_ZH, env.get("direction"), "中性")
                conf = env.get("confidence")
                conf_text = f"{float(conf):.2f}" if isinstance(conf, (int, float)) else "—"
                out.append(f"{_zh(_LAYER_ZH, layer_name, layer_name)} {direction}({conf_text})")
                break
    return out


def _candidate_lines(agent_root: Path, run_date: str) -> list[str]:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    daily_plan = _read_json_or(paths.daily_plan_path, {})
    candidate_scores = _read_json_or(paths.candidate_scores_path, {})
    risk_overlay = _read_json_or(paths.risk_overlay_path, {})
    catalyst = _read_json_or(paths.catalyst_snapshot_path, {})
    watch = _read_json_or(paths.trader_watch_levels_path, {})
    factor_alpha = _read_json_or(paths.factor_alpha_path, {})
    ai_signals = _read_json_or(paths.ai_signals_path, {})
    fundamental = _read_json_or(paths.signals_dir / "fundamental_snapshot.json", {})
    event = _read_json_or(paths.planner_dir / "event_snapshot.json", {})
    tradable = []
    if isinstance(risk_overlay, dict):
        tradable = list(risk_overlay.get("tradable_candidates") or [])
    if not tradable and isinstance(daily_plan, dict):
        tradable = list(daily_plan.get("tradable_candidates") or [])
    if not tradable:
        return ["今天没有满足买入条件的股票；盘中继续按计划观察。"]

    score_symbols = candidate_scores.get("symbols") if isinstance(candidate_scores, dict) else {}
    rules = risk_overlay.get("symbol_trade_rules") if isinstance(risk_overlay, dict) else {}
    catalyst_symbols = catalyst.get("symbols") if isinstance(catalyst, dict) else {}
    watch_symbols = watch.get("symbols") if isinstance(watch, dict) else {}
    factor_symbols = factor_alpha.get("symbols") if isinstance(factor_alpha, dict) else {}
    fundamental_symbols = fundamental.get("symbols") if isinstance(fundamental, dict) else {}
    event_symbols = event.get("symbols") if isinstance(event, dict) else {}
    lines: list[str] = []
    for raw_symbol in tradable:
        symbol = str(raw_symbol).upper()
        score_payload = (score_symbols or {}).get(symbol) or {}
        rule = (rules or {}).get(symbol) or {}
        catalyst_payload = (catalyst_symbols or {}).get(symbol) or {}
        wl = (watch_symbols or {}).get(symbol) or {}
        total_score = score_payload.get("total_score", score_payload.get("score", "未评分")) if isinstance(score_payload, dict) else "未评分"
        components = score_payload.get("components") if isinstance(score_payload, dict) else {}
        component_text = []
        if isinstance(components, dict) and components:
            for key in ("technical", "dsa", "catalyst", "kronos", "quote"):
                if key in components:
                    component_text.append(f"{_zh(_LAYER_ZH, key, key)} {components[key]}")
        max_notional = rule.get("max_notional") if isinstance(rule, dict) else None
        catalysts = catalyst_payload.get("catalysts") if isinstance(catalyst_payload, dict) else []
        risks = catalyst_payload.get("risk_flags") if isinstance(catalyst_payload, dict) else []

        lines.append(f"{symbol}：总分 {total_score}" + (f"，单笔上限 {_money(max_notional)}" if max_notional is not None else ""))
        if component_text:
            lines.append(f"  分项：{_join_or_none(component_text)}")
        # 技术面计划价位（来自确定性引擎 → trader_watch_levels）
        if isinstance(wl, dict) and wl:
            context = _zh(_ACTION_ZH, wl.get("current_context"), "观察")
            entry_low, entry_high = wl.get("entry_low"), wl.get("entry_high")
            entry_text = f"{_money(entry_low)}–{_money(entry_high)}" if entry_low is not None and entry_high is not None else "—"
            tech_bits = [
                f"动作 {context}",
                f"入场 {entry_text}",
                f"突破上破 {_money(wl.get('buy_trigger_above'))}",
                f"止损 {_money(wl.get('invalidation_below'))}",
                f"目标 {_money(wl.get('target_1'))}/{_money(wl.get('target_2'))}",
            ]
            lines.append("  技术：" + " ｜ ".join(tech_bits))
        # advisory 层：量价因子 / AI / 基本面 / 事件
        adv_bits: list[str] = []
        fa = (factor_symbols or {}).get(symbol) or {}
        if isinstance(fa, dict) and fa.get("factor_alpha_score") is not None:
            adv_bits.append(f"量价因子 {fa.get('factor_alpha_score')}")
        adv_bits.extend(_ai_layer_by_symbol(ai_signals if isinstance(ai_signals, dict) else {}, symbol))
        fund = (fundamental_symbols or {}).get(symbol) or {}
        if isinstance(fund, dict):
            qflags = fund.get("quality_flags") or []
            adv_bits.append("基本面 " + ("、".join(_QUALITY_FLAG_ZH.get(f, f) for f in qflags) if qflags else "合格"))
        ev = (event_symbols or {}).get(symbol) or {}
        if isinstance(ev, dict) and ev.get("event_flags"):
            adv_bits.append("事件 " + "、".join(_EVENT_FLAG_ZH.get(f, f) for f in ev.get("event_flags")))
        if adv_bits:
            lines.append("  辅助：" + " ｜ ".join(adv_bits))
        lines.append(f"  催化：{_clip_text(_join_or_none(catalysts), limit=120)}")
        lines.append(f"  风险：{_clip_text(_join_or_none(risks), limit=120)}")
    return lines


def build_premarket_email_body(agent_root: Path, *, run_date: str | None = None) -> str:
    paths = build_runtime_paths(agent_root, run_date=run_date)
    daily_plan = _read_json_or(paths.daily_plan_path, {})
    risk_overlay = _read_json_or(paths.risk_overlay_path, {})
    watchlist = []
    if isinstance(daily_plan, dict):
        watchlist = list(daily_plan.get("today_watchlist") or [])
    if not watchlist and isinstance(risk_overlay, dict):
        watchlist = list(risk_overlay.get("today_watchlist") or [])
    symbols = [str(symbol).upper() for symbol in watchlist]
    if isinstance(risk_overlay, dict):
        symbols.extend(str(symbol).upper() for symbol in risk_overlay.get("tradable_candidates") or [])
    symbols = list(dict.fromkeys(symbols))
    allowed_actions = daily_plan.get("allowed_actions") if isinstance(daily_plan, dict) else []
    lines = [
        "【盘前计划通知】",
        _bullet("日期", paths.run_date),
        _bullet("计划状态", _zh(_PLAN_STATE_ZH, daily_plan.get("plan_state")) if isinstance(daily_plan, dict) else "未知"),
        _bullet("市场状态", _zh(_REGIME_ZH, daily_plan.get("market_regime")) if isinstance(daily_plan, dict) else "未知"),
        _bullet("可执行动作", _join_or_none([_zh(_ALLOWED_ACTION_ZH, a) for a in allowed_actions] if isinstance(allowed_actions, list) else [])),
        _bullet("今日关注", _join_or_none(symbols)),
        *_section("消息面重点"),
        *_news_lines(agent_root, paths.run_date, symbols),
        *_section("可买股票重点"),
        *_candidate_lines(agent_root, paths.run_date),
        *_section("模块运行总结"),
        *_stage_summary_lines(agent_root, paths.run_date),
        *_section("本地记录"),
        f"盘前计划：{_compact_path(paths.daily_plan_path)}",
        f"中文计划：{_compact_path(paths.daily_plan_zh_markdown_path)}",
        f"风控覆盖：{_compact_path(paths.risk_overlay_path)}",
        f"候选评分：{_compact_path(paths.candidate_scores_path)}",
    ]
    return "\n".join(lines) + "\n"


def build_postmarket_email_body(summary: Mapping[str, object]) -> str:
    positions = summary.get("open_position_details")
    position_lines: list[str] = []
    if isinstance(positions, list):
        for item in positions:
            if not isinstance(item, Mapping):
                continue
            symbol = str(item.get("symbol") or "").upper()
            if not symbol:
                continue
            position_lines.append(
                f"{symbol}：数量 {_number(item.get('quantity'))}，成本 {_money(item.get('average_cost'))}，"
                f"现价 {_money(item.get('market_price'))}，市值 {_money(item.get('market_value'))}，"
                f"未实现盈亏 {_money(item.get('unrealized_pnl'))}（{float(item.get('unrealized_return_pct') or 0):.2f}%）"
            )
    if not position_lines:
        position_lines = ["当前没有持仓。"]
    lines = [
        "【盘后复盘通知】",
        _bullet("日期", summary.get("date", "")),
        _bullet("交易模式", {"paper": "模拟盘", "review": "审阅", "live": "实盘"}.get(str(summary.get("trading_mode") or "paper"), str(summary.get("trading_mode") or "paper"))),
        _bullet("期初总权益", _money(summary.get("starting_total_equity"))),
        _bullet("期末总权益", _money(summary.get("ending_total_equity"))),
        _bullet("总权益变化", _money(summary.get("total_equity_change"))),
        _bullet("已实现盈亏", _money(summary.get("realized_pnl"))),
        *_section("当前持仓分析"),
        *position_lines,
        *_section("今日回顾"),
        f"总权益变化 {_money(summary.get('total_equity_change'))}，已实现盈亏 {_money(summary.get('realized_pnl'))}。",
        f"订单数 {int(summary.get('order_count', 0) or 0)}，成交 {int(summary.get('filled_order_count', 0) or 0)}，成交名义金额 {_money(summary.get('filled_notional'))}。",
        f"收盘持仓数量 {int(summary.get('open_position_count', 0) or 0)}，明天盘前继续按风险层级和候选评分更新计划。",
        *_section("账户与执行"),
        _bullet("现金变化", _money(summary.get("cash_change"))),
        _bullet("持仓市值", _money(summary.get("positions_market_value"))),
        _bullet("拒绝或取消订单数", int(summary.get("rejected_or_canceled_order_count", 0) or 0)),
    ]
    return "\n".join(lines) + "\n"


_REASON_ZH = {
    "candidate_ranked": "候选排名通过",
    "hard_blocks_cleared": "硬性交易阻断已排除",
    "entry_zone_ok": "价格位于计划入场区间",
    "breakout_trigger_ok": "突破触发条件通过",
    "no_chase_ok": "未追高",
    "reward_risk_ok": "盈亏比通过",
    "risk_sizing_ok": "仓位和风控额度通过",
    "theme_weight_ok": "主题权重限制通过",
    "partial_take_profit": "分批止盈条件触发",
    "risk_exit": "风险退出条件触发",
    "full_invalidation_exit": "完整失效退出条件触发",
    "catastrophic_stop": "灾难止损触发",
}


def build_intraday_trade_email_body(decision: PolicyDecision) -> str:
    intent = decision.intent
    if intent is None:
        return "【盘中成交通知】\n\n【本次操作】\n本次没有可记录订单。\n"
    side_zh = "买入" if intent.side == "buy" else "卖出"
    mode_zh = {"paper": "模拟盘", "review": "审阅", "live": "实盘"}.get(decision.trading_mode, decision.trading_mode)
    reason_text = "、".join(_REASON_ZH.get(code, "其他策略条件通过") for code in intent.reason_codes)
    if not reason_text:
        reason_text = "策略触发条件通过"
    confidence_pct = f"{float(intent.confidence or 0) * 100:.0f}%"
    lines = [
        "【盘中成交通知】",
        *_section("本次操作"),
        f"{mode_zh}已{side_zh} {intent.symbol}，数量 {_number(intent.quantity)}，限价 {_money(intent.limit_price)}，名义金额 {_money(intent.estimated_notional)}。",
        f"执行动作：{_zh(_ACTION_TAKEN_ZH, decision.action_taken)}；交易模式：{mode_zh}。",
        *_section("买入原因" if intent.side == "buy" else "操作原因"),
        f"{reason_text}。",
        f"策略形态：{_zh(_SETUP_ZH, intent.setup_type, '未记录')}；置信度：{confidence_pct}。",
        *_section("风险与价格"),
        f"参考价格：{_money(intent.reference_price)}；限价：{_money(intent.limit_price)}；止损 {_money(intent.stop_price)}。",
        f"目标一：{_money(intent.target_1)}；目标二：{_money(intent.target_2)}；预估盈亏比：{_number(intent.reward_risk)}。",
    ]
    overlay_lines = _intraday_overlay_lines(intent.advisory_overlay)
    if overlay_lines:
        lines.extend([*_section("辅助信号叠加（advisory overlay）"), *overlay_lines])
    lines.extend([
        *_section("本地记录"),
        "订单、账户和持仓以本地 paper 账本与 intraday 决策日志为准。",
    ])
    return "\n".join(lines) + "\n"


def _intraday_overlay_lines(overlay: dict[str, object]) -> list[str]:
    if not overlay:
        return []
    components = overlay.get("components") if isinstance(overlay.get("components"), dict) else {}
    factor = components.get("factor_alpha") if isinstance(components.get("factor_alpha"), dict) else {}
    ai = components.get("ai") if isinstance(components.get("ai"), dict) else {}
    regime = components.get("regime") if isinstance(components.get("regime"), dict) else {}
    portfolio = components.get("portfolio") if isinstance(components.get("portfolio"), dict) else {}
    fundamental = components.get("fundamental") if isinstance(components.get("fundamental"), dict) else {}
    event = components.get("event") if isinstance(components.get("event"), dict) else {}
    lines = [
        f"排序调整：{float(overlay.get('rank_delta') or 0):+.2f}；仓位乘数：{float(overlay.get('size_multiplier') or 1):.2f}。"
    ]
    if overlay.get("block_buy"):
        reasons = "、".join(str(reason) for reason in (overlay.get("blocked_reasons") or []))
        lines.append(f"买入阻断：{reasons or '未记录原因'}。")
    if factor.get("score") is not None:
        lines.append(f"量价因子：{factor.get('score')}。")
    for layer, payload in ai.items():
        if not isinstance(payload, dict):
            continue
        conf = payload.get("confidence")
        conf_text = f"{float(conf):.2f}" if isinstance(conf, (int, float)) else "—"
        lines.append(f"AI·{_zh(_LAYER_ZH, layer, layer)}：{_zh(_DIRECTION_ZH, payload.get('direction'), '中性')}（置信度 {conf_text}）。")
    if regime.get("regime"):
        lines.append(f"市场状态：{_zh(_REGIME_ZH, regime.get('regime'))}；仓位乘数={regime.get('applied_multiplier')}。")
    if portfolio.get("position_weight") is not None:
        lines.append(f"组合：当前权重={portfolio.get('position_weight')}" + ("（主题超配）" if portfolio.get("overexposed_theme") else "") + "。")
    if fundamental.get("quality_flags"):
        lines.append(f"基本面：{'、'.join(_QUALITY_FLAG_ZH.get(f, f) for f in fundamental.get('quality_flags'))}。")
    if event.get("event_flags"):
        lines.append(f"事件：{'、'.join(_EVENT_FLAG_ZH.get(f, f) for f in event.get('event_flags'))}。")
    return lines
