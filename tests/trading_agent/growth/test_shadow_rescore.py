from __future__ import annotations

import os
from unittest import mock

from trading_agent.growth import shadow_runner


_BASE_PROFILE = {"dsa": 0.25, "technical": 0.30, "kronos": 0.15, "quote": 0.10, "catalyst": 0.20}


def _profile(tmp_path, experiment):
    # _challenger_scoring_profile reads load_scoring_profile + config_dir; patch both so the test is
    # independent of on-disk config.
    with mock.patch.object(shadow_runner, "load_scoring_profile", return_value=dict(_BASE_PROFILE)), \
         mock.patch.object(shadow_runner, "build_runtime_paths") as paths:
        paths.return_value.config_dir = tmp_path
        return shadow_runner._challenger_scoring_profile(tmp_path, experiment)


def test_single_scoring_mutation_always_applies(tmp_path):
    exp = {"module": "scoring", "field": "dsa", "proposed": 0.40}
    prof = _profile(tmp_path, exp)
    assert prof["dsa"] == 0.40
    assert prof["technical"] == 0.30  # untouched


def test_changes_list_applies_when_flag_on(tmp_path):
    exp = {"changes": [{"module": "scoring", "field": "technical", "proposed": 0.45},
                       {"module": "scoring", "field": "kronos", "proposed": 0.05}]}
    with mock.patch.dict(os.environ, {"ENABLE_SHADOW_RESCORE": "1"}, clear=False):
        prof = _profile(tmp_path, exp)
    assert prof["technical"] == 0.45
    assert prof["kronos"] == 0.05
    assert prof["dsa"] == 0.25  # unchanged keys keep the champion value


def test_changes_skips_non_scoring_and_malformed(tmp_path):
    exp = {"changes": [{"module": "risk_overlay", "field": "x", "proposed": 1.0},
                       {"module": "scoring", "field": "dsa", "proposed": "oops"},
                       "not_a_dict"]}
    with mock.patch.dict(os.environ, {"ENABLE_SHADOW_RESCORE": "1"}, clear=False):
        prof = _profile(tmp_path, exp)
    assert prof == _BASE_PROFILE  # nothing valid applied


# --- H4 expensive-path re-scoring config extraction ---

def test_rescore_config_none_for_pure_threshold_challenger():
    # A scoring-profile-only challenger needs no re-scoring → cheap path.
    exp = {"module": "scoring", "field": "trade_threshold", "proposed": 45}
    with mock.patch.dict(os.environ, {"ENABLE_SHADOW_RESCORE": "1"}, clear=False):
        assert shadow_runner._challenger_rescore_config(exp) is None


def test_rescore_config_disables_analyzer():
    exp = {"changes": [{"module": "analyzer", "field": "kronos.enabled", "proposed": False}]}
    with mock.patch.dict(os.environ, {"ENABLE_SHADOW_RESCORE": "1"}, clear=False):
        cfg = shadow_runner._challenger_rescore_config(exp)
    assert cfg["disabled_components"] == {"kronos"}


def test_rescore_config_component_weight_override():
    exp = {"changes": [{"module": "scoring", "field": "technical_weight", "proposed": 0.45}]}
    with mock.patch.dict(os.environ, {"ENABLE_SHADOW_RESCORE": "1"}, clear=False):
        cfg = shadow_runner._challenger_rescore_config(exp)
    assert cfg["component_weights"]["technical"] == 0.45


def test_rescore_config_factor_alpha_weight():
    exp = {"changes": [{"module": "factor", "field": "factor_alpha_weight", "proposed": 0.20}]}
    with mock.patch.dict(os.environ, {"ENABLE_SHADOW_RESCORE": "1"}, clear=False):
        cfg = shadow_runner._challenger_rescore_config(exp)
    assert cfg["factor_alpha_weight"] == 0.20


def test_challenger_candidate_scores_cheap_path_returns_champion(tmp_path, monkeypatch):
    # No rescore config → returns champion candidate_scores untouched (byte-for-byte).
    champion = {"symbols": {"NVDA": {"score": 80}}, "ranked_symbols": ["NVDA"]}
    with mock.patch.object(shadow_runner, "build_runtime_paths") as paths, \
         mock.patch.object(shadow_runner, "_read_json_or_empty", return_value=champion):
        paths.return_value.candidate_scores_path = tmp_path / "cs.json"
        exp = {"module": "scoring", "field": "trade_threshold", "proposed": 45}
        with mock.patch.dict(os.environ, {"ENABLE_SHADOW_RESCORE": "1"}, clear=False):
            result = shadow_runner._challenger_candidate_scores(tmp_path, "2026-06-18", exp)
    assert result is champion
