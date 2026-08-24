#!/usr/bin/env python3
"""Jetson Controller entry point for the DepthAI sensor recorder.

The managed pipeline copies this repository to a read-only release directory,
then passes the selected config path to this file.  Runtime output must stay in
the writable results directory supplied by the controller.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parent
CODE_ROOT = REPOSITORY_ROOT / "safe_gard_test" / "code"
DEFAULT_CONFIG = REPOSITORY_ROOT / "config.yaml"


def _has_option(arguments: Sequence[str], option: str) -> bool:
    """Return whether argv contains ``--option value`` or ``--option=value``."""
    return any(value == option or value.startswith(f"{option}=") for value in arguments)


def recorder_arguments(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Build recorder argv while enforcing Controller-managed writable paths."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    environment = os.environ if environ is None else environ

    if not _has_option(arguments, "--config"):
        arguments[:0] = ["--config", str(DEFAULT_CONFIG)]

    results_value = environment.get("JETSON_PIPELINE_RESULTS_DIR") or ""
    sensor_bridge_value = environment.get("JETSON_PIPELINE_SENSOR_BRIDGE_DIR") or ""

    if results_value:
        # argparse keeps the final occurrence, so the managed writable path wins
        # over both YAML and a stale argument saved in an older pipeline manifest.
        arguments.extend(["--output-dir", results_value])

    if sensor_bridge_value:
        arguments.extend(["--controller-bridge-dir", sensor_bridge_value])
    elif results_value:
        arguments.extend(
            [
                "--controller-bridge-dir",
                str(Path(results_value) / "controller-bridge"),
            ]
        )
    return arguments


def _load_recorder_main():
    """Import hardware dependencies only when the entry point actually runs."""
    if not CODE_ROOT.is_dir():
        raise RuntimeError(f"DepthAI source directory is missing: {CODE_ROOT}")
    code_path = str(CODE_ROOT)
    if code_path not in sys.path:
        sys.path.insert(0, code_path)

    from geonova_depthai.capture.raw_event_recorder import main as recorder_main

    return recorder_main


def main(argv: Sequence[str] | None = None) -> int:
    recorder_main = _load_recorder_main()
    result = recorder_main(recorder_arguments(argv))
    return int(result) if result is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
