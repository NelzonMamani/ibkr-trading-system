"""Prepare a new, private official SDK environment; never run broker code."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import ssl
import stat
import subprocess
import sys
import time
import urllib.request
import zipfile


SDK_URL = "https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip"
SDK_SHA256 = "673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3"
SDK_BYTES = 11412955
SDK_VERSION = "10.50.2"
PROTOBUF_VERSION = "5.29.5"
SDK_SOURCE_COUNT = 235
SDK_SOURCE_SHA256 = "72dccfacba1295b3e4c45d5c97cf160cdb2e86d95b92de2ff408610f570b208b"
PYTHON_PREFIX = "IBJts/source/pythonclient/"
WINDOWS = os.name == "nt"
WINDOWS_ROOT = Path("C:/tmp")
MAX_EXPANDED_BYTES = 134217728
MAX_MEMBER_BYTES = 16777216


class PreparationError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise PreparationError("SDK_DOWNLOAD_REDIRECT_REFUSED")


def copy_verified_archive(source, destination):
    digest, length = hashlib.sha256(), 0
    deadline = time.monotonic() + 120
    with destination.open("xb") as saved:
        while True:
            if time.monotonic() >= deadline:
                raise PreparationError("SDK_DOWNLOAD_BUDGET_EXCEEDED")
            block = source.read(min(131072, SDK_BYTES - length + 1))
            if time.monotonic() >= deadline:
                raise PreparationError("SDK_DOWNLOAD_BUDGET_EXCEEDED")
            if not block:
                break
            length += len(block)
            if length > SDK_BYTES:
                raise PreparationError("SDK_ARCHIVE_SIZE_MISMATCH")
            digest.update(block)
            saved.write(block)
    if length != SDK_BYTES or digest.hexdigest() != SDK_SHA256:
        raise PreparationError("SDK_ARCHIVE_DIGEST_OR_SIZE_MISMATCH")


def obtain_archive(destination, cached_archive=None):
    if cached_archive is not None:
        with Path(cached_archive).open("rb") as source:
            copy_verified_archive(source, destination)
        return
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    request = urllib.request.Request(SDK_URL, headers={"User-Agent": "IBKR-SDK-Preparation/1"})
    with opener.open(request, timeout=20) as response:
        if response.geturl() != SDK_URL:
            raise PreparationError("SDK_DOWNLOAD_ORIGIN_MISMATCH")
        size = response.headers.get("Content-Length")
        if size is not None and size != str(SDK_BYTES):
            raise PreparationError("SDK_ARCHIVE_SIZE_MISMATCH")
        copy_verified_archive(response, destination)


def extract_python_source(archive, destination):
    # Validate the entire central directory before writing any selected source.
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        if len(members) > 10000 or sum(item.file_size for item in members) > MAX_EXPANDED_BYTES:
            raise PreparationError("SDK_ARCHIVE_EXPANSION_LIMIT")
        selected, names = [], set()
        for member in members:
            name = member.filename
            raw_name = member.orig_filename
            path = PurePosixPath(name)
            mode = member.external_attr >> 16
            # ZipInfo may normalize native separators or truncate at NUL. Never
            # accept a rewritten member name as evidence that its raw path is safe.
            if (raw_name != name or "\\" in raw_name or "\x00" in raw_name
                    or not name or "\\" in name or "\x00" in name or path.is_absolute()
                    or any(part in (".", "..") or ":" in part or part.endswith((".", " "))
                           or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", part.split(".")[0])
                           for part in name.rstrip("/").split("/"))
                    or member.file_size > MAX_MEMBER_BYTES or member.flag_bits & 1
                    or stat.S_ISLNK(mode)
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise PreparationError("SDK_ARCHIVE_UNSAFE_MEMBER")
            key = str(path).casefold()
            if key in names:
                raise PreparationError("SDK_ARCHIVE_DUPLICATE_MEMBER")
            names.add(key)
            if name.startswith(PYTHON_PREFIX):
                relative = PurePosixPath(name[len(PYTHON_PREFIX):])
                if relative.parts:
                    selected.append((member, destination.joinpath(*relative.parts)))
        if not selected:
            raise PreparationError("SDK_PYTHON_SOURCE_MISSING")
        destination.mkdir()
        for member, target in selected:
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(member) as source, target.open("xb") as saved:
                shutil.copyfileobj(source, saved, 131072)
    initializer = destination / "ibapi/__init__.py"
    tree = ast.parse(initializer.read_text(encoding="utf-8"))
    versions = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets)]
    if versions != [{"major": 10, "minor": 50, "micro": 2}] or not (destination / "setup.py").is_file():
        raise PreparationError("SDK_PYTHON_VERSION_MISMATCH")


def run_checked(arguments, stage, timeout):
    try:
        process = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise PreparationError(stage + "_FAILED") from None
    if process.returncode:
        raise PreparationError(stage + "_FAILED")
    return process.stdout.strip()


def prepare(base_python, new_root, requirements=None, cached_archive=None):
    base_python, new_root = Path(base_python), Path(new_root)
    repo = Path(__file__).resolve().parents[2]
    requirements = Path(requirements) if requirements is not None else repo / "requirements.txt"
    if not WINDOWS:
        raise PreparationError("WINDOWS_PREPARATION_REQUIRED")
    if (not base_python.is_file() or base_python.name.lower() != "python.exe"
            or not requirements.is_file() or not new_root.is_absolute()
            or new_root.parent.resolve() != WINDOWS_ROOT.resolve() or new_root.exists()
            or new_root.is_symlink() or not new_root.name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", new_root.name)):
        raise PreparationError("NEW_PRIVATE_ROOT_AND_EXISTING_INPUTS_REQUIRED")
    new_root.mkdir()  # Exclusive allocation; never reuse or delete an earlier run.
    archive = new_root / "official-sdk.zip"
    obtain_archive(archive, cached_archive)
    source = new_root / "pythonclient"
    extract_python_source(archive, source)
    environment = new_root / "venv"
    run_checked([str(base_python), "-I", "-B", "-m", "venv", str(environment)], "SDK_VENV_CREATION", 120)
    python = environment / "Scripts/python.exe"
    if not python.is_file():
        raise PreparationError("SDK_NEW_INTERPRETER_MISSING")
    run_checked([str(python), "-I", "-B", "-m", "pip", "--isolated", "install",
                 "--disable-pip-version-check", "--no-input", "--no-cache-dir",
                 "-r", str(requirements.resolve()), str(source), "protobuf==" + PROTOBUF_VERSION],
                "SDK_DEPENDENCY_INSTALL", 900)
    verifier = (
        "import json,sys;from importlib.metadata import version;"
        "sys.path.insert(0,sys.argv[1]);"
        "from src.ibkr.sdk_profile import require_supported_sdk,OFFICIAL_SDK_SOURCE_COUNT,OFFICIAL_SDK_SOURCE_SHA256;"
        "profile=require_supported_sdk();"
        "assert profile=='10.50.2' and version('ibapi')=='10.50.2' and version('protobuf')=='5.29.5';"
        "print(json.dumps({'sdk_version':profile,'protobuf_version':version('protobuf'),"
        "'source_count':OFFICIAL_SDK_SOURCE_COUNT,'source_sha256':OFFICIAL_SDK_SOURCE_SHA256}))"
    )
    try:
        installed = json.loads(run_checked([str(python), "-I", "-B", "-c", verifier, str(repo)],
                                            "SDK_PROFILE_VALIDATION", 60))
    except (TypeError, ValueError):
        raise PreparationError("SDK_PROFILE_VALIDATION_FAILED") from None
    if installed != {"sdk_version": SDK_VERSION, "protobuf_version": PROTOBUF_VERSION,
                     "source_count": SDK_SOURCE_COUNT, "source_sha256": SDK_SOURCE_SHA256}:
        raise PreparationError("SDK_PROFILE_VALIDATION_FAILED")
    report = {"schema": "IBKR_OFFICIAL_SDK_ENVIRONMENT_V1", "status": "SDK_ENVIRONMENT_PREPARED",
              "root": str(new_root), "python": str(python), "sdk_version": SDK_VERSION,
              "protobuf_version": PROTOBUF_VERSION, "archive_sha256": SDK_SHA256,
              "source_count": SDK_SOURCE_COUNT, "source_sha256": SDK_SOURCE_SHA256,
              "sdk_profile_verified": True, "PAPER_READY": False}
    (new_root / "sdk-environment.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-python", required=True)
    parser.add_argument("--new-root", required=True)
    parser.add_argument("--requirements")
    parser.add_argument("--archive", help="Optional cached copy; the same exact digest and size are required.")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.base_python, args.new_root, args.requirements, args.archive)
    except PreparationError as error:
        print(json.dumps({"status": "SDK_ENVIRONMENT_NOT_PREPARED", "code": str(error), "PAPER_READY": False}))
        return 1
    except Exception:
        print(json.dumps({"status": "SDK_ENVIRONMENT_NOT_PREPARED", "code": "SDK_PREPARATION_FAILED", "PAPER_READY": False}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
