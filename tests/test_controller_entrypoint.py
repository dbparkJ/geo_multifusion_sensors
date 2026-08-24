from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULES_BEFORE_ENTRYPOINT_IMPORT = set(sys.modules)
SPEC = importlib.util.spec_from_file_location(
    "geo_multifusion_controller_main",
    REPOSITORY_ROOT / "main.py",
)
assert SPEC is not None and SPEC.loader is not None
controller_main = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controller_main)
MODULES_IMPORTED_BY_ENTRYPOINT = set(sys.modules) - MODULES_BEFORE_ENTRYPOINT_IMPORT


def _last_value(arguments: list[str], option: str) -> str:
    parser = argparse.ArgumentParser()
    parser.add_argument(option)
    parsed, _ = parser.parse_known_args(arguments)
    return getattr(parsed, option.lstrip("-").replace("-", "_"))


def test_import_is_hardware_lazy() -> None:
    assert not any(
        name == "depthai" or name.startswith("geonova_depthai")
        for name in MODULES_IMPORTED_BY_ENTRYPOINT
    )
    assert controller_main.CODE_ROOT == REPOSITORY_ROOT / "safe_gard_test" / "code"


def test_default_arguments_use_root_config_without_overriding_its_paths() -> None:
    arguments = controller_main.recorder_arguments([], {})

    assert arguments[:2] == ["--config", str(REPOSITORY_ROOT / "config.yaml")]
    assert "--controller-bridge-dir" not in arguments
    assert "--output-dir" not in arguments


def test_explicit_bridge_argument_is_preserved_without_managed_path_environment() -> None:
    arguments = controller_main.recorder_arguments(
        ["--controller-bridge-dir", "/var/lib/jetson-sensors"],
        {},
    )

    assert _last_value(arguments, "--controller-bridge-dir") == "/var/lib/jetson-sensors"
    assert arguments.count("--controller-bridge-dir") == 1


def test_controller_results_override_is_the_last_output_value() -> None:
    arguments = controller_main.recorder_arguments(
        ["--config=field.yaml", "--output-dir", "stale-output"],
        {"JETSON_PIPELINE_RESULTS_DIR": "/srv/pipeline/results"},
    )

    assert arguments.count("--config=field.yaml") == 1
    assert arguments[-4:] == [
        "--output-dir",
        "/srv/pipeline/results",
        "--controller-bridge-dir",
        "/srv/pipeline/results/controller-bridge",
    ]
    assert _last_value(arguments, "--output-dir") == "/srv/pipeline/results"


def test_explicit_sensor_bridge_environment_wins() -> None:
    arguments = controller_main.recorder_arguments(
        ["--controller-bridge-dir=stale-bridge"],
        {
            "JETSON_PIPELINE_RESULTS_DIR": "/srv/pipeline/results",
            "JETSON_PIPELINE_SENSOR_BRIDGE_DIR": "/var/lib/jetson-sensors",
        },
    )

    assert _last_value(arguments, "--controller-bridge-dir") == "/var/lib/jetson-sensors"


def test_main_delegates_adjusted_argv_without_loading_hardware_in_test(monkeypatch) -> None:
    captured = []

    def fake_recorder(arguments):
        captured.extend(arguments)

    monkeypatch.setattr(controller_main, "_load_recorder_main", lambda: fake_recorder)
    monkeypatch.setenv("JETSON_PIPELINE_RESULTS_DIR", "/tmp/managed-results")
    monkeypatch.delenv("JETSON_PIPELINE_SENSOR_BRIDGE_DIR", raising=False)

    assert controller_main.main(["--config", "selected.yaml"]) == 0
    assert _last_value(captured, "--output-dir") == "/tmp/managed-results"
    assert _last_value(captured, "--controller-bridge-dir") == (
        "/tmp/managed-results/controller-bridge"
    )


def test_root_config_contains_only_portable_runtime_paths() -> None:
    config = yaml.safe_load((REPOSITORY_ROOT / "config.yaml").read_text(encoding="utf-8"))

    assert config["output_dir"] == "results"
    assert config["controller_bridge_dir"] == "results/controller-bridge"
    assert not Path(config["output_dir"]).is_absolute()
    assert not Path(config["controller_bridge_dir"]).is_absolute()
