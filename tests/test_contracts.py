import unittest

from trading_agent.contracts.kronos import validate_kronos_payload
from trading_agent.contracts.technical import validate_technical_payload


class ContractTests(unittest.TestCase):
    def test_validate_kronos_payload_accepts_minimal_valid_shape(self) -> None:
        payload = {
            "date": "2026-06-14",
            "generated_at": "2026-06-14T05:30:00-07:00",
            "timeframe": "30m",
            "horizon_bars": 8,
            "source_universe": "config/universe.txt",
            "model": {"name": "NeoQuasar/Kronos-small", "tokenizer": "base", "mode": "inference_only"},
            "data_status": "ok",
            "symbols": {},
            "notes": "ok",
        }
        validate_kronos_payload(payload)

    def test_validate_technical_payload_requires_symbols(self) -> None:
        with self.assertRaises(ValueError):
            validate_technical_payload({"date": "2026-06-14"})
