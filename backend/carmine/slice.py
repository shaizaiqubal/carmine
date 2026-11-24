from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.db import Database, apply_migrations
from app.slice.pipeline import SlicePipeline
from app.startup_config import load_startup_seed


def _write_outputs(result: dict, output_dir: Path, stage: str):
    output_dir.mkdir(parents=True, exist_ok=True)
    stages = {"plan": ["plan"], "retrieve": ["plan", "retrieve"], "select": ["plan", "retrieve", "select"], "extract": ["plan", "retrieve", "select", "extract"]}[stage]
    for name in stages:
        payload = {"summary": result["summary"]}
        if name in {"plan", "retrieve", "select", "extract"}:
            payload["plans"] = result.get("plans", {})
        if name in {"retrieve", "select", "extract"}:
            payload["retrieved"] = result.get("retrieved", {})
        if name in {"select", "extract"}:
            payload["selected"] = result.get("selected", {})
        if name == "extract":
            payload["candidates"] = result.get("candidates", [])
            payload["low_evidence"] = result.get("low_evidence", [])
        (output_dir / f"{name}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Carmine's market vertical slice")
    parser.add_argument("--startup", required=True, type=Path)
    parser.add_argument("--assumption", type=int)
    parser.add_argument("--stage", choices=["plan", "retrieve", "select", "extract"], default="extract")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("-m", choices=["live"], help="explicitly acknowledge live providers")
    args = parser.parse_args()
    settings = Settings()
    db = Database(settings)
    apply_migrations(db, Path(__file__).resolve().parents[1] / "app" / "migrations")
    try:
        db.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", ("slice-cli",))
        db.commit()
        startup_id = load_startup_seed(args.startup, db, "slice-cli")
        result = SlicePipeline(db).run(startup_id, assumption_index=args.assumption, stage=args.stage, force=args.force)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = Path("eval/out") / args.startup.stem / timestamp
        _write_outputs(result, output_dir, args.stage)
        print(json.dumps(result["summary"], indent=2))
        print(f"artifacts: {output_dir}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
