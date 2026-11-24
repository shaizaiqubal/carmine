"""Run the two quota-free LLM layer demos and save readable DB evidence."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
command = [sys.executable, "-m", "pytest", "tests/test_llm_demo.py", "-q", "-s"]
raise SystemExit(subprocess.run(command, cwd=ROOT).returncode)
