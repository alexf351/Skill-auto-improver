"""Tests for ProposalEngine amendment proposals."""

import unittest
from pathlib import Path
import tempfile
import json

from skill_auto_improver.evaluator import TestResult, GoldenFixture
from skill_auto_improver.proposer import ProposalEngine
from skill_auto_improver.operating_memory import scaffold_operating_memory


class ProposalEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = ProposalEngine()

    def _failed(self, fixture_name: str = "test_greeting") -> TestResult:
        return TestResult(
            fixture_name=fixture_name,
            passed=False,
            expected={"greeting": "Hello, Alice!"},
            actual={"greeting": "Hi, Alice"},
            delta={"greeting": {"expected": "Hello, Alice!", "actual": "Hi, Alice"}},
            reason="Mismatch",
        )

    def test_generate_proposals_instruction_type(self):
        report = self.engine.generate_proposals([self._failed()])
        self.assertEqual(report.total_failures, 1)
        self.assertGreaterEqual(report.total_proposals, 1)
        instr = report.proposals_by_type("instruction")[0]
        self.assertIn("greeting", instr.description)
        self.assertEqual(instr.severity, "warning")

    def test_generate_proposals_test_case_type(self):
        report = self.engine.generate_proposals([self._failed()])
        test_prop = report.proposals_by_type("test_case")[0]
        self.assertIn("regression", test_prop.description)
        self.assertEqual(test_prop.type, "test_case")
        self.assertIn("fixture", test_prop.content)

    def test_generate_proposals_reasoning_type(self):
        failed = TestResult(
            fixture_name="test_complex",
            passed=False,
            expected={"a": 1, "b": 2, "c": 3},
            actual={"a": 1, "b": 99},
            delta={"b": {"expected": 2, "actual": 99}, "c": {"expected": 3, "actual": "<missing>"}},
            reason="Mismatch",
        )
        report = self.engine.generate_proposals([failed])
        reasoning = report.proposals_by_type("reasoning")[0]
        self.assertIn("Root cause", reasoning.description)
        self.assertIn("root_cause_hypothesis", reasoning.content)

    def test_generate_proposals_multiple_failures(self):
        report = self.engine.generate_proposals([self._failed("test_greeting"), self._failed("test_farewell")])
        self.assertEqual(report.total_failures, 2)
        fixtures = {p.fixture_name for p in report.proposals}
        self.assertIn("test_greeting", fixtures)
        self.assertIn("test_farewell", fixtures)

    def test_generate_proposals_empty_failures(self):
        report = self.engine.generate_proposals([])
        self.assertEqual(report.total_failures, 0)
        self.assertEqual(report.total_proposals, 0)

    def test_proposal_with_no_delta_skips_instruction(self):
        failed = TestResult(fixture_name="test_ok", passed=False, expected={}, actual={}, delta={})
        report = self.engine.generate_proposals([failed])
        self.assertEqual(len(report.proposals_by_type("instruction")), 0)

    def test_proposal_report_to_dict(self):
        report_dict = self.engine.generate_proposals([self._failed("test_x")]).to_dict()
        self.assertIn("total_failures", report_dict)
        self.assertIn("total_proposals", report_dict)
        self.assertIn("proposals", report_dict)
        self.assertEqual(report_dict["total_failures"], 1)

    def test_proposal_confidence_levels(self):
        report = self.engine.generate_proposals([self._failed("test_x")])
        for proposal in report.proposals:
            self.assertGreaterEqual(proposal.confidence, 0.0)
            self.assertLessEqual(proposal.confidence, 1.0)

    def test_proposal_severity_escalation(self):
        failed_single = TestResult(
            fixture_name="test_single",
            passed=False,
            expected={"a": 1},
            actual={"a": 2},
            delta={"a": {"expected": 1, "actual": 2}},
        )
        reasoning_single = self.engine.generate_proposals([failed_single]).proposals_by_type("reasoning")
        self.assertEqual(reasoning_single[0].severity, "warning")

        failed_multi = TestResult(
            fixture_name="test_multi",
            passed=False,
            expected={"a": 1, "b": 2, "c": 3},
            actual={"a": 9, "b": 9, "c": 9},
            delta={"a": {"expected": 1, "actual": 9}, "b": {"expected": 2, "actual": 9}, "c": {"expected": 3, "actual": 9}},
        )
        reasoning_multi = self.engine.generate_proposals([failed_multi]).proposals_by_type("reasoning")
        self.assertEqual(reasoning_multi[0].severity, "critical")

    def test_operating_memory_biases_proposals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scaffold_operating_memory(root)
            (root / 'lessons.md').write_text(
                '# lessons.md\n\n## Entries\n- Date: 2026-03-21\n- Pattern: greeting_test must stay formal\n- Rule: use a formal greeting and full salutation\n- Example: greeting_test expects Hello, Alice!\n',
                encoding='utf-8',
            )
            (root / 'gotchas.md').write_text(
                '# gotchas.md\n\n## Gotchas\n- Failure: greeting_test regressed before\n- Trigger: casual greeting wording slipped in\n- Prevention: avoid casual greeting phrasing\n',
                encoding='utf-8',
            )
            (root / 'data' / 'preferences.json').write_text(json.dumps({
                'proposal': {
                    'boost_terms': ['formal greeting'],
                    'prefer_types': ['instruction'],
                    'fixture_policies': {
                        'greeting_test': {
                            'boost_terms': ['keep salutations formal'],
                            'avoid_terms': ['do not say hey'],
                            'prefer_types': ['instruction'],
                            'min_confidence': 0.95,
                            'accepted_severities': ['critical'],
                        }
                    },
                }
            }), encoding='utf-8')
            (root / 'data' / 'run-history.jsonl').write_text(json.dumps({'fixture_name': 'greeting_test', 'rolled_back': True, 'regressed_count': 1}) + '\n', encoding='utf-8')

            from skill_auto_improver.operating_memory import OperatingMemory
            memory_context = OperatingMemory(root).load_context()
            report = self.engine.generate_proposals([self._failed('greeting_test')], operating_memory=memory_context)
            instruction = report.proposals_by_type('instruction')[0]
            artifact = report.proposals_by_type('artifact')[0]
            test_case = report.proposals_by_type('test_case')[0]
            self.assertIn('Memory hints', instruction.description)
            self.assertGreaterEqual(instruction.confidence, 0.95)
            self.assertEqual(instruction.severity, 'critical')
            self.assertEqual(test_case.severity, 'warning')
            self.assertEqual(report.proposals[0].type, 'instruction')
            self.assertIn('keep salutations formal', instruction.content['memory_hints'])
            self.assertIn('do not say hey', instruction.content['memory_hints'])
            self.assertEqual(instruction.content['memory_bias']['fixture_profile']['policy']['min_confidence'], 0.95)
            self.assertEqual(artifact.content['target_path'], 'references/auto-improver/greeting_test.md')

    def test_regression_prone_fixture_is_sorted_ahead_of_non_regression_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scaffold_operating_memory(root)
            (root / 'data' / 'run-history.jsonl').write_text(
                json.dumps({'fixture_name': 'greeting_test', 'rolled_back': True, 'regressed_count': 1}) + '\n',
                encoding='utf-8',
            )
            from skill_auto_improver.operating_memory import OperatingMemory
            memory_context = OperatingMemory(root).load_context()
            report = self.engine.generate_proposals(
                [self._failed('other_test'), self._failed('greeting_test')],
                operating_memory=memory_context,
            )
            self.assertEqual(report.proposals[0].fixture_name, 'greeting_test')

    def test_historically_protected_fixture_prioritizes_test_case_before_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scaffold_operating_memory(root)
            promotion_state = {
                'current': None,
                'history': [
                    {'timestamp': '2026-03-21T00:00:00+00:00', 'trial': {'after_eval': {'results': [{'fixture_name': 'greeting_test', 'passed': True}]}}},
                    {'timestamp': '2026-03-22T00:00:00+00:00', 'trial': {'after_eval': {'results': [{'fixture_name': 'greeting_test', 'passed': True}]}}},
                ],
            }
            (root / 'data' / 'promotion.json').write_text(json.dumps(promotion_state), encoding='utf-8')
            from skill_auto_improver.operating_memory import OperatingMemory
            memory_context = OperatingMemory(root).load_context()
            report = self.engine.generate_proposals([self._failed('greeting_test')], operating_memory=memory_context)
            ordered_types = [proposal.type for proposal in report.proposals]
            self.assertEqual(ordered_types[:2], ['test_case', 'artifact'])
            self.assertIn('historically_protected', report.proposals[0].content['memory_bias']['promotion_profile'])

    def test_structure_aware_artifact_prefers_existing_docs_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scaffold_operating_memory(root)
            (root / 'docs').mkdir()
            report = self.engine.generate_proposals([self._failed('greeting_test')], skill_path=root)
            artifact = report.proposals_by_type('artifact')[0]
            self.assertEqual(artifact.content['target_path'], 'docs/auto-improver/greeting_test.md')
            self.assertEqual(artifact.content['format'], 'markdown_append')
            self.assertIn('docs', artifact.content['structure_reason'])
            self.assertEqual(report.memory_context['skill_profile']['preferred_artifact_dir'], 'docs/auto-improver')

    def test_structure_aware_artifact_prefers_checklist_when_skill_has_checklists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scaffold_operating_memory(root)
            (root / 'checklists').mkdir()
            report = self.engine.generate_proposals([self._failed('greeting_test')], skill_path=root)
            artifact = report.proposals_by_type('artifact')[0]
            self.assertEqual(artifact.content['target_path'], 'checklists/auto-improver/greeting_test.md')
            self.assertEqual(artifact.content['format'], 'markdown_checklist')
            self.assertIn('- [ ] Protect fixture `greeting_test`', artifact.content['body'])


class ProposalIntegrationTests(unittest.TestCase):
    def test_evaluator_failures_to_proposals(self):
        from skill_auto_improver.evaluator import GoldenEvaluator

        fixtures = [
            GoldenFixture(name="greeting_test", input_data={"name": "Alice"}, expected_output={"greeting": "Hello, Alice!"}),
            GoldenFixture(name="math_test", input_data={"a": 2, "b": 3}, expected_output={"sum": 5, "product": 6}),
        ]
        actual_outputs = {
            "greeting_test": {"greeting": "Hi, Alice"},
            "math_test": {"sum": 5},
        }

        evaluator = GoldenEvaluator(fixtures)
        eval_report = evaluator.evaluate_all(actual_outputs)
        failed_results = [r for r in eval_report.results if not r.passed]
        proposal_report = ProposalEngine().generate_proposals(failed_results)

        self.assertEqual(proposal_report.total_failures, 2)
        self.assertGreater(proposal_report.total_proposals, 0)
        self.assertGreater(len(proposal_report.proposals_by_type("instruction")), 0)


if __name__ == "__main__":
    unittest.main()
