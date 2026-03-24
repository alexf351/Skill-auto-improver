from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from examples.real_skill_guarded_trial import run_demo


class ExampleTests(unittest.TestCase):
    def test_real_skill_guarded_trial_demo_runs_safe_then_rolls_back_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_demo(tmp)

            self.assertTrue(summary["safe_trial"]["accepted"])
            self.assertFalse(summary["safe_trial"]["rolled_back"])
            self.assertEqual(summary["safe_trial"]["ab"]["recovered_count"], 1)
            self.assertTrue(summary["safe_skill_contains_formal_guidance"])

            self.assertFalse(summary["regression_trial"]["accepted"])
            self.assertTrue(summary["regression_trial"]["rolled_back"])
            self.assertEqual(summary["regression_trial"]["ab"]["regressed_count"], 1)
            self.assertTrue(summary["skill_preserved_after_rollback"])

            self.assertEqual(summary["observe_before_regression"]["trace_count"], 1)
            self.assertEqual(
                summary["observe_before_regression"]["acceptance_reasons"].get("safe improvement"),
                1,
            )
            self.assertIn(
                "continue iterating on the highest-confidence failing fixture",
                summary["inspect_before_regression"]["priorities"],
            )

            self.assertEqual(summary["observe_after_regression"]["trace_count"], 2)
            self.assertEqual(summary["observe_after_regression"]["total_regressions"], 1)
            self.assertIn("recent regressions detected: 1", summary["observe_after_regression"]["signals"])
            self.assertEqual(
                summary["observe_after_regression"]["acceptance_reasons"].get("promoted baseline regression"),
                1,
            )
            self.assertIn(
                "protect promoted fixtures before attempting broader amendments",
                summary["inspect_after_regression"]["priorities"],
            )

            logs_dir = Path(summary["logs_dir"])
            self.assertTrue((logs_dir / "safe-demo-run.json").exists())
            self.assertTrue((logs_dir / "regression-demo-run.json").exists())
            safe_trace = json.loads((logs_dir / "safe-demo-run.json").read_text(encoding="utf-8"))
            self.assertTrue(safe_trace["metadata"]["patch_trial"]["accepted"])


if __name__ == "__main__":
    unittest.main()
