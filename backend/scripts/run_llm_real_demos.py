"""Run the opt-in real-provider demos and save readable DB evidence."""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
env = os.environ.copy()
env["CARMINE_RUN_REAL_LLM_DEMOS"] = "1"
command = [sys.executable, "-m", "pytest", "tests/test_llm_real_demo.py", "-q", "-s"]
raise SystemExit(subprocess.run(command, cwd=ROOT, env=env).returncode)
