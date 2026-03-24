#!/usr/bin/env python3
"""
Wrapper script to run nightly orchestrator with proper path setup.
"""
import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

# Now run it
from skill_auto_improver.nightly_orchestrator import NightlyOrchestratorRunner

if __name__ == "__main__":
    workspace_root = Path.home() / ".openclaw" / "workspace"
    runner = NightlyOrchestratorRunner(str(workspace_root))
    success = runner.run()
    
    if success:
        print("\n✅ Nightly orchestration completed successfully")
        sys.exit(0)
    else:
        print("\n❌ Nightly orchestration failed")
        sys.exit(1)
