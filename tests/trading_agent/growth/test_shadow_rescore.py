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


def test_changes_list_ignored_when_flag_off(tmp_path):
    exp = {"changes": [{"module": "scoring", "field": "technical", "proposed": 0.45},
                       {"module": "scoring", "field": "kronos", "proposed": 0.05}]}
    with mock.patch.dict(os.environ, {"ENABLE_SHADOW_RESCORE": "0"}, clear=False):
        prof = _profile(tmp_path, exp)
    assert prof == _BASE_PROFILE  # changes list not applied


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
