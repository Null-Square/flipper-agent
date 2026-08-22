from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    duration_seconds: float


PROFILES: dict[str, tuple[tuple[str, ...], ...]] = {
    "quick": (
        ("ruff", "check", "src", "tests", "scripts"),
        ("pytest", "-q", "-m", "not contract and not hil", "--maxfail=1"),
    ),
    "contract": (
        ("pytest", "-q", "-m", "contract", "--maxfail=1"),
    ),
    "ci": (
        ("ruff", "check", "."),
        ("pytest", "-q", "-m", "not hil"),
    ),
    "hil": (
        ("pytest", "-q", "-m", "hil", "-s"),
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic Hardware Pentest Agent developer/HIL test profiles."
    )
    parser.add_argument("profile", choices=tuple(PROFILES))
    parser.add_argument(
        "--json-output",
        help="Optional JSON summary path; useful for agents and CI wrappers.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.profile == "hil" and os.environ.get("HPA_HIL") != "1":
        print(
            "Refusing to run real-hardware tests: export HPA_HIL=1 explicitly first.",
            file=sys.stderr,
        )
        return 2

    results: list[CommandResult] = []
    for command in PROFILES[args.profile]:
        print("+ " + " ".join(command), flush=True)
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            shell=False,
        )
        duration = time.monotonic() - started
        result = CommandResult(
            command=command,
            returncode=completed.returncode,
            duration_seconds=round(duration, 3),
        )
        results.append(result)
        if completed.returncode != 0:
            break

    passed = bool(results) and all(item.returncode == 0 for item in results)
    payload = {
        "profile": args.profile,
        "passed": passed,
        "hardware_enabled": os.environ.get("HPA_HIL") == "1",
        "results": [asdict(item) for item in results],
    }
    if args.json_output:
        path = Path(args.json_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
