# Skill Auto-Improver

> 🤖 Autonomous improvement system for AgentSkills via structured observe → inspect → amend → evaluate loops.

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![Tests Passing](https://img.shields.io/badge/tests-126%2F126-green)](tests/)
[![License MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-production--ready-brightgreen)](#)

Skill Auto-Improver enables **continuous, autonomous improvement** of AgentSkills with:

- 🔄 **Closed-Loop Optimization** — Observe failures → Inspect root causes → Amend skills → Evaluate improvements
- 🧠 **Cross-Skill Learning** — Share lessons across skills via structured memory blocks
- 🛡️ **Safety-First** — Built-in rollback, A/B evaluation, and regression detection
- 📊 **Operational Excellence** — Nightly orchestration with Telegram summaries and automated backups
- 📚 **Golden Test Fixtures** — Compare against expected outputs to detect improvements
- 💡 **Smart Proposals** — Generate actionable patches (instructions, test cases, diagnostics)

Perfect for maintaining large skill ecosystems where manual optimization becomes prohibitive.

---

## 🔒 Privacy & Local-First Architecture

**Core principle:** Skill Auto-Improver is **100% local and auditable**.

### What stays on your machine:
- ✅ All optimization logic (observe, inspect, amend, evaluate)
- ✅ All skill code and fixtures
- ✅ All learned memory and promotion history
- ✅ Full source code (you can review every line)
- ✅ No external API calls from the library itself

### Optional: External integrations
The **operational layer** (nightly crons, summaries, backups) can optionally send to external services, but:
- ⚙️ This is a **deployment choice**, not built into the library
- ⚙️ Telegram delivery is managed by OpenClaw's cron system, not by Skill Auto-Improver
- ⚙️ You can run Skill Auto-Improver completely offline if desired
- ⚙️ All data sent to external services is your choice (backups, summaries, etc.)

### Data you control:
- **Nightly backups** — Optional; sent to Telegram only if you configure it
- **Morning summaries** — Optional; delivered via OpenClaw crons only if you enable them
- **Run history** — Local JSONL file; never leaves your machine unless you explicitly send it

**Bottom line:** This is a local optimization engine. The deployment scripts show how we use it with Telegram for convenience, but the library itself has zero external dependencies and zero external calls.

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/skill-auto-improver.git
cd skill-auto-improver

# Optional: Create virtual environment
python -m venv venv
source venv/bin/activate

# Install (no external dependencies!)
pip install -e .
```

### 5-Minute Demo

```python
from skill_auto_improver import SkillAutoImprover

# Point to a skill directory
improver = SkillAutoImprover(skill_path="~/.openclaw/workspace/skills/weather-brief")

# Run a complete optimization loop
trace = improver.run()

# Check what was learned
print(trace.status)           # "success" or "failed"
print(trace.metadata)         # Summary metrics
for step in trace.steps:
    print(f"{step.stage}: {step.status}")
```

See [examples/](examples/) for more detailed demos.

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Skill Auto-Improver                          │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │        Operational Layer (Nightly Crons)                │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │  🌙 Nightly Orchestrator (2 AM PST)                     │  │
│  │     • Run trials across 5+ skills                       │  │
│  │     • Log to run-history.jsonl                          │  │
│  │     • Prepare morning-summary.json                      │  │
│  │                                                          │  │
│  │  📤 Morning Summary Sender (7 AM PST)                   │  │
│  │     • Format and send Telegram brief                    │  │
│  │     • Archive summaries with metadata                   │  │
│  │                                                          │  │
│  │  💾 Nightly Backup (midnight PST)                       │  │
│  │     • Zip entire workspace                              │  │
│  │     • Send via Telegram (with retention)                │  │
│  │     • Save metadata for recovery                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ▲                                   │
│                              │                                   │
│  ┌──────────────────────────┼───────────────────────────────┐  │
│  │    Multi-Skill Layer     │                               │  │
│  ├──────────────────────────┼───────────────────────────────┤  │
│  │  MultiSkillOrchestrator──┴─ Coordinates 5+ skills       │  │
│  │  SkillTrialConfig        Defines per-skill parameters   │  │
│  │  OrchestrationRun        Captures cross-skill results   │  │
│  └────────────────────────────────────────────────────────┬─┘  │
│                                                            │     │
│  ┌───────────────────────────────────────────────────────┼──┐  │
│  │        Shared Brain (Cross-Skill Learning)           │  │  │
│  ├───────────────────────────────────────────────────────┼──┤  │
│  │  📖 Core Directives        (System rules)             │  │  │
│  │  🏆 Promotion Wisdom       (Success patterns)         │  │  │
│  │  ⚠️  Regression Patterns   (Failure modes)            │  │  │
│  │  📦 Fixture Library        (Reusable patterns)        │  │  │
│  │  🎯 Skill Mastery          (Per-skill insights)       │  │  │
│  └───────────────────────────────────────────────────────┘─┬┘  │
│                                                              │   │
│  ┌──────────────────────────────────────────────────────────┴┐  │
│  │          Core Pipeline (Single Skill)                     │  │
│  ├─────────────────────────────────────────────────────────┬─┤  │
│  │  [1] Observe                                            │ │  │
│  │      └─ Load test fixtures, run skill                  │ │  │
│  │  [2] Inspect                                            │ │  │
│  │      └─ Evaluate outputs vs expected (A/B)             │ │  │
│  │  [3] Amend                                              │ │  │
│  │      └─ Generate proposals (instruction/test/reasoning)│ │  │
│  │  [4] Evaluate + Rollback                                │ │  │
│  │      └─ Apply patches → test → auto-rollback if broken │ │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Core Pipeline Flow

```
OBSERVE
  Input: Skill path, test fixtures
  Output: Before-eval report (pass_rate, failures)
    ▼
INSPECT
  Input: Before-eval failures
  Output: A/B comparison showing what changed
    ▼
AMEND
  Input: Failed tests (deltas)
  Output: Patch proposals (instructions, test cases, reasoning)
    ▼
EVALUATE + ROLLBACK
  Input: Proposals to apply
  Process:
    1. Apply accepted proposals
    2. Re-evaluate against fixtures
    3. Compare before/after (A/B)
    4. Auto-rollback if regressions detected
  Output: Applied patches + improvement metrics
```

### Module Structure

```
skill_auto_improver/
├── loop.py                    # Core pipeline runner
├── evaluator.py              # Golden fixture evaluation
├── proposer.py               # Amendment proposal generator
├── ab_evaluator.py           # Regression detection
├── applier.py                # Patch application & rollback
├── operating_memory.py       # Trial state tracking
├── shared_brain.py           # Cross-skill memory blocks
├── orchestrator.py           # Multi-skill coordination
├── nightly_orchestrator.py   # Cron: Run nightly trials
├── morning_summary_sender.py # Cron: Send Telegram brief
├── nightly_backup.py         # Cron: Backup workspace
├── logger.py                 # Structured logging
├── cli.py                    # Command-line interface
└── models.py                 # Data classes & schemas
```

---

## Features

### 🔄 Closed-Loop Optimization

Run complete improve-evaluate-rollback cycles automatically:

```python
# Single-skill trial with full safety
improver = SkillAutoImprover(skill_path="path/to/skill")
trace = improver.run(
    stage_order=["evaluate", "amend", "patch_trial"]
)

# Check if patch was safe
if trace.metadata.get("rolled_back"):
    print("Patch caused regressions, rolled back")
else:
    print(f"Improvement: {trace.metadata['pass_rate_delta']:+.1%}")
```

### 🧠 Shared Brain for Cross-Skill Learning

Learn from one skill to improve others:

```python
from skill_auto_improver.shared_brain import SharedBrain
from skill_auto_improver.orchestrator import MultiSkillOrchestrator

# Initialize shared brain for all skills
brain = SharedBrain(root="~/.openclaw/workspace/skill-auto-improver/shared_brain")

# Create orchestrator
orchestrator = MultiSkillOrchestrator(brain)

# Run trials on multiple skills
for skill_name in ["morning-brief", "weather-brief", "kiro-dev-assistant"]:
    config = SkillTrialConfig(
        skill_name=skill_name,
        skill_path=f"~/.openclaw/workspace/skills/{skill_name}",
        use_shared_brain=True
    )
    result = orchestrator.run_orchestration([config])
    
# Brain learns:
# - Which proposal types work best per skill type
# - Common regression patterns to avoid
# - Reusable fixture patterns
# - Cross-skill insights
```

### 🛡️ Safety-First Design

Built-in protection against breaking changes:

```python
# A/B evaluation detects regressions
before = evaluator.evaluate_snapshot(old_output)  # 85% pass
after = evaluator.evaluate_snapshot(new_output)   # 90% pass

ab_report = ab_evaluator.compare(before, after)
print(f"Safe: {ab_report.is_safe}")      # True (no regressions)
print(f"Recovered: {ab_report.recovered_count}")  # 5 tests fixed
print(f"Regressed: {ab_report.regressed_count}")  # 0 tests broken
```

### 📊 Operational Excellence

Three nightly crons keep the system running:

```bash
# Nightly Orchestrator (2 AM PST)
# - Runs trials on all 5 monitored skills
# - Logs to run-history.jsonl
# - Prepares morning-summary.json

# Morning Summary Sender (7 AM PST)
# - Sends formatted brief to Telegram
# - Archives summaries with metadata

# Nightly Backup (midnight PST)
# - Zips entire workspace
# - Sends via Telegram
# - Retains last 30 backups
```

See [CRON_SETUP.md](CRON_SETUP.md) for detailed configuration.

### 📚 Golden Test Fixtures

Evaluate improvements with confidence:

```json
{
  "fixtures": [
    {
      "input": {"location": "San Francisco", "period": "today"},
      "expected_output": {
        "temperature_range": "65-75°F",
        "condition": "partly_cloudy",
        "recommendation": "Light jacket recommended"
      }
    }
  ]
}
```

### 💡 Smart Proposals

Three types of automated amendments:

| Type | Purpose | Confidence | Example |
|------|---------|------------|---------|
| **Instruction** | Rewrite SKILL.md guidance | 0.85 | "Add 'San Francisco' to geography handling" |
| **Test Case** | Add regression fixture | 0.80 | "Add fixture to prevent future location bugs" |
| **Reasoning** | Diagnostic hint | 0.90 | "Temperature parsing failing for °F symbol" |

---

## Usage Examples

### Basic Single-Skill Trial

```python
from skill_auto_improver import SkillAutoImprover

improver = SkillAutoImprover(
    skill_path="~/.openclaw/workspace/skills/weather-brief"
)

# Run observation → inspection → amendment → evaluation
trace = improver.run()

# Check results
print(f"Status: {trace.status}")
print(f"Steps: {[s.stage for s in trace.steps]}")
for step in trace.steps:
    if step.payload:
        print(f"  {step.stage}: {step.payload}")
```

### A/B Evaluation with Rollback

```python
from skill_auto_improver.ab_evaluator import ABEvaluator

# Evaluate before and after
before = evaluator.evaluate_all(skill, original_fixtures)
after = evaluator.evaluate_all(skill, patched_fixtures)

# Compare
ab = ABEvaluator()
comparison = ab.compare(before, after)

if comparison.is_safe:
    print(f"✅ Safe to deploy (+{comparison.pass_rate_delta:+.1%})")
else:
    print(f"❌ Regressions detected, rolling back")
    restore_from_backup()
```

### Multi-Skill Orchestration

```python
from skill_auto_improver.orchestrator import MultiSkillOrchestrator, SkillTrialConfig
from skill_auto_improver.shared_brain import SharedBrain

brain = SharedBrain("~/.openclaw/workspace/skill-auto-improver/shared_brain")
orchestrator = MultiSkillOrchestrator(brain)

configs = [
    SkillTrialConfig(
        skill_name="morning-brief",
        skill_path="~/.openclaw/workspace/skills/morning-brief",
        use_shared_brain=True
    ),
    SkillTrialConfig(
        skill_name="weather-brief",
        skill_path="~/.openclaw/workspace/skills/weather-brief",
        use_shared_brain=True
    ),
]

run = orchestrator.run_orchestration(configs)
print(f"Improved {run.skills_successful}/{run.skills_attempted} skills")

# Brain now contains cross-skill learnings
brain_summary = brain.summarize()
print(f"Promotion wisdom entries: {len(brain_summary['promotion_wisdom'])}")
```

See [examples/](examples/) directory for complete working examples.

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage report
pytest tests/ --cov=skill_auto_improver --cov-report=html

# Run specific test
pytest tests/test_shared_brain.py::SharedBrainTest::test_promotion_wisdom_recording -v

# Run examples
python examples/multi_skill_orchestration_demo.py
```

**Test Suite:** 126 tests, all passing ✅

---

## API Documentation

### Core Classes

#### `SkillAutoImprover`
Main entry point for single-skill improvement loops.

```python
improver = SkillAutoImprover(skill_path, operating_memory_max=100)
trace = improver.run(stage_order=["evaluate", "amend", "patch_trial"])
```

#### `MultiSkillOrchestrator`
Coordinates improvements across multiple skills with shared brain.

```python
orchestrator = MultiSkillOrchestrator(brain)
run = orchestrator.run_orchestration(configs)
```

#### `SharedBrain`
Cross-skill memory with 5 persistent blocks.

```python
brain = SharedBrain(root)
brain.record_promotion_wisdom("instruction", "success", skills=["s1", "s2"])
brain.summarize()
```

#### `GoldenEvaluator`
Compares skill outputs against expected golden fixtures.

```python
evaluator = GoldenEvaluator(fixtures)
report = evaluator.evaluate_all(skill_outputs)
```

See [MULTI_SKILL_GUIDE.md](MULTI_SKILL_GUIDE.md) for complete API reference.

---

## Configuration

### Environment Variables

```bash
# Workspace root (optional, defaults to ~/.openclaw/workspace)
export OPENCLAW_WORKSPACE=/home/user/.openclaw/workspace

# Telegram credentials (for Telegram integration)
export TELEGRAM_BOT_TOKEN=your-bot-token
export TELEGRAM_CHAT_ID=your-chat-id
```

### Using Skill Auto-Improver Locally (No External Calls)

Want to use Skill Auto-Improver without any external integrations?

```python
from skill_auto_improver import SkillAutoImprover, SkillTrialConfig

# Point to your skill
improver = SkillAutoImprover(skill_path="/path/to/skill")

# Run optimization loop entirely locally
trace = improver.run()

# Results stay on your machine
for step in trace.steps:
    print(f"{step.stage}: {step.status}")

# Access learned memory (also local)
memory = improver.operating_memory.load_context()
print(memory.lessons)
print(memory.promotion_wisdom)
```

No Telegram, no external APIs, no cloud calls. 100% local.

### Optional: Cron Setup (With Telegram)

If you want nightly automation with Telegram summaries, see [CRON_SETUP.md](CRON_SETUP.md):

Three optional nightly jobs integrate with OpenClaw's cron system:

- **Nightly Orchestrator** (2 AM PST) — Run trials, log history
- **Morning Summary** (7 AM PST) — Send Telegram brief
- **Nightly Backup** (midnight PST) — Backup workspace

---

## Performance

- **Memory:** Keeps last 100 trials in memory (configurable)
- **Speed:** Single skill trial in 5-30 seconds (depends on fixture count)
- **Storage:** ~100 KB per run in run-history.jsonl
- **Backups:** 30-day retention (~2 GB typical)

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development setup
- Testing requirements
- Code style guidelines
- Pull request process
- Common tasks (add proposal type, memory block, cron job)

---

## Roadmap

### Near Term
- [ ] Distributed multi-node orchestration
- [ ] Proposal ranking by shared brain insights
- [ ] CLI dashboard for monitoring
- [ ] Automated confidence thresholds

### Medium Term
- [ ] Integration with version control (Git commits per patch)
- [ ] Performance analytics and trending
- [ ] Skill health reports
- [ ] Multi-language skill support (JS, Go, Rust)

### Long Term
- [ ] Multi-agent improvement coordination
- [ ] Real-time proposal streaming
- [ ] Hardware acceleration for large trial batches
- [ ] Commercial SaaS offering

See [ROADMAP.md](ROADMAP.md) for full details.

---

## Troubleshooting

### Tests Failing
```bash
# Check Python version
python --version  # Should be 3.9+

# Reinstall in dev mode
pip install -e .

# Run with verbose output
pytest tests/ -vv
```

### Cron Jobs Not Running
See [CRON_SETUP.md](CRON_SETUP.md) troubleshooting section.

### Telegram Messages Not Sending
1. Verify credentials: `echo $TELEGRAM_BOT_TOKEN $TELEGRAM_CHAT_ID`
2. Test API: `curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"`
3. Check logs: `tail ~/.openclaw/workspace/skill-auto-improver/logs/*.log`

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Citation

If you use Skill Auto-Improver in research or production, please cite:

```bibtex
@software{skill_auto_improver_2026,
  title = {Skill Auto-Improver: Autonomous Improvement of AgentSkills},
  author = {Alex},
  year = {2026},
  url = {https://github.com/yourusername/skill-auto-improver}
}
```

---

## Support

- 📖 **Documentation:** See [MULTI_SKILL_GUIDE.md](MULTI_SKILL_GUIDE.md) and [CRON_SETUP.md](CRON_SETUP.md)
- 🐛 **Bug Reports:** [GitHub Issues](https://github.com/yourusername/skill-auto-improver/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/yourusername/skill-auto-improver/discussions)
- 📧 **Email:** contact@example.com

---

**Status:** Production-ready ✅  
**Last Updated:** 2026-03-24  
**Maintainer:** Alex
