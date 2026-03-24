"""
Multi-skill orchestration demo with shared brain learning.

Demonstrates:
1. Initializing a shared brain for cross-skill learning
2. Running improvement trials on multiple skills
3. Recording promotion wisdom and regression patterns
4. Using learned insights from one skill to improve another
5. Tracking skill mastery metrics across the system
"""

from pathlib import Path
import json
import tempfile

from skill_auto_improver.shared_brain import SharedBrain
from skill_auto_improver.orchestrator import MultiSkillOrchestrator, SkillTrialConfig


def demo_basic_brain():
    """Demonstrate basic shared brain operations."""
    print("\n=== DEMO 1: Basic Shared Brain ===\n")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        brain = SharedBrain(Path(temp_dir) / "brain")
        
        # Record a successful promotion
        print("1. Recording a promotion wisdom entry...")
        wisdom = brain.record_promotion(
            fixture_name="greeting_formal_test",
            skill_name="weather-brief",
            proposal_types=["test_case", "instruction"],
            reason="100% recovery with zero regressions, all fixtures pass",
            confidence=0.92,
            shared_lessons=[
                "Always pair test_case proposal before instruction for greeting fixtures",
                "Formal greeting format should use 'Hello' not 'Hi'",
            ],
        )
        print(f"   ✓ Recorded: {wisdom.fixture_name} in {', '.join(wisdom.skills_successful)}")
        print(f"   ✓ Confidence: {wisdom.confidence}, Promotion count: {wisdom.promotion_count}")
        
        # Record a regression pattern
        print("\n2. Recording a regression pattern...")
        pattern = brain.record_regression(
            pattern_name="instruction_without_test_case",
            skill_name="weather-brief",
            trigger="Submitted instruction proposal without accompanying test_case",
            fix_strategy="Enforce fixture-level policy: require test_case for historically protected fixtures",
            severity="critical",
        )
        print(f"   ✓ Recorded: {pattern.pattern_name} in {', '.join(pattern.observed_in_skills)}")
        print(f"   ✓ Severity: {pattern.severity}, Occurrences: {pattern.occurrence_count}")
        
        # Add a fixture to the library
        print("\n3. Adding a fixture to the shared library...")
        entry = brain.add_fixture_to_library(
            fixture_pattern_name="greeting_format_check",
            fixture_template={
                "name": "greeting_formal_test",
                "input_data": {"recipient": "Alice"},
                "expected_output": {"greeting": "Hello, Alice!"},
            },
            expected_behavior="Generate formal greeting with 'Hello' prefix",
            successful_skills=["weather-brief"],
        )
        print(f"   ✓ Added: {entry.fixture_pattern_name}")
        print(f"   ✓ Successful in: {', '.join(entry.successful_skills)}")
        
        # Create skill mastery
        print("\n4. Creating skill mastery record...")
        mastery = brain.get_or_create_skill_mastery("weather-brief", skill_type="forecast")
        brain.update_skill_mastery(
            "weather-brief",
            total_trials=10,
            successful_promotions=8,
            most_effective_proposal_types=["test_case", "instruction"],
            average_proposal_confidence=0.88,
        )
        print(f"   ✓ Created: {mastery.skill_name} (type: {mastery.skill_type})")
        print(f"   ✓ Success rate: {8}/{10} trials successful")
        
        # Get brain summary
        print("\n5. Brain summary:")
        summary = brain.summarize_for_skill("weather-brief")
        print(f"   ✓ Applicable directives: {len(summary['applicable_directives'])}")
        print(f"   ✓ Promotion wisdom entries: {summary['total_promotions_across_system']}")
        print(f"   ✓ Skill mastery: {summary['mastery']['skill_name']} ({summary['mastery']['total_trials']} trials)")


def demo_cross_skill_learning():
    """Demonstrate cross-skill learning with promotion wisdom."""
    print("\n=== DEMO 2: Cross-Skill Learning ===\n")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        brain = SharedBrain(Path(temp_dir) / "brain")
        
        # Skill A succeeds with a greeting fixture
        print("1. Skill A (weather-brief) successfully promotes greeting fixture...")
        wisdom_a = brain.record_promotion(
            fixture_name="greeting_format",
            skill_name="weather-brief",
            proposal_types=["test_case", "instruction"],
            reason="Recovery from missing formal greeting",
            confidence=0.90,
            shared_lessons=["Formal greeting must say 'Hello', not 'Hi'"],
        )
        print(f"   ✓ Promotion recorded for: {wisdom_a.fixture_name}")
        
        # Skill B encounters the same fixture
        print("\n2. Skill B (kiro) encounters similar greeting fixture...")
        wisdom_b = brain.get_promotion_wisdom_for_fixture("greeting_format")
        if wisdom_b:
            print(f"   ✓ Found promotion wisdom from {len(wisdom_b[0].skills_successful)} skill(s)")
            print(f"   ✓ Proven proposal sequence: {' → '.join(wisdom_b[0].proposal_type_sequence)}")
            print(f"   ✓ Shared lessons: {wisdom_b[0].shared_lessons}")
        
        # Verify merging behavior
        print("\n3. Skill B promotes the same fixture...")
        wisdom_merged = brain.record_promotion(
            fixture_name="greeting_format",
            skill_name="kiro",
            proposal_types=["test_case", "instruction"],
            reason="Recovery from missing formal greeting",
            confidence=0.88,
        )
        print(f"   ✓ Merged with existing wisdom")
        print(f"   ✓ Now successful in: {', '.join(wisdom_merged.skills_successful)}")
        print(f"   ✓ Total promotion count: {wisdom_merged.promotion_count}")


def demo_regression_prevention():
    """Demonstrate regression pattern sharing across skills."""
    print("\n=== DEMO 3: Regression Prevention ===\n")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        brain = SharedBrain(Path(temp_dir) / "brain")
        
        # Skill A encounters a regression
        print("1. Skill A encounters regression: instruction-only proposal breaks tests...")
        pattern = brain.record_regression(
            pattern_name="instruction_only_breaks_tests",
            skill_name="skill_a",
            trigger="Instruction proposal without test_case caused 3 fixtures to fail",
            fix_strategy="Always require test_case proposals for historically protected fixtures",
            severity="critical",
        )
        print(f"   ✓ Pattern recorded: {pattern.pattern_name}")
        print(f"   ✓ Prevention: {pattern.fix_strategy}")
        
        # Same pattern occurs in Skill B
        print("\n2. Skill B encounters the same regression pattern...")
        pattern_again = brain.record_regression(
            pattern_name="instruction_only_breaks_tests",
            skill_name="skill_b",
            trigger="Same issue: instruction-without-test",
            fix_strategy="Always require test_case proposals for historically protected fixtures",
        )
        print(f"   ✓ Pattern already known!")
        print(f"   ✓ Observed in skills: {', '.join(pattern_again.observed_in_skills)}")
        print(f"   ✓ Total occurrences: {pattern_again.occurrence_count}")
        
        # Retrieve patterns for awareness
        print("\n3. Pre-trial context for Skill C...")
        patterns = brain.get_regression_patterns_for_skill("skill_c")
        print(f"   ✓ Warning: {len(brain.regression_patterns)} known regression pattern(s)")
        for p in brain.regression_patterns.values():
            print(f"   ✓ {p.pattern_name}: observed in {len(p.observed_in_skills)} skill(s)")


def demo_orchestrator():
    """Demonstrate multi-skill orchestrator."""
    print("\n=== DEMO 4: Multi-Skill Orchestrator ===\n")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        brain_dir = Path(temp_dir) / "brain"
        
        # Initialize orchestrator
        print("1. Initializing orchestrator with shared brain...")
        orchestrator = MultiSkillOrchestrator(brain_dir=brain_dir)
        print(f"   ✓ Orchestrator created with brain at {brain_dir}")
        
        # Define skill configurations
        print("\n2. Defining skill trial configurations...")
        configs = [
            SkillTrialConfig(
                skill_path="/skills/weather-brief",
                skill_name="weather-brief",
                skill_type="forecast",
                min_confidence=0.85,
                enabled=True,
            ),
            SkillTrialConfig(
                skill_path="/skills/kiro",
                skill_name="kiro",
                skill_type="mobile_app",
                min_confidence=0.80,
                enabled=True,
            ),
        ]
        print(f"   ✓ Configured {len(configs)} skill(s)")
        
        # Check brain state before orchestration
        print("\n3. Brain state before orchestration:")
        summary = orchestrator.get_brain_summary()
        print(f"   ✓ Core directives: {summary['core_directives']}")
        print(f"   ✓ Promotion wisdom: {summary['promotion_wisdom_entries']}")
        print(f"   ✓ Regression patterns: {summary['regression_patterns']}")
        
        # Get pre-trial context for first skill
        print("\n4. Pre-trial context for weather-brief:")
        context = orchestrator.get_skill_context_for_trial("weather-brief")
        print(f"   ✓ Applicable directives: {len(context['applicable_directives'])}")
        print(f"   ✓ Regression patterns to watch: {len(context['regression_patterns_to_watch'])}")
        
        # Run orchestration (will have no actual trials since paths don't exist)
        print("\n5. Running orchestration (dry-run, paths don't exist):")
        run = orchestrator.run_orchestration(
            skill_configs=configs,
            logs_dir=Path(temp_dir) / "logs",
        )
        print(f"   ✓ Orchestration run ID: {run.run_id}")
        print(f"   ✓ Total skills configured: {run.total_skills}")
        print(f"   ✓ Started at: {run.started_at}")
        print(f"   ✓ Finished at: {run.finished_at}")


def demo_persistence():
    """Demonstrate shared brain persistence across sessions."""
    print("\n=== DEMO 5: Brain Persistence ===\n")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        brain_dir = Path(temp_dir) / "brain"
        
        # Session 1: Create and populate brain
        print("1. Session 1: Creating and populating brain...")
        brain1 = SharedBrain(brain_dir)
        brain1.record_promotion(
            fixture_name="test_1",
            skill_name="skill_a",
            proposal_types=["instruction"],
            reason="Good",
            confidence=0.85,
        )
        brain1.update_skill_mastery("skill_a", total_trials=5, successful_promotions=4)
        print(f"   ✓ Recorded 1 promotion")
        print(f"   ✓ Created mastery for skill_a")
        
        # Session 2: Load brain, verify persistence
        print("\n2. Session 2: Loading brain in new instance...")
        brain2 = SharedBrain(brain_dir)
        
        wisdom = brain2.get_promotion_wisdom_for_fixture("test_1")
        mastery = brain2.get_skill_mastery("skill_a")
        
        print(f"   ✓ Loaded promotion wisdom: {len(wisdom)} entries")
        print(f"   ✓ Loaded skill mastery: {mastery.skill_name} ({mastery.total_trials} trials)")
        
        # Session 3: Add more data, verify accumulation
        print("\n3. Session 3: Adding more data...")
        brain2.record_promotion(
            fixture_name="test_2",
            skill_name="skill_b",
            proposal_types=["test_case"],
            reason="Good",
            confidence=0.90,
        )
        
        brain3 = SharedBrain(brain_dir)
        all_wisdom = brain3.promotion_wisdom
        print(f"   ✓ Total promotions across sessions: {len(all_wisdom)}")
        
        # List all memory blocks
        print("\n4. Brain files persisted:")
        for file in brain_dir.glob("*.json"):
            size = file.stat().st_size
            print(f"   ✓ {file.name}: {size} bytes")


if __name__ == "__main__":
    print("=" * 60)
    print("Multi-Skill Orchestration Demo")
    print("=" * 60)
    
    demo_basic_brain()
    demo_cross_skill_learning()
    demo_regression_prevention()
    demo_orchestrator()
    demo_persistence()
    
    print("\n" + "=" * 60)
    print("Demo complete! See MULTI_SKILL_GUIDE.md for full documentation.")
    print("=" * 60)
