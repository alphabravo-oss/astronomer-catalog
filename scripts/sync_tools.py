#!/usr/bin/env python3
"""Install the complete locked tool graph; only PyYAML may build from source."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import pathlib
import platform
import re
import signal
import subprocess
import sys
import threading
import time
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def observe_exit(process: subprocess.Popen[bytes]) -> bool:
    # Keep the child unreaped until group drain; its PID cannot be reused.
    observed = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    return observed is not None and observed.si_pid == process.pid


def live_descendants(group: int) -> list[int]:
    found = []
    for directory in pathlib.Path("/proc").iterdir():
        if not directory.name.isdigit() or int(directory.name) == group:
            continue
        try:
            raw = (directory / "stat").read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        fields = raw[raw.rfind(")") + 2:].split()
        if len(fields) < 3:
            raise RuntimeError("owned process inventory incomplete")
        if int(fields[2]) == group and fields[0] not in {"Z", "X"}:
            found.append(int(directory.name))
    return found


def signal_owned_group(process: subprocess.Popen[bytes], action: signal.Signals) -> None:
    observe_exit(process)  # ChildProcessError fails closed without a group signal.
    try:
        os.killpg(process.pid, action)
    except ProcessLookupError:
        pass


def drain_owned_group(process: subprocess.Popen[bytes], terminate: bool) -> None:
    exited = observe_exit(process)
    descendants = live_descendants(process.pid)
    if terminate or not exited or descendants:
        signal_owned_group(process, signal.SIGTERM)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if observe_exit(process) and not live_descendants(process.pid):
                break
            time.sleep(0.02)
        if not observe_exit(process) or live_descendants(process.pid):
            signal_owned_group(process, signal.SIGKILL)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if observe_exit(process) and not live_descendants(process.pid):
            process.wait(timeout=0.5)
            return
        time.sleep(0.02)
    raise RuntimeError("owned synchronization group did not drain")


def synchronize(command: list[str], env: dict[str, str], timeout: float = 600) -> None:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("synchronization requires a positive finite timeout")
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise ValueError("synchronization requires default child ownership")
    if threading.active_count() != 1:
        raise ValueError("synchronization requires the single-threaded installer")
    process: subprocess.Popen[bytes] | None = None
    completed = False
    # The first interrupt triggers finally; further signals cannot cut drain short.
    def interrupt(_number: int, _frame: object) -> None:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise InterruptedError("catalog synchronization interrupted")

    previous = {number: signal.signal(number, interrupt)
                for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        # Defer pending parent interrupts until the owned child handle is stored.
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        def restore_child_mask() -> None:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        try:
            process = subprocess.Popen(command, env=env, start_new_session=True,
                                       preexec_fn=restore_child_mask)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        deadline = time.monotonic() + timeout
        while not observe_exit(process):
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(command, timeout)
            time.sleep(0.05)
        completed = True
    finally:
        try:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            if process is not None:
                drain_owned_group(process, terminate=not completed)
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)
    if process is None or process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode if process else -1, command)


def package_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", value):
        raise ValueError("invalid locked package name")
    return re.sub(r"[-_.]+", "-", value).lower()


def locked_names(lock: dict) -> list[str]:
    if lock.get("requires-python") != "==3.15.*":
        raise ValueError("lock must select Python 3.15")
    names = []
    for row in lock.get("package", []):
        if row.get("source") == {"virtual": "."}:
            if row.get("name") != "astronomer-catalog-tools":
                raise ValueError("unexpected virtual project")
            continue
        if row.get("source") != {"registry": "https://pypi.org/simple"}:
            raise ValueError("locked tools must use the canonical public index")
        name = package_name(row["name"])
        if name in names or not isinstance(row.get("version"), str):
            raise ValueError("duplicate or malformed locked package")
        artifacts = row.get("wheels", []) + ([row["sdist"]] if "sdist" in row else [])
        if not artifacts or any(
            not re.fullmatch(r"sha256:[a-f0-9]{64}", artifact.get("hash", ""))
            for artifact in artifacts
        ):
            raise ValueError("every locked distribution must have a SHA256 digest")
        if name == "pyyaml" and row["version"] != "6.0.3":
            raise ValueError("PyYAML source-build exception requires explicit review")
        names.append(name)
    if "pyyaml" not in names or not {"cython", "setuptools"}.issubset(names):
        raise ValueError("locked source-build backend is incomplete")
    return sorted(names)


def commands(uv: str, python: str, names: list[str]) -> list[list[str]]:
    base = [uv, "--no-config", "--directory", str(ROOT)]
    common = ["sync", "--locked", "--python", python,
              "--default-index", "https://pypi.org/simple", "--no-install-project"]
    backend = base + common + ["--only-group", "build-backend", "--no-build"]
    complete = base + common + ["--all-groups", "--no-default-groups",
                               "--no-binary-package", "pyyaml",
                               "--no-build-isolation-package", "pyyaml"]
    for name in names:
        if name != "pyyaml":
            complete += ["--no-build-package", name]
    return [backend, complete]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True, help="Selected Python 3.15.0 executable")
    parser.add_argument("--uv", default="uv", help="Selected uv 0.13.0 executable")
    parser.add_argument("--environment", default=str(ROOT / ".venv"))
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "aarch64"}:
        raise ValueError("catalog tooling supports Linux x86_64/aarch64 only")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYYAML_FORCE_LIBYAML": "0",
           "UV_PYTHON_DOWNLOADS": "never", "UV_PROJECT_ENVIRONMENT": args.environment,
           "UV_COMPILE_BYTECODE": "0"}
    # Do not inherit an alternative resolver/index/build configuration.
    for key in tuple(env):
        if key.startswith(("PIP_", "UV_")) and key not in {
            "UV_PYTHON_DOWNLOADS", "UV_PROJECT_ENVIRONMENT", "UV_COMPILE_BYTECODE"
        }:
            del env[key]
    python_version = subprocess.check_output(
        [args.python, "--version"], env=env, text=True, timeout=30
    ).strip()
    uv_version = subprocess.check_output(
        [args.uv, "--version"], env=env, text=True, timeout=30
    ).strip()
    if python_version != "Python 3.15.0" or not uv_version.startswith("uv 0.13.0 "):
        raise ValueError("selected Python/uv versions do not match the reviewed toolchain")
    lock_path = ROOT / "uv.lock"
    before = lock_path.read_bytes()
    names = locked_names(tomllib.loads(before.decode()))
    for command in commands(args.uv, args.python, names):
        synchronize(command, env)
        if lock_path.read_bytes() != before:
            raise ValueError("locked synchronization changed uv.lock")
    print(f"installed {len(names)} locked tool versions; lock SHA256 "
          f"{hashlib.sha256(before).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
