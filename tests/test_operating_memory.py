from pathlib import Path
import json

from skill_auto_improver.operating_memory import scaffold_operating_memory, OperatingMemory


def test_scaffold_operating_memory_creates_files(tmp_path: Path) -> None:
    result = scaffold_operating_memory(tmp_path)

    assert (tmp_path / 'doctrine.md').exists()
    assert (tmp_path / 'lessons.md').exists()
    assert (tmp_path / 'todo.md').exists()
    assert (tmp_path / 'gotchas.md').exists()
    assert (tmp_path / 'verification.md').exists()
    assert (tmp_path / 'data' / 'preferences.json').exists()
    assert (tmp_path / 'data' / 'run-history.jsonl').exists()
    assert (tmp_path / 'data' / 'feedback.log').exists()
    assert 'doctrine.md' in result['created']


def test_scaffold_operating_memory_preserves_existing_without_force(tmp_path: Path) -> None:
    (tmp_path / 'doctrine.md').write_text('custom', encoding='utf-8')
    scaffold_operating_memory(tmp_path)
    assert (tmp_path / 'doctrine.md').read_text(encoding='utf-8') == 'custom'


def test_scaffold_operating_memory_overwrites_with_force(tmp_path: Path) -> None:
    (tmp_path / 'doctrine.md').write_text('custom', encoding='utf-8')
    scaffold_operating_memory(tmp_path, force=True)
    assert 'Plan Node Default' in (tmp_path / 'doctrine.md').read_text(encoding='utf-8')
    prefs = json.loads((tmp_path / 'data' / 'preferences.json').read_text(encoding='utf-8'))
    assert 'style' in prefs
    assert 'proposal' in prefs


def test_operating_memory_load_context_merges_preferences_and_history(tmp_path: Path) -> None:
    scaffold_operating_memory(tmp_path)
    (tmp_path / 'lessons.md').write_text(
        '# lessons.md\n\n## Entries\n- Date: 2026-03-21\n- Pattern: keep greeting_test formal\n- Rule: prefer formal greeting wording\n- Example: greeting_test expects Hello, Alice!\n',
        encoding='utf-8',
    )
    (tmp_path / 'gotchas.md').write_text(
        '# gotchas.md\n\n## Gotchas\n- Failure: greeting_test regressed before\n- Trigger: a casual greeting slipped in\n- Prevention: avoid casual greeting phrasing\n',
        encoding='utf-8',
    )
    (tmp_path / 'data' / 'preferences.json').write_text(json.dumps({
        'proposal': {
            'boost_terms': ['formal greeting'],
            'avoid_terms': ['casual greeting'],
            'prefer_types': ['instruction'],
            'min_confidence': 0.91,
            'accepted_severities': ['warning', 'critical'],
        }
    }), encoding='utf-8')
    (tmp_path / 'data' / 'run-history.jsonl').write_text(
        json.dumps({'fixture_name': 'greeting_test', 'accepted': False, 'rolled_back': True, 'regressed_count': 1, 'recovered_count': 0}) + '\n',
        encoding='utf-8',
    )

    memory = OperatingMemory(tmp_path)
    context = memory.load_context()

    assert 'formal greeting' in context['proposal_hints']['boost_terms']
    assert 'casual greeting' in context['proposal_hints']['avoid_terms']
    assert 'instruction' in context['proposal_hints']['prefer_types']
    assert 'greeting_test' in context['proposal_hints']['boosted_fixtures']
    assert context['policy']['min_confidence'] == 0.91
    assert context['policy']['accepted_severities'] == ['warning', 'critical']
    profile = context['proposal_hints']['fixture_profiles']['greeting_test']
    assert profile['regression_prone'] is True
    assert any('prefer formal greeting wording' in item for item in profile['boost_terms'])
    assert any('avoid casual greeting phrasing' in item for item in profile['avoid_terms'])
    assert profile['history']['rollback_count'] == 1


def test_operating_memory_load_context_builds_fixture_specific_policy_profiles(tmp_path: Path) -> None:
    scaffold_operating_memory(tmp_path)
    (tmp_path / 'data' / 'preferences.json').write_text(json.dumps({
        'proposal': {
            'fixture_policies': {
                'greeting_test': {
                    'boost_terms': ['keep salutations formal'],
                    'avoid_terms': ['never say hey there'],
                    'prefer_types': ['instruction'],
                    'min_confidence': 0.95,
                    'accepted_severities': ['critical'],
                }
            }
        }
    }), encoding='utf-8')

    context = OperatingMemory(tmp_path).load_context()
    profile = context['proposal_hints']['fixture_profiles']['greeting_test']
    assert profile['policy']['min_confidence'] == 0.95
    assert profile['policy']['accepted_severities'] == ['critical']
    assert profile['prefer_types'] == ['instruction']
    assert 'keep salutations formal' in profile['boost_terms']
    assert 'never say hey there' in profile['avoid_terms']
    assert context['policy']['fixture_policies']['greeting_test']['min_confidence'] == 0.95


def test_operating_memory_record_trial_promotes_last_accepted_state(tmp_path: Path) -> None:
    memory = OperatingMemory(tmp_path)
    result = memory.record_trial(
        result={
            'accepted': True,
            'rolled_back': False,
            'rollback_count': 0,
            'acceptance_reason': 'safe improvement',
            'before_eval': {'results': [{'fixture_name': 'greeting_test', 'passed': False}]},
            'after_eval': {'results': [{'fixture_name': 'greeting_test', 'passed': True}]},
            'apply': {'applied_count': 1, 'skipped_count': 0},
            'ab': {'pass_rate_delta': 1.0, 'recovered_count': 1, 'regressed_count': 0},
            'promotion_guard': {'is_safe': True, 'regressed_from_promoted': []},
        },
        proposals=[{'type': 'instruction', 'fixture_name': 'greeting_test'}],
        policy={'min_confidence': 0.9},
    )

    promotion_path = tmp_path / 'data' / 'promotion.json'
    promotion = json.loads(promotion_path.read_text(encoding='utf-8'))
    assert result['promotion']['promoted'] is True
    assert promotion['current']['acceptance_reason'] == 'safe improvement'
    assert promotion['current']['trial']['after_eval']['results'][0]['fixture_name'] == 'greeting_test'
    assert len(promotion['history']) == 1


def test_operating_memory_evaluate_promotion_guard_detects_regression_from_promoted_baseline(tmp_path: Path) -> None:
    memory = OperatingMemory(tmp_path)
    memory.record_trial(
        result={
            'accepted': True,
            'rolled_back': False,
            'rollback_count': 0,
            'acceptance_reason': 'safe improvement',
            'before_eval': {'results': [{'fixture_name': 'greeting_test', 'passed': False}]},
            'after_eval': {'results': [{'fixture_name': 'greeting_test', 'passed': True}]},
            'apply': {'applied_count': 1, 'skipped_count': 0},
            'ab': {'pass_rate_delta': 1.0, 'recovered_count': 1, 'regressed_count': 0},
            'promotion_guard': {'is_safe': True, 'regressed_from_promoted': []},
        },
        proposals=[{'type': 'instruction', 'fixture_name': 'greeting_test'}],
        policy={'min_confidence': 0.9},
    )

    guard = memory.evaluate_promotion_guard(
        before_eval={'results': [{'fixture_name': 'greeting_test', 'passed': True}]},
        after_eval={'results': [{'fixture_name': 'greeting_test', 'passed': False}]},
    )
    assert guard['has_promoted_baseline'] is True
    assert guard['is_safe'] is False
    assert guard['regressed_from_promoted'] == ['greeting_test']
    assert guard['degraded_vs_promoted_baseline'] == ['greeting_test']


def test_operating_memory_evaluate_promotion_guard_tracks_history_stable_fixtures(tmp_path: Path) -> None:
    memory = OperatingMemory(tmp_path)
    for _ in range(2):
        memory.record_trial(
            result={
                'accepted': True,
                'rolled_back': False,
                'rollback_count': 0,
                'acceptance_reason': 'safe improvement',
                'before_eval': {'results': [{'fixture_name': 'greeting_test', 'passed': False}, {'fixture_name': 'tone_test', 'passed': False}]},
                'after_eval': {'results': [{'fixture_name': 'greeting_test', 'passed': True}, {'fixture_name': 'tone_test', 'passed': True}]},
                'apply': {'applied_count': 1, 'skipped_count': 0},
                'ab': {'pass_rate_delta': 1.0, 'recovered_count': 1, 'regressed_count': 0},
                'promotion_guard': {'is_safe': True, 'regressed_from_promoted': []},
            },
            proposals=[{'type': 'instruction', 'fixture_name': 'greeting_test'}],
            policy={'min_confidence': 0.9},
        )

    guard = memory.evaluate_promotion_guard(
        before_eval={'results': [{'fixture_name': 'greeting_test', 'passed': True}, {'fixture_name': 'tone_test', 'passed': True}]},
        after_eval={'results': [{'fixture_name': 'greeting_test', 'passed': True}, {'fixture_name': 'tone_test', 'passed': False}]},
        history_window=5,
        min_promotions_for_fixture_guard=2,
    )
    assert guard['promotion_history_depth'] == 2
    assert guard['promotion_pass_counts']['tone_test'] == 2
    assert 'tone_test' in guard['historically_protected_fixtures']
    assert guard['regressed_from_promotion_history'] == ['tone_test']
    assert guard['degraded_vs_promotion_history'] == ['tone_test']
    assert guard['is_safe'] is False


def test_operating_memory_record_trial_logs_history_and_updates_review_files(tmp_path: Path) -> None:
    memory = OperatingMemory(tmp_path)
    result = memory.record_trial(
        result={
            'accepted': True,
            'rolled_back': False,
            'rollback_count': 0,
            'apply': {'applied_count': 1, 'skipped_count': 0},
            'ab': {'pass_rate_delta': 1.0, 'recovered_count': 1, 'regressed_count': 0},
        },
        proposals=[{'type': 'instruction', 'fixture_name': 'greeting_test'}],
        policy={'min_confidence': 0.9},
    )

    history_lines = (tmp_path / 'data' / 'run-history.jsonl').read_text(encoding='utf-8').strip().splitlines()
    assert len(history_lines) == 1
    entry = json.loads(history_lines[0])
    assert entry['kind'] == 'safe_patch_trial'
    assert entry['accepted'] is True
    assert entry['proposal_count'] == 1
    assert entry['fixture_names'] == ['greeting_test']
    assert 'Trial' in (tmp_path / 'verification.md').read_text(encoding='utf-8')
    assert 'Trial accepted' in (tmp_path / 'todo.md').read_text(encoding='utf-8')
    assert 'accepted patch recovered' in (tmp_path / 'lessons.md').read_text(encoding='utf-8')
    assert result['history_path'].endswith('data/run-history.jsonl')
    assert result['context']['history']['accepted_count'] >= 1


def test_operating_memory_record_trial_logs_gotcha_on_regression(tmp_path: Path) -> None:
    scaffold_operating_memory(tmp_path)
    memory = OperatingMemory(tmp_path)
    memory.record_trial(
        result={
            'accepted': False,
            'rolled_back': True,
            'rollback_count': 1,
            'apply': {'applied_count': 1, 'skipped_count': 0},
            'ab': {'pass_rate_delta': -1.0, 'recovered_count': 0, 'regressed_count': 1},
        },
        proposals=[{'type': 'instruction', 'fixture_name': 'greeting_test'}],
        policy={'rollback_on_regression': True},
    )

    gotchas = (tmp_path / 'gotchas.md').read_text(encoding='utf-8')
    assert 'proposed patch regressed an already-working behavior' in gotchas
    assert 'keep rollback enabled' in gotchas
