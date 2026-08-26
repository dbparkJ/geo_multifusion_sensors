#!/usr/bin/env python3
"""Create a cross-platform uv environment and install the matching PyTorch build.

This bootstrap intentionally uses Python 3.8-compatible syntax and only the standard
library.  It can therefore install the project's Python 3.11 environment on older
Ubuntu/Jetson hosts before any project dependencies are available.
"""

from __future__ import annotations

import argparse
import json
import ast
import ctypes.util
import os
import platform
import re
import site
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple


TORCH_VERSION = "2.7.1"
TORCHVISION_VERSION = "0.22.1"
TORCHAUDIO_VERSION = "2.7.1"
SUPPORTED_BUILDS = ("cpu", "cu118", "cu126", "cu128")


class JetsonTorchSpec(NamedTuple):
    jetpack: str
    python: str
    torch_url: str
    torchvision: str


JETSON_5_TORCH = JetsonTorchSpec(
    jetpack="5.1.x",
    python="3.8",
    torch_url=(
        "https://developer.download.nvidia.com/compute/redist/jp/v511/pytorch/"
        "torch-2.0.0+nv23.05-cp38-cp38-linux_aarch64.whl"
    ),
    torchvision="0.15.1",
)
JETSON_6_0_TORCH = JetsonTorchSpec(
    jetpack="6.0",
    python="3.10",
    torch_url=(
        "https://developer.download.nvidia.com/compute/redist/jp/v60/pytorch/"
        "torch-2.4.0a0+3bcc3cddb5.nv24.07.16234504-cp310-cp310-linux_aarch64.whl"
    ),
    torchvision="0.19.0",
)
JETSON_6_1_TORCH = JetsonTorchSpec(
    jetpack="6.1/6.2",
    python="3.10",
    torch_url=(
        "https://developer.download.nvidia.com/compute/redist/jp/v61/pytorch/"
        "torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl"
    ),
    torchvision="0.20.0",
)


def run(
    command: List[str],
    cwd: Optional[Path] = None,
    capture: bool = False,
    env: Optional[Dict[str, str]] = None,
) -> str:
    print("+", subprocess.list2cmdline(command), flush=True)
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        env=env,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return completed.stdout or ""


def uv_candidates() -> List[Path]:
    """Return common uv locations, including user installs not present in PATH."""
    executable_name = "uv.exe" if os.name == "nt" else "uv"
    candidates = [Path(sysconfig.get_path("scripts")) / executable_name]
    candidates.append(Path(site.getuserbase()) / ("Scripts" if os.name == "nt" else "bin") / executable_name)
    candidates.append(Path.home() / ".local" / "bin" / executable_name)
    candidates.append(Path.home() / ".cargo" / "bin" / executable_name)
    return candidates


def locate_uv() -> Optional[str]:
    executable = shutil.which("uv")
    if executable:
        return executable
    for candidate in uv_candidates():
        if candidate.is_file():
            return str(candidate)
    return None


def build_pytorch_packages(
    with_torchaudio: bool = False,
    torch_version: str = TORCH_VERSION,
    torchvision_version: str = TORCHVISION_VERSION,
    torchaudio_version: str = TORCHAUDIO_VERSION,
) -> List[str]:
    def package_with_version(package: str, version: str) -> str:
        if version == "latest" or not str(version).strip():
            return package
        return f"{package}=={version}"

    packages = [
        package_with_version("torch", torch_version),
        package_with_version("torchvision", torchvision_version),
    ]
    if with_torchaudio:
        packages.append(package_with_version("torchaudio", torchaudio_version))
    return packages


def install_uv_officially() -> None:
    """Use Astral's installer when pip is unavailable or externally managed."""
    if os.name == "nt":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            raise RuntimeError("PowerShell is required to bootstrap uv on Windows.")
        url = "https://astral.sh/uv/install.ps1"
        suffix = ".ps1"
    else:
        shell = shutil.which("sh")
        if not shell:
            raise RuntimeError("A POSIX sh executable is required to bootstrap uv.")
        url = "https://astral.sh/uv/install.sh"
        suffix = ".sh"

    print(f"Downloading the official uv installer from {url}", flush=True)
    with tempfile.TemporaryDirectory(prefix="depthai-uv-") as temporary:
        installer = Path(temporary) / ("install" + suffix)
        urllib.request.urlretrieve(url, str(installer))
        if os.name == "nt":
            run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer)])
        else:
            run([shell, str(installer)])


def find_uv() -> str:
    executable = locate_uv()
    if executable:
        return executable

    print("uv was not found; bootstrapping it for the current user.", flush=True)
    try:
        run([sys.executable, "-m", "pip", "--version"], capture=True)
    except subprocess.CalledProcessError:
        try:
            run([sys.executable, "-m", "ensurepip", "--upgrade"])
        except subprocess.CalledProcessError:
            pass

    pip_command = [sys.executable, "-m", "pip", "install"]
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
        pip_command.append("--user")
    try:
        run(pip_command + ["uv"])
    except subprocess.CalledProcessError:
        install_uv_officially()

    executable = locate_uv()
    if executable:
        return executable
    raise RuntimeError("uv installation completed but the uv executable was not found.")


def nvcc_version() -> Optional[Tuple[int, int]]:
    executable = shutil.which("nvcc")
    if not executable:
        return None
    output = run([executable, "--version"], capture=True)
    print(output, end="")
    match = re.search(r"release\s+(\d+)\.(\d+)", output)
    return (int(match.group(1)), int(match.group(2))) if match else None


def detect_jetson_release() -> Optional[Tuple[int, int, int]]:
    """Return the L4T release tuple when running on an NVIDIA Jetson."""
    release_file = Path("/etc/nv_tegra_release")
    if sys.platform != "linux" or platform.machine() != "aarch64" or not release_file.is_file():
        return None
    text = release_file.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"# R(\d+).*REVISION:\s*(\d+)(?:\.(\d+))?", text)
    if not match:
        raise RuntimeError(f"Could not parse Jetson L4T release from {release_file}")
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def jetson_torch_spec(release: Tuple[int, int, int]) -> JetsonTorchSpec:
    major, minor, _ = release
    if major == 35:
        return JETSON_5_TORCH
    if major == 36 and minor < 4:
        return JETSON_6_0_TORCH
    if major == 36:
        return JETSON_6_1_TORCH
    raise RuntimeError(
        f"L4T R{major}.{minor} is not supported by this installer. "
        "Add its NVIDIA JetPack PyTorch wheel to jetson_torch_spec()."
    )


def jetson_cuda_arch() -> Optional[str]:
    model_file = Path("/proc/device-tree/model")
    if not model_file.is_file():
        return None
    model = model_file.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
    if "Xavier" in model:
        return "7.2"
    if "Orin" in model:
        return "8.7"
    return None


def python_version(python: Path) -> Tuple[int, int]:
    output = run(
        [str(python), "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
        capture=True,
    )
    major, minor = output.strip().split(".", 1)
    return int(major), int(minor)


def torch_library_dir(python: Path) -> Path:
    output = run(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        capture=True,
    )
    return Path(output.strip()) / "torch" / "lib"


def ensure_jetson_openblas(python: Path) -> None:
    """Place NVIDIA PyTorch's OpenBLAS runtime dependency inside the wheel."""
    if ctypes.util.find_library("openblas"):
        return
    apt_get = shutil.which("apt-get")
    dpkg_deb = shutil.which("dpkg-deb")
    if not apt_get or not dpkg_deb:
        raise RuntimeError(
            "Jetson PyTorch requires libopenblas. Install libopenblas0-pthread and rerun."
        )

    destination = torch_library_dir(python)
    destination.mkdir(parents=True, exist_ok=True)
    print("OpenBLAS is not installed system-wide; installing its runtime inside .venv.")
    with tempfile.TemporaryDirectory(prefix="jetson-openblas-") as temporary:
        temporary_path = Path(temporary)
        run([apt_get, "download", "libopenblas0-pthread"], cwd=temporary_path)
        packages = list(temporary_path.glob("*.deb"))
        if len(packages) != 1:
            raise RuntimeError("Could not resolve the libopenblas0-pthread Debian package.")
        extracted = temporary_path / "extracted"
        run([dpkg_deb, "-x", str(packages[0]), str(extracted)])
        libraries = list(extracted.glob("usr/lib/*/openblas-*/libopenblas*.so*"))
        if not libraries:
            raise RuntimeError("The downloaded OpenBLAS package contained no shared library.")
        for library in libraries:
            shutil.copy2(library.resolve(), destination / library.name)


def install_jetson_torch(
    uv: str,
    python: Path,
    root: Path,
    spec: JetsonTorchSpec,
) -> None:
    numpy_version = "1.24.4" if spec.python == "3.8" else "1.26.4"
    run([
        uv, "pip", "install", "--python", str(python),
        f"numpy=={numpy_version}", "setuptools==69.5.1", "wheel", "pillow", "requests",
    ], cwd=root)
    run([
        uv, "pip", "install", "--python", str(python), "--no-cache", spec.torch_url,
    ], cwd=root)
    ensure_jetson_openblas(python)

    build_env = os.environ.copy()
    build_env["FORCE_CUDA"] = "1"
    build_env["MAX_JOBS"] = build_env.get("MAX_JOBS", "2")
    cuda_arch = jetson_cuda_arch()
    if cuda_arch:
        build_env["TORCH_CUDA_ARCH_LIST"] = cuda_arch
    run([
        uv, "pip", "install", "--python", str(python), "--no-build-isolation", "--no-deps",
        f"git+https://github.com/pytorch/vision.git@v{spec.torchvision}",
    ], cwd=root, env=build_env)


def select_torch_build(requested: str) -> Tuple[str, Optional[Tuple[int, int]]]:
    version = nvcc_version()
    if requested != "auto":
        return requested, version
    if version is None:
        return "cpu", None
    if version >= (12, 8):
        return "cu128", version
    if version >= (12, 6):
        return "cu126", version
    if version >= (11, 8):
        return "cu118", version
    print(f"CUDA Toolkit {version[0]}.{version[1]} has no pinned PyTorch 2.7.1 wheel; using CPU.")
    return "cpu", version


def probe_torch_stack(
    python: Path,
    include_torchaudio: bool = False,
) -> Optional[Dict[str, Any]]:
    base_script = (
        "import json, torch, torchvision, torch.version; "
        "data = {"
        "'torch': torch.__version__, "
        "'torchvision': torchvision.__version__, "
        "'cuda': torch.version.cuda, "
        "'cuda_available': bool(torch.cuda.is_available())"
        "}; "
        "print(json.dumps(data))"
    )
    torchaudio_script = (
        "import json, torch, torchvision, torchaudio, torch.version; "
        "data = {"
        "'torch': torch.__version__, "
        "'torchvision': torchvision.__version__, "
        "'torchaudio': torchaudio.__version__, "
        "'cuda': torch.version.cuda, "
        "'cuda_available': bool(torch.cuda.is_available())"
        "}; "
        "print(json.dumps(data))"
    )
    try:
        output = run(
            [str(python), "-c", torchaudio_script if include_torchaudio else base_script],
            capture=True,
        )
    except subprocess.CalledProcessError:
        return None

    if not output.strip():
        return None
    try:
        return json.loads(output.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return None


def environment_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def parse_scalar(text: str) -> Any:
    value = text.strip()
    lowered = value.lower()
    if lowered in ("null", "none", "~"):
        return None
    if lowered in ("true", "yes", "on"):
        return True
    if lowered in ("false", "no", "off"):
        return False
    try:
        return ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return value.strip("'\"")


def load_setup_config(path: Path) -> Dict[str, Any]:
    """Read the installer's flat YAML file without requiring PyYAML."""
    data = {}  # type: Dict[str, Any]
    for number, source_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = source_line.strip()
        if not line or line.startswith("#") or line == "---":
            continue
        if source_line[:1].isspace() or line.startswith("-") or ":" not in line:
            raise ValueError(f"{path}:{number}: setup config must use flat key: value entries")
        key, value = line.split(":", 1)
        data[key.strip().replace("-", "_")] = parse_scalar(value.split(" #", 1)[0])
    return data


def setup_defaults(config_path: Optional[Path]) -> Dict[str, Any]:
    defaults = {
        "venv": Path(".venv"),
        "python": "3.11",
        "cuda": "auto",
        "recreate": False,
        "dev": False,
    }  # type: Dict[str, Any]
    if config_path is None:
        return defaults

    loaded = load_setup_config(config_path.expanduser().resolve())
    unknown = sorted(set(loaded) - set(defaults))
    if unknown:
        raise ValueError("Unknown setup config keys: " + ", ".join(unknown))
    defaults.update(loaded)
    defaults["venv"] = Path(str(defaults["venv"]))
    defaults["python"] = str(defaults["python"])
    if defaults["cuda"] not in ("auto",) + SUPPORTED_BUILDS:
        raise ValueError("cuda must be one of: auto, " + ", ".join(SUPPORTED_BUILDS))
    for name in ("recreate", "dev"):
        if not isinstance(defaults[name], bool):
            raise ValueError(f"{name} must be true or false")
    return defaults


def parse_args() -> argparse.Namespace:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", type=Path)
    known, _ = bootstrap.parse_known_args()
    try:
        defaults = setup_defaults(known.config)
    except (OSError, ValueError) as exc:
        bootstrap.error(str(exc))

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--config", type=Path, help="Flat YAML setup configuration")
    parser.add_argument("--venv", type=Path, default=defaults["venv"], help="Virtual environment directory")
    parser.add_argument("--python", default=defaults["python"], help="Python version passed to uv venv")
    parser.add_argument(
        "--cuda", choices=("auto",) + SUPPORTED_BUILDS, default=defaults["cuda"],
        help="PyTorch wheel build; auto detects nvcc",
    )
    parser.add_argument(
        "--jetson",
        action="store_true",
        help="Force Jetson installation; real Jetson devices are detected automatically.",
    )
    parser.add_argument(
        "--torch-version",
        default=TORCH_VERSION,
        help="Torch version override (default: %(default)s). Use `latest` to install latest available.",
    )
    parser.add_argument(
        "--torchvision-version",
        default=TORCHVISION_VERSION,
        help="TorchVision version override (default: %(default)s). Use `latest` to install latest available.",
    )
    parser.add_argument(
        "--torchaudio-version",
        default=TORCHAUDIO_VERSION,
        help="TorchAudio version override (default: %(default)s). Use `latest` to install latest available.",
    )
    parser.add_argument(
        "--with-torchaudio",
        action="store_true",
        help="Install torchaudio in Jetson mode (off by default).",
    )
    parser.add_argument("--recreate", dest="recreate", action="store_true", help="Delete and rebuild the selected virtual environment")
    parser.add_argument("--no-recreate", dest="recreate", action="store_false", help=argparse.SUPPRESS)
    parser.add_argument("--dev", dest="dev", action="store_true", help="Also install pytest")
    parser.add_argument("--no-dev", dest="dev", action="store_false", help=argparse.SUPPRESS)
    parser.set_defaults(recreate=defaults["recreate"], dev=defaults["dev"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    root = Path(__file__).resolve().parent
    venv = (root / args.venv).resolve() if not args.venv.is_absolute() else args.venv.resolve()
    uv = find_uv()
    detected_jetson = detect_jetson_release()
    is_jetson = args.jetson or detected_jetson is not None
    if is_jetson and detected_jetson is None:
        raise RuntimeError("--jetson was specified, but /etc/nv_tegra_release was not found.")
    jetson_spec = jetson_torch_spec(detected_jetson) if detected_jetson else None
    selected_python = jetson_spec.python if jetson_spec else args.python
    if jetson_spec:
        build, detected = "cpu", nvcc_version()
    else:
        build, detected = select_torch_build(args.cuda)
    detected_text = "not found" if detected is None else f"{detected[0]}.{detected[1]}"
    if jetson_spec and detected_jetson:
        l4t_text = ".".join(str(part) for part in detected_jetson)
        print(
            f"Jetson detected: L4T R{l4t_text}, JetPack {jetson_spec.jetpack}, "
            f"Python {selected_python}, nvcc CUDA {detected_text}."
        )
    else:
        print(f"Platform: {sys.platform}; nvcc CUDA: {detected_text}; PyTorch build: {build}")

    if args.recreate and venv.exists():
        shutil.rmtree(venv)
    existing_python = environment_python(venv)
    expected_version = tuple(int(part) for part in selected_python.split(".")[:2])
    if existing_python.exists() and python_version(existing_python) != expected_version:
        print(f"Existing environment uses the wrong Python; recreating {venv}.")
        shutil.rmtree(venv)
    if not environment_python(venv).exists():
        if jetson_spec:
            system_python = shutil.which(f"python{selected_python}")
            if not system_python:
                raise RuntimeError(f"JetPack {jetson_spec.jetpack} requires Python {selected_python}.")
            run([uv, "venv", "--python", system_python, str(venv)], cwd=root)
        else:
            run([uv, "python", "install", selected_python], cwd=root)
            run([uv, "venv", "--python", selected_python, str(venv)], cwd=root)

    python = environment_python(venv)
    index_url = (
        "https://download.pytorch.org/whl/cpu"
        if build == "cpu"
        else f"https://download.pytorch.org/whl/{build}"
    )
    if jetson_spec:
        install_jetson_torch(uv, python, root, jetson_spec)
    else:
        run([
            uv, "pip", "install", "--python", str(python),
            *build_pytorch_packages(
                with_torchaudio=True,
                torch_version=args.torch_version,
                torchvision_version=args.torchvision_version,
                torchaudio_version=args.torchaudio_version,
            ),
            "--index-url", index_url,
        ], cwd=root)

    torch_runtime = probe_torch_stack(python, include_torchaudio=args.with_torchaudio)
    if torch_runtime is None:
        if jetson_spec:
            raise RuntimeError("The automatically selected Jetson torch stack failed to import.")
        raise RuntimeError("torch import failed after installation.")
    if jetson_spec and not torch_runtime["cuda_available"]:
        raise RuntimeError(
            "The JetPack-matched PyTorch wheel installed, but CUDA is not available."
        )

    run([uv, "pip", "install", "--python", str(python), "-r", str(root / "requirements.txt")], cwd=root)
    try:
        run([uv, "pip", "install", "--python", str(python), "depthai==3.1.0"], cwd=root)
    except subprocess.CalledProcessError:
        print("uv rejected the DepthAI wheel metadata; using pip for this package only.")
        run([uv, "pip", "install", "--python", str(python), "pip"], cwd=root)
        run([str(python), "-m", "pip", "install", "--force-reinstall", "--no-deps", "depthai==3.1.0"], cwd=root)
    if args.dev:
        run([uv, "pip", "install", "--python", str(python), "pytest"], cwd=root)
    if args.with_torchaudio:
        run([
            str(python), "-c",
            "import torch, torchvision, torchaudio; "
            "print('torch=', torch.__version__); "
            "print('torchvision=', torchvision.__version__); "
            "print('torchaudio=', torchaudio.__version__); "
            "print('torch CUDA build=', torch.version.cuda); "
            "print('CUDA available=', torch.cuda.is_available())",
        ], cwd=root)
    else:
        run([
            str(python), "-c",
            "import torch, torchvision; "
            "print('torch=', torch.__version__); "
            "print('torchvision=', torchvision.__version__); "
            "print('torch CUDA build=', torch.version.cuda); "
            "print('CUDA available=', torch.cuda.is_available())",
        ], cwd=root)
    activate = venv / ("Scripts/Activate.ps1" if os.name == "nt" else "bin/activate")
    print(f"Environment ready. Activate it with: {activate}")


if __name__ == "__main__":
    main()
