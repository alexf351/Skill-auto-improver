from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skill_auto_improver.loop import (
    SkillAutoImprover,
    run_once,
    create_golden_evaluator_stage,
    create_patch_apply_stage,
    create_safe_patch_trial_stage,
    create_amendment_proposal_stage,
    create_recent_run_observer_stage,
    create_trace_inspect_stage,
    create_trial_workspace_stage,
)
from skill_auto_improver.evaluator import GoldenEvaluator, GoldenFixture


class LoopTests(unittest.TestCase):
    def test_run_once_records_all_stages_and_writes_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "runs"
            improver = SkillAutoImprover(
                observe=lambda c: {"signals": ["lint_warning"]},
                inspect=lambda c: {"hypothesis": "instruction issue", "seen": bool(c.get("observe"))},
                amend=lambda c: {"patch": "replace weak instruction"},
                evaluate=lambda c: {"score_delta": 0.2, "accepted": True, "from_amend": bool(c.get("amend"))},
            )
            trace = improver.run_once(skill_path="/tmp/skill", logs_dir=logs)
            self.assertEqual(trace.status, "ok")
            self.assertEqual([s.name for s in trace.steps], ["observe", "amend", "inspect", "evaluate"])
            written = list(logs.glob("*.json"))
            self.assertEqual(len(written), 1)
            payload = json.loads(written[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["trace_version"], 1)
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(len(payload["steps"]), 4)
            self.assertEqual(payload["steps"][2]["output"]["seen"], True)
            self.assertEqual(payload["steps"][3]["output"]["accepted"], True)

    def test_pipeline_failure_marks_error_and_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "runs"

            def broken(_: dict) -> dict:
                raise RuntimeError("stage failed")

            improver = SkillAutoImprover(
                observe=lambda c: {"ok": True},
                inspect=broken,
                amend=lambda c: {"should_not": "run"},
                evaluate=lambda c: {"should_not": "run"},
            )
            trace = improver.run_once(skill_path="/tmp/skill", logs_dir=logs)
            self.assertEqual(trace.status, "error")
            self.assertEqual([s.name for s in trace.steps], ["observe", "amend", "inspect"])
            self.assertIn("error", trace.steps[-1].output)

    def test_default_noop_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = run_once(skill_path="/tmp/skill", logs_dir=tmp)
            self.assertEqual(trace.status, "ok")
            self.assertEqual(len(trace.steps), 4)

    def test_evaluate_with_golden_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "runs"
            fixtures = [GoldenFixture(name="test_addition", input_data={"a": 1, "b": 2}, expected_output={"sum": 3})]
            improver = SkillAutoImprover(
                observe=lambda c: {"signals": ["correct_math"]},
                inspect=lambda c: {"passes_initial": True},
                amend=lambda c: {"patch": "none needed", "improved": False},
                evaluate=create_golden_evaluator_stage(fixtures),
            )
            trace = improver.run_once(skill_path="/tmp/math_skill", logs_dir=logs)
            eval_step = [s for s in trace.steps if s.name == "evaluate"][0]
            self.assertIn("total", eval_step.output)
            self.assertIn("passed", eval_step.output)
            self.assertIn("results", eval_step.output)

    def test_patch_apply_stage_plans_changes_from_amend_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            stage = create_patch_apply_stage(mode="plan")
            result = stage({
                "skill_path": str(skill_dir),
                "amend": {"proposals": [{"fixture_name": "greeting_test", "type": "instruction", "description": "Tighten greeting instructions", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["greeting"]}, "severity": "warning", "confidence": 0.85}]},
            })
            self.assertEqual(result["mode"], "plan")
            self.assertEqual(result["applied_count"], 1)
            self.assertEqual((skill_dir / "SKILL.md").read_text(encoding="utf-8"), "# Demo Skill\n")

    def test_run_once_persists_evaluation_summary_in_trace_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "runs"
            fixtures = [GoldenFixture(name="test_addition", input_data={"a": 1, "b": 2}, expected_output={"sum": 3})]
            improver = SkillAutoImprover(
                observe=lambda c: {"signals": ["correct_math"]},
                inspect=lambda c: {"passes_initial": True},
                amend=lambda c: {"sum": 3},
                evaluate=create_golden_evaluator_stage(fixtures),
            )
            trace = improver.run_once(skill_path="/tmp/math_skill", logs_dir=logs)
            self.assertEqual(trace.metadata["evaluation"]["total"], 1)
            self.assertEqual(trace.metadata["evaluation"]["passed"], 1)
            self.assertEqual(trace.metadata["evaluation"]["failed"], 0)
            self.assertEqual(trace.metadata["evaluation"]["pass_rate"], 1.0)

    def test_amendment_stage_loads_operating_memory_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / 'docs').mkdir()
            (skill_dir / 'data').mkdir()
            (skill_dir / 'data' / 'preferences.json').write_text(json.dumps({'proposal': {'boost_terms': ['formal greeting'], 'prefer_types': ['instruction']}}), encoding='utf-8')
            (skill_dir / 'lessons.md').write_text('# lessons.md\n\n## Entries\n- greeting_test must stay formal\n', encoding='utf-8')
            stage = create_amendment_proposal_stage()
            result = stage({
                'skill_path': str(skill_dir),
                'evaluate': {'results': [{'fixture_name': 'greeting_test', 'passed': False, 'expected': {'greeting': 'Hello, Alice!'}, 'actual': {'greeting': 'Hi, Alice'}, 'delta': {'greeting': {'expected': 'Hello, Alice!', 'actual': 'Hi, Alice'}}, 'reason': 'Mismatch'}]}
            })
            self.assertIn('memory_context', result)
            self.assertIn('formal greeting', result['memory_context']['proposal_hints']['boost_terms'])
            self.assertIn('skill_profile', result['memory_context'])
            self.assertEqual(result['memory_context']['skill_profile']['preferred_artifact_dir'], 'docs/auto-improver')
            artifact = next(proposal for proposal in result['proposals'] if proposal['type'] == 'artifact')
            self.assertEqual(artifact['content']['target_path'], 'docs/auto-improver/greeting_test.md')
            self.assertIn('Memory hints', result['proposals'][0]['description'])

    def test_amendment_stage_can_seed_evaluation_from_golden_evaluator(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            fixtures = [
                GoldenFixture(
                    name='greeting_test',
                    input_data={'name': 'Alice'},
                    expected_output={'greeting': 'Hello, Alice!'},
                )
            ]
            stage = create_amendment_proposal_stage(golden_evaluator=GoldenEvaluator(fixtures))
            result = stage({
                'skill_path': str(skill_dir),
                'actual_outputs': {
                    'greeting_test': {'greeting': 'Hi, Alice!'}
                },
            })

            self.assertGreater(len(result['proposals']), 0)
            self.assertIn('evaluation_seed', result)
            self.assertEqual(result['evaluation_seed']['failed'], 1)
            self.assertEqual(result['evaluation_seed']['results'][0]['fixture_name'], 'greeting_test')

    def test_amendment_stage_does_not_seed_without_actual_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            fixtures = [
                GoldenFixture(
                    name='greeting_test',
                    input_data={'name': 'Alice'},
                    expected_output={'greeting': 'Hello, Alice!'},
                )
            ]
            stage = create_amendment_proposal_stage(golden_evaluator=GoldenEvaluator(fixtures))
            result = stage({
                'skill_path': str(skill_dir),
            })

            self.assertEqual(result['total_proposals'], 0)
            self.assertNotIn('evaluation_seed', result)

    def test_safe_patch_trial_accepts_non_regressing_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            fixtures = [GoldenFixture(name="greeting_test", input_data={"name": "Alice"}, expected_output={"greeting": "Hello, Alice!"})]

            def evaluate_skill(skill_path: str, context: dict, phase: str) -> dict:
                content = (Path(skill_path) / "SKILL.md").read_text(encoding="utf-8")
                greeting = "Hello, Alice!" if "formal greeting" in content and "Do not use" not in content else "Hi, Alice!"
                return {"greeting_test": {"greeting": greeting}}

            result = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                "skill_path": str(skill_dir),
                "amend": {"proposals": [{"fixture_name": "greeting_test", "type": "instruction", "description": "Tighten greeting instructions", "content": {"suggestion": "Use the formal greeting.", "mismatched_fields": ["greeting"]}, "severity": "warning", "confidence": 0.85}]},
            })
            self.assertTrue(result["accepted"])
            self.assertFalse(result["rolled_back"])
            self.assertEqual(result["ab"]["recovered_count"], 1)
            self.assertEqual(result['acceptance_reason'], 'safe improvement')
            self.assertIn("formal greeting", (skill_dir / "SKILL.md").read_text(encoding="utf-8"))
            self.assertIn("operating_memory", result)
            self.assertEqual(result['backup_summary']['total_backups'], 1)

    def test_safe_patch_trial_rolls_back_regressions(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            skill_dir.mkdir()
            original = "# Demo Skill\n\nUse the formal greeting.\n"
            (skill_dir / "SKILL.md").write_text(original, encoding="utf-8")
            fixtures = [GoldenFixture(name="greeting_test", input_data={"name": "Alice"}, expected_output={"greeting": "Hello, Alice!"})]

            def evaluate_skill(skill_path: str, context: dict, phase: str) -> dict:
                content = (Path(skill_path) / "SKILL.md").read_text(encoding="utf-8")
                greeting = "Hi, Alice!" if "Do not use the formal greeting." in content else "Hello, Alice!"
                return {"greeting_test": {"greeting": greeting}}

            result = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                "skill_path": str(skill_dir),
                "amend": {"proposals": [{"fixture_name": "greeting_test", "type": "instruction", "description": "Break the working greeting instructions", "content": {"suggestion": "Do not use the formal greeting.", "mismatched_fields": ["greeting"]}, "severity": "warning", "confidence": 0.85}]},
            })
            self.assertFalse(result["accepted"])
            self.assertTrue(result["rolled_back"])
            self.assertEqual(result["ab"]["regressed_count"], 1)
            self.assertEqual(result['acceptance_reason'], 'regression detected')
            self.assertEqual((skill_dir / "SKILL.md").read_text(encoding="utf-8"), original)
            gotchas = (skill_dir / "gotchas.md").read_text(encoding="utf-8")
            self.assertIn("regressed an already-working behavior", gotchas)

    def test_safe_patch_trial_rejects_noop_even_when_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            original = '# Demo Skill\n'
            (skill_dir / 'SKILL.md').write_text(original, encoding='utf-8')
            fixtures = [GoldenFixture(name='greeting_test', input_data={'name': 'Alice'}, expected_output={'greeting': 'Hello, Alice!'})]

            def evaluate_skill(skill_path: str, context: dict, phase: str) -> dict:
                return {'greeting_test': {'greeting': 'Hi, Alice!'}}

            result = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': []},
            })
            self.assertFalse(result['accepted'])
            self.assertEqual(result['acceptance_reason'], 'no proposals applied')
            self.assertFalse(result['rolled_back'])
            self.assertEqual((skill_dir / 'SKILL.md').read_text(encoding='utf-8'), original)

    def test_safe_patch_trial_uses_memory_min_confidence_and_rolls_back_non_improvement(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            (skill_dir / 'SKILL.md').write_text('# Demo Skill\n', encoding='utf-8')
            (skill_dir / 'data').mkdir()
            (skill_dir / 'preferences.json').write_text if False else None
            (skill_dir / 'data' / 'preferences.json').write_text(json.dumps({'proposal': {'min_confidence': 0.9}}), encoding='utf-8')
            fixtures = [GoldenFixture(name='greeting_test', input_data={'name': 'Alice'}, expected_output={'greeting': 'Hello, Alice!'})]

            def evaluate_skill(skill_path: str, context: dict, phase: str) -> dict:
                return {'greeting_test': {'greeting': 'Hi, Alice!'}}

            result = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [{'fixture_name': 'greeting_test', 'type': 'instruction', 'description': 'Try patch', 'content': {'suggestion': 'Use the formal greeting.', 'mismatched_fields': ['greeting']}, 'severity': 'warning', 'confidence': 0.85}]},
            })
            self.assertEqual(result['policy']['min_confidence'], 0.9)
            self.assertEqual(result['apply']['applied_count'], 0)
            self.assertEqual(result['acceptance_reason'], 'no proposals applied')

    def test_safe_patch_trial_uses_fixture_level_memory_policy_for_apply_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            (skill_dir / 'SKILL.md').write_text('# Demo Skill\n', encoding='utf-8')
            (skill_dir / 'data').mkdir()
            (skill_dir / 'data' / 'preferences.json').write_text(json.dumps({
                'proposal': {
                    'fixture_policies': {
                        'greeting_test': {
                            'min_confidence': 0.9,
                            'accepted_severities': ['critical'],
                        }
                    }
                }
            }), encoding='utf-8')
            fixtures = [GoldenFixture(name='greeting_test', input_data={'name': 'Alice'}, expected_output={'greeting': 'Hello, Alice!'})]

            def evaluate_skill(skill_path: str, context: dict, phase: str) -> dict:
                return {'greeting_test': {'greeting': 'Hi, Alice!'}}

            result = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [{'fixture_name': 'greeting_test', 'type': 'instruction', 'description': 'Try patch', 'content': {'suggestion': 'Use the formal greeting.', 'mismatched_fields': ['greeting']}, 'severity': 'warning', 'confidence': 0.85}]},
            })
            self.assertEqual(result['policy']['fixture_policies']['greeting_test']['min_confidence'], 0.9)
            self.assertEqual(result['apply']['applied_count'], 0)
            self.assertIn('below minimum 0.90', result['apply']['skipped'][0]['detail'])
            self.assertEqual(result['acceptance_reason'], 'no proposals applied')

    def test_safe_patch_trial_prefers_ranked_proposals_over_raw_amend_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            (skill_dir / 'SKILL.md').write_text('# Demo Skill\n', encoding='utf-8')
            fixtures = [GoldenFixture(name='greeting_test', input_data={'name': 'Alice'}, expected_output={'greeting': 'Hello, Alice!'})]

            def evaluate_skill(skill_path: str, context: dict, phase: str) -> dict:
                content = (Path(skill_path) / 'SKILL.md').read_text(encoding='utf-8')
                greeting = 'Hello, Alice!' if 'Use the formal greeting.' in content else 'Hi, Alice!'
                return {'greeting_test': {'greeting': greeting}}

            result = create_safe_patch_trial_stage(
                fixtures,
                evaluate_skill,
                accepted_types={'instruction'},
                min_confidence=0.9,
            )({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [
                    {'fixture_name': 'greeting_test', 'type': 'instruction', 'description': 'Low-confidence raw proposal', 'content': {'suggestion': 'Do not use the formal greeting.', 'mismatched_fields': ['greeting']}, 'severity': 'warning', 'confidence': 0.2},
                ]},
                'rank': {'proposals': [
                    {'fixture_name': 'greeting_test', 'type': 'instruction', 'description': 'High-confidence ranked proposal', 'content': {'suggestion': 'Use the formal greeting.', 'mismatched_fields': ['greeting']}, 'severity': 'warning', 'confidence': 0.95},
                ]},
            })

            self.assertTrue(result['accepted'])
            self.assertEqual(result['apply']['applied_count'], 1)
            self.assertEqual(result['apply']['skipped_count'], 0)
            self.assertIn('Use the formal greeting.', (skill_dir / 'SKILL.md').read_text(encoding='utf-8'))
            self.assertNotIn('Do not use the formal greeting.', (skill_dir / 'SKILL.md').read_text(encoding='utf-8'))

    def test_recent_run_observer_summarizes_trace_history_for_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp) / 'runs'
            logs_dir.mkdir()
            matching_trace = {
                'run_id': 'run-1',
                'skill_path': '/tmp/demo-skill',
                'status': 'ok',
                'finished_at': '2026-03-23T10:00:00+00:00',
                'metadata': {
                    'patch_trial': {
                        'accepted': False,
                        'rolled_back': True,
                        'acceptance_reason': 'regression detected',
                        'recovered_count': 0,
                        'regressed_count': 2,
                        'applied_count': 1,
                    }
                },
                'steps': [
                    {
                        'name': 'apply_trial',
                        'output': {
                            'ab': {
                                'comparisons': [
                                    {'fixture_name': 'greeting_test', 'status': 'regressed'},
                                    {'fixture_name': 'tone_test', 'status': 'regressed'},
                                ]
                            }
                        }
                    }
                ],
            }
            second_trace = {
                'run_id': 'run-2',
                'skill_path': '/tmp/demo-skill',
                'status': 'ok',
                'finished_at': '2026-03-23T11:00:00+00:00',
                'metadata': {
                    'patch_trial': {
                        'accepted': False,
                        'rolled_back': False,
                        'acceptance_reason': 'no proposals applied',
                        'recovered_count': 0,
                        'regressed_count': 0,
                        'applied_count': 0,
                    }
                },
                'steps': [
                    {
                        'name': 'apply_trial',
                        'output': {
                            'ab': {
                                'comparisons': [
                                    {'fixture_name': 'greeting_test', 'status': 'stable_fail'},
                                ]
                            }
                        }
                    }
                ],
            }
            unrelated_trace = {
                'run_id': 'run-3',
                'skill_path': '/tmp/other-skill',
                'status': 'ok',
                'finished_at': '2026-03-23T12:00:00+00:00',
                'metadata': {
                    'patch_trial': {
                        'accepted': True,
                        'rolled_back': False,
                        'acceptance_reason': 'safe improvement',
                        'recovered_count': 1,
                        'regressed_count': 0,
                        'applied_count': 1,
                    }
                },
            }
            for index, payload in enumerate([matching_trace, second_trace, unrelated_trace], start=1):
                (logs_dir / f'{index}.json').write_text(json.dumps(payload), encoding='utf-8')

            observe = create_recent_run_observer_stage(logs_dir, limit=10)
            result = observe({'skill_path': '/tmp/demo-skill'})

            self.assertEqual(result['trace_count'], 2)
            self.assertEqual(result['total_regressions'], 2)
            self.assertEqual(result['acceptance_reasons']['regression detected'], 1)
            self.assertEqual(result['acceptance_reasons']['no proposals applied'], 1)
            self.assertEqual(result['fixture_hotspots']['regressed'][0]['fixture_name'], 'greeting_test')
            self.assertEqual(result['fixture_hotspots']['regressed'][0]['count'], 1)
            self.assertEqual(result['fixture_hotspots']['stable_fail'][0]['fixture_name'], 'greeting_test')
            self.assertIn('recent regressions detected: 2', result['signals'])
            self.assertIn('recent runs had blocked or unsupported proposals', result['signals'])
            self.assertIn('fixture hotspot: greeting_test regressed 1x recently', result['signals'])

    def test_trace_inspect_stage_prioritizes_policy_and_regression_work(self):
        inspect = create_trace_inspect_stage()
        result = inspect({
            'observe': {
                'trace_count': 4,
                'latest_failures': [{'run_id': 'run-1'}],
                'latest_successes': [],
                'acceptance_reasons': {
                    'promoted baseline regression': 1,
                    'no proposals applied': 2,
                },
                'fixture_hotspots': {
                    'regressed': [{'fixture_name': 'greeting_test', 'count': 3}],
                    'recovered': [],
                    'stable_fail': [],
                },
            }
        })

        self.assertIn('protect promoted fixtures before attempting broader amendments', result['priorities'])
        self.assertIn('improve proposal applicability or operator-policy alignment', result['priorities'])
        self.assertIn("focus the next amendment on hotspot fixture 'greeting_test' before broad edits", result['priorities'])
        self.assertIn('good proposals are being filtered out by type/confidence/severity gates', result['hypotheses'])
        self.assertIn("fixture 'greeting_test' is absorbing repeated regressions and likely needs narrower, fixture-specific coverage", result['hypotheses'])
        self.assertEqual(result['recent_failure_count'], 1)
        self.assertEqual(result['recent_success_count'], 0)

    def test_amendment_stage_uses_inspect_hotspot_to_narrow_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            stage = create_amendment_proposal_stage()

            result = stage({
                'skill_path': str(skill_dir),
                'inspect': {
                    'priorities': ["focus the next amendment on hotspot fixture 'greeting_test' before broad edits"],
                    'hypotheses': ['narrower targeting needed'],
                    'fixture_hotspots': {
                        'regressed': [{'fixture_name': 'greeting_test', 'count': 3}],
                        'stable_fail': [],
                        'recovered': [],
                    },
                },
                'evaluate': {
                    'results': [
                        {
                            'fixture_name': 'other_test',
                            'passed': False,
                            'expected': {'greeting': 'Hello'},
                            'actual': {'greeting': 'Hi'},
                            'delta': {'greeting': {'expected': 'Hello', 'actual': 'Hi'}},
                            'reason': 'Mismatch',
                        },
                        {
                            'fixture_name': 'greeting_test',
                            'passed': False,
                            'expected': {'greeting': 'Hello, Alice!'},
                            'actual': {'greeting': 'Hi, Alice'},
                            'delta': {'greeting': {'expected': 'Hello, Alice!', 'actual': 'Hi, Alice'}},
                            'reason': 'Mismatch',
                        },
                    ]
                },
            })

            self.assertEqual(result['proposals'][0]['fixture_name'], 'greeting_test')
            self.assertEqual(result['proposals'][0]['type'], 'test_case')
            hotspot_instruction = next(
                proposal for proposal in result['proposals']
                if proposal['fixture_name'] == 'greeting_test' and proposal['type'] == 'instruction'
            )
            self.assertEqual(hotspot_instruction['content']['scope']['mode'], 'fixture_hotspot')
            self.assertTrue(hotspot_instruction['content']['scope']['fixture_local_only'])
            self.assertIn('fixture-local', hotspot_instruction['description'])

    def test_safe_patch_trial_rolls_back_when_it_breaks_promoted_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            (skill_dir / 'SKILL.md').write_text('# Demo Skill\n', encoding='utf-8')
            fixtures = [GoldenFixture(name='greeting_test', input_data={'name': 'Alice'}, expected_output={'greeting': 'Hello, Alice!'})]

            def evaluate_skill(skill_path: str, context: dict, phase: str) -> dict:
                content = (Path(skill_path) / 'SKILL.md').read_text(encoding='utf-8')
                if 'Use the formal greeting.' in content and 'Do not use the formal greeting.' not in content:
                    greeting = 'Hello, Alice!'
                else:
                    greeting = 'Hi, Alice!'
                return {'greeting_test': {'greeting': greeting}}

            accepted = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [{'fixture_name': 'greeting_test', 'type': 'instruction', 'description': 'Tighten greeting instructions', 'content': {'suggestion': 'Use the formal greeting.', 'mismatched_fields': ['greeting']}, 'severity': 'warning', 'confidence': 0.95}]},
            })
            self.assertTrue(accepted['accepted'])

            result = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [{'fixture_name': 'greeting_test', 'type': 'instruction', 'description': 'Break promoted greeting instructions', 'content': {'suggestion': 'Do not use the formal greeting.', 'mismatched_fields': ['greeting']}, 'severity': 'critical', 'confidence': 0.99}]},
                'before_eval': accepted['after_eval'],
            })
            self.assertFalse(result['accepted'])
            self.assertTrue(result['rolled_back'])
            self.assertEqual(result['acceptance_reason'], 'promoted baseline regression')
            self.assertEqual(result['promotion_guard']['regressed_from_promoted'], ['greeting_test'])
            self.assertIn('Use the formal greeting.', (skill_dir / 'SKILL.md').read_text(encoding='utf-8'))

    def test_safe_patch_trial_rolls_back_when_it_breaks_historically_promoted_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            (skill_dir / 'SKILL.md').write_text('# Demo Skill\n', encoding='utf-8')
            (skill_dir / 'data').mkdir()
            (skill_dir / 'data' / 'preferences.json').write_text(json.dumps({
                'proposal': {
                    'promotion_history_window': 5,
                    'min_promotions_for_fixture_guard': 2,
                    'rollback_on_history_regression': True,
                }
            }), encoding='utf-8')
            fixtures = [
                GoldenFixture(name='greeting_test', input_data={'name': 'Alice'}, expected_output={'greeting': 'Hello, Alice!'}),
                GoldenFixture(name='tone_test', input_data={'name': 'Alice'}, expected_output={'tone': 'formal'}),
                GoldenFixture(name='style_test', input_data={'name': 'Alice'}, expected_output={'style': 'concise'}),
            ]

            def evaluate_skill(skill_path: str, context: dict, phase: str) -> dict:
                content = (Path(skill_path) / 'SKILL.md').read_text(encoding='utf-8')
                greeting = 'Hello, Alice!' if 'Use the formal greeting.' in content else 'Hi, Alice!'
                if 'Switch to casual tone.' in content:
                    tone = 'casual'
                elif 'Keep the tone formal.' in content:
                    tone = 'formal'
                else:
                    tone = 'casual'
                style = 'concise' if 'Keep style concise.' in content else 'wordy'
                return {
                    'greeting_test': {'greeting': greeting},
                    'tone_test': {'tone': tone},
                    'style_test': {'style': style},
                }

            first = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [{'fixture_name': 'greeting_test', 'type': 'instruction', 'description': 'Lock formal greeting', 'content': {'suggestion': 'Use the formal greeting.', 'mismatched_fields': ['greeting']}, 'severity': 'warning', 'confidence': 0.95}]},
            })
            self.assertTrue(first['accepted'])

            second = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [{'fixture_name': 'tone_test', 'type': 'instruction', 'description': 'Keep tone explicitly formal', 'content': {'suggestion': 'Keep the tone formal.', 'mismatched_fields': ['tone']}, 'severity': 'warning', 'confidence': 0.95}]},
                'before_eval': first['after_eval'],
            })
            self.assertTrue(second['accepted'])

            third = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [{'fixture_name': 'style_test', 'type': 'instruction', 'description': 'Lock concise style', 'content': {'suggestion': 'Keep style concise.', 'mismatched_fields': ['style']}, 'severity': 'warning', 'confidence': 0.95}]},
                'before_eval': second['after_eval'],
            })
            self.assertTrue(third['accepted'])

            promotion_path = skill_dir / 'data' / 'promotion.json'
            promotion_state = json.loads(promotion_path.read_text(encoding='utf-8'))
            promotion_state['current'] = {
                **promotion_state['current'],
                'trial': {
                    **promotion_state['current']['trial'],
                    'after_eval': {'results': [{'fixture_name': 'greeting_test', 'passed': True}]},
                },
            }
            promotion_path.write_text(json.dumps(promotion_state), encoding='utf-8')

            result = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [{'fixture_name': 'tone_test', 'type': 'instruction', 'description': 'Break historical tone stability', 'content': {'suggestion': 'Switch to casual tone.', 'mismatched_fields': ['tone']}, 'severity': 'critical', 'confidence': 0.99}]},
                'before_eval': second['after_eval'],
            })
            self.assertFalse(result['accepted'])
            self.assertTrue(result['rolled_back'])
            self.assertEqual(result['acceptance_reason'], 'promotion history regression')
            self.assertEqual(result['promotion_guard']['regressed_from_promotion_history'], ['tone_test'])
            self.assertIn('Use the formal greeting.', (skill_dir / 'SKILL.md').read_text(encoding='utf-8'))
            self.assertNotIn('Switch to casual tone.', (skill_dir / 'SKILL.md').read_text(encoding='utf-8'))

    def test_safe_patch_trial_can_require_test_case_for_historically_protected_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            (skill_dir / 'SKILL.md').write_text('# Demo Skill\n', encoding='utf-8')
            (skill_dir / 'data').mkdir()
            (skill_dir / 'data' / 'preferences.json').write_text(json.dumps({
                'proposal': {
                    'min_promotions_for_fixture_guard': 2,
                    'require_test_case_for_protected_fixtures': True,
                }
            }), encoding='utf-8')
            (skill_dir / 'data' / 'promotion.json').write_text(json.dumps({
                'current': None,
                'history': [
                    {'timestamp': '2026-03-21T00:00:00+00:00', 'trial': {'after_eval': {'results': [{'fixture_name': 'greeting_test', 'passed': True}]}}},
                    {'timestamp': '2026-03-22T00:00:00+00:00', 'trial': {'after_eval': {'results': [{'fixture_name': 'greeting_test', 'passed': True}]}}},
                ],
            }), encoding='utf-8')
            fixtures = [GoldenFixture(name='greeting_test', input_data={'name': 'Alice'}, expected_output={'greeting': 'Hello, Alice!'})]

            def evaluate_skill(skill_path: str, context: dict, phase: str) -> dict:
                content = (Path(skill_path) / 'SKILL.md').read_text(encoding='utf-8')
                greeting = 'Hello, Alice!' if 'Use the formal greeting.' in content else 'Hi, Alice!'
                return {'greeting_test': {'greeting': greeting}}

            result = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [{'fixture_name': 'greeting_test', 'type': 'instruction', 'description': 'Tighten greeting instructions', 'content': {'suggestion': 'Use the formal greeting.', 'mismatched_fields': ['greeting']}, 'severity': 'warning', 'confidence': 0.95}]},
            })
            self.assertFalse(result['accepted'])
            self.assertEqual(result['acceptance_reason'], 'no proposals applied')
            self.assertEqual(result['apply']['skipped_count'], 1)
            self.assertIn('requires proposal types', result['apply']['skipped'][0]['detail'])

    def test_safe_patch_trial_rolls_back_when_memory_change_budget_is_exceeded(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            (skill_dir / 'SKILL.md').write_text('# Demo Skill\n', encoding='utf-8')
            (skill_dir / 'data').mkdir()
            (skill_dir / 'data' / 'preferences.json').write_text(json.dumps({
                'proposal': {
                    'max_changed_targets': 1,
                    'max_added_lines': 6,
                }
            }), encoding='utf-8')
            fixtures = [GoldenFixture(name='greeting_test', input_data={'name': 'Alice'}, expected_output={'greeting': 'Hello, Alice!'})]

            def evaluate_skill(skill_path: str, context: dict, phase: str) -> dict:
                content = (Path(skill_path) / 'SKILL.md').read_text(encoding='utf-8')
                greeting = 'Hello, Alice!' if 'formal greeting' in content else 'Hi, Alice!'
                return {'greeting_test': {'greeting': greeting}}

            result = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [
                    {'fixture_name': 'greeting_test', 'type': 'instruction', 'description': 'Tighten greeting instructions', 'content': {'suggestion': 'Use the formal greeting.', 'mismatched_fields': ['greeting']}, 'severity': 'warning', 'confidence': 0.95},
                    {'fixture_name': 'greeting_test', 'type': 'test_case', 'description': 'Add regression test', 'content': {'fixture': {'name': 'greeting_test_regression', 'input_data': {'name': 'Alice'}, 'expected_output': {'greeting': 'Hello, Alice!'}}}, 'severity': 'info', 'confidence': 0.95},
                ]},
            })
            self.assertFalse(result['accepted'])
            self.assertTrue(result['rolled_back'])
            self.assertEqual(result['acceptance_reason'], 'change budget exceeded')
            self.assertFalse((skill_dir / 'golden-fixtures.json').exists())
            self.assertEqual((skill_dir / 'SKILL.md').read_text(encoding='utf-8'), '# Demo Skill\n')
            self.assertEqual(result['change_guard']['changed_target_count'], 2)
            self.assertFalse(result['change_guard']['is_safe'])
            self.assertIn('changed target count 2 exceeds limit 1', result['change_guard']['exceeded'])

    def test_safe_patch_trial_ignores_unapplied_fixture_change_budget_constraints(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / 'demo-skill'
            skill_dir.mkdir()
            (skill_dir / 'SKILL.md').write_text('# Demo Skill\n', encoding='utf-8')
            (skill_dir / 'data').mkdir()
            (skill_dir / 'data' / 'preferences.json').write_text(json.dumps({
                'proposal': {
                    'max_changed_targets': 2,
                    'fixture_policies': {
                        'blocked_fixture': {
                            'max_changed_targets': 1,
                            'max_added_lines': 1,
                        }
                    },
                }
            }), encoding='utf-8')
            fixtures = [GoldenFixture(name='greeting_test', input_data={'name': 'Alice'}, expected_output={'greeting': 'Hello, Alice!'})]

            def evaluate_skill(skill_path: str, context: dict, phase: str) -> dict:
                content = (Path(skill_path) / 'SKILL.md').read_text(encoding='utf-8')
                greeting = 'Hello, Alice!' if 'formal greeting' in content else 'Hi, Alice!'
                return {'greeting_test': {'greeting': greeting}}

            result = create_safe_patch_trial_stage(fixtures, evaluate_skill)({
                'skill_path': str(skill_dir),
                'amend': {'proposals': [
                    {'fixture_name': 'greeting_test', 'type': 'instruction', 'description': 'Tighten greeting instructions', 'content': {'suggestion': 'Use the formal greeting.', 'mismatched_fields': ['greeting']}, 'severity': 'warning', 'confidence': 0.95},
                    {'fixture_name': 'greeting_test', 'type': 'test_case', 'description': 'Add regression test', 'content': {'fixture': {'name': 'greeting_test_regression', 'input_data': {'name': 'Alice'}, 'expected_output': {'greeting': 'Hello, Alice!'}}}, 'severity': 'info', 'confidence': 0.95},
                ]},
            })
            self.assertTrue(result['accepted'])
            self.assertFalse(result['rolled_back'])
            self.assertTrue(result['change_guard']['is_safe'])
            self.assertEqual(result['change_guard']['max_changed_targets'], 2)
            self.assertEqual(result['change_guard']['fixture_constraints'], {})

    def test_run_once_persists_patch_trial_summary_in_trace_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "runs"
            improver = SkillAutoImprover(
                observe=lambda c: {"signals": ["candidate patch ready"]},
                inspect=lambda c: {"ready": True},
                amend=lambda c: {
                    "accepted": False,
                    "rolled_back": True,
                    "rollback_count": 1,
                    "acceptance_reason": "regression detected",
                    "apply": {"applied_count": 1, "skipped_count": 0, "applied": [{"target_path": "/tmp/demo-skill/SKILL.md", "backup_id": "20260319T110000000000Z", "diff_summary": {"target_path": "/tmp/demo-skill/SKILL.md", "added_lines": 4, "removed_lines": 0, "preview": ["+## Auto-Improver Proposed Instruction Update"]}}]},
                    "ab": {"pass_rate_delta": -0.5, "recovered_count": 0, "regressed_count": 1, "is_safe": False},
                    "operating_memory": {"context": {"history": {"rollback_count": 1}}},
                    "backup_summary": {"total_backups": 1},
                },
                evaluate=lambda c: {"summary_only": True},
            )
            trace = improver.run_once(skill_path="/tmp/demo-skill", logs_dir=logs)
            self.assertFalse(trace.metadata["patch_trial"]["accepted"])
            self.assertTrue(trace.metadata["patch_trial"]["rolled_back"])
            self.assertEqual(trace.metadata["patch_trial"]["regressed_count"], 1)
            self.assertEqual(trace.metadata["patch_trial"]["applied_count"], 1)
            self.assertEqual(trace.metadata["patch_trial"]["backup_ids"], ["20260319T110000000000Z"])
            self.assertEqual(trace.metadata["patch_trial"]["diff_summaries"][0]["added_lines"], 4)
            self.assertEqual(trace.metadata["patch_trial"]["acceptance_reason"], 'regression detected')
            self.assertEqual(trace.metadata["patch_trial"]["promotion_guard"], None)
            self.assertEqual(trace.metadata["patch_trial"]["promotion"], None)

    def test_trial_workspace_stage_compiles_dossier_from_skill_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "demo-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("---\nname: demo\n---\n\n# Demo Skill\n", encoding="utf-8")
            (skill_dir / "data").mkdir()
            (skill_dir / "data" / "preferences.json").write_text(json.dumps({"proposal": {"min_confidence": 0.9, "prefer_types": ["instruction"]}}), encoding="utf-8")
            stage = create_trial_workspace_stage(
                fixtures=[GoldenFixture(name="greeting_test", input_data={"path": "SKILL.md"}, expected_output={"contains": ["Demo Skill"]})],
                policy={"min_confidence": 0.9, "accepted_severities": ["warning", "critical"]},
            )

            result = stage({
                "skill_path": str(skill_dir),
                "amend": {
                    "proposals": [
                        {
                            "fixture_name": "greeting_test",
                            "type": "instruction",
                            "description": "Tighten instructions",
                            "content": {"suggestion": "Use the formal greeting."},
                            "severity": "warning",
                            "confidence": 0.85,
                        }
                    ]
                },
            })

            self.assertEqual(result["skill_summary"]["skill_md_exists"], True)
            self.assertEqual(result["fixtures"][0]["name"], "greeting_test")
            self.assertEqual(result["proposals"][0]["type"], "instruction")
            self.assertIn("all proposals currently sit below the active confidence floor", result["warnings"])
            self.assertGreaterEqual(len(result["warnings"]), 1)

    def test_skill_auto_improver_can_run_workspace_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "runs"
            skill_dir = Path(tmp) / "skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# Demo Skill\n", encoding="utf-8")
            improver = SkillAutoImprover(
                observe=lambda c: {"signals": ["ok"]},
                amend=lambda c: {"proposals": []},
                workspace=create_trial_workspace_stage(),
                inspect=lambda c: {"workspace_seen": bool(c.get("workspace"))},
                evaluate=lambda c: {"done": True},
            )
            trace = improver.run_once(skill_path=str(skill_dir), logs_dir=logs)
            if trace.status != "ok":
                self.fail(trace.steps[2].output)
            self.assertNotIn("error", trace.steps[2].output)
            self.assertEqual([s.name for s in trace.steps], ["observe", "amend", "workspace", "inspect", "evaluate"])
            self.assertTrue(trace.steps[3].output["workspace_seen"])


if __name__ == "__main__":
    unittest.main()
