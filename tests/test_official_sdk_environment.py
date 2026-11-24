"""Preparation is filesystem/package setup only; no native client is imported."""

import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import zipfile

import pytest

from scripts.certification import prepare_official_sdk_environment as preparation


def archive_bytes(extra=()):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr(preparation.PYTHON_PREFIX + "ibapi/__init__.py",
                        "VERSION={'major':10,'minor':50,'micro':2}\n")
        zipped.writestr(preparation.PYTHON_PREFIX + "setup.py", "# inert fixture; never execute\n")
        zipped.writestr("IBJts/samples/DO_NOT_RUN.py", "raise AssertionError('sample executed')")
        for name, value in extra:
            # Bypass ZipInfo's platform-dependent constructor normalization so
            # the central directory really contains the hostile raw filename.
            member = zipfile.ZipInfo("fixture-placeholder")
            member.filename = member.orig_filename = name
            zipped.writestr(member, value)
    return stream.getvalue()


def pin_fixture(monkeypatch, data):
    monkeypatch.setattr(preparation, "SDK_BYTES", len(data))
    monkeypatch.setattr(preparation, "SDK_SHA256", hashlib.sha256(data).hexdigest())


def test_pins_match_the_reviewed_source_profile():
    from src.ibkr import sdk_profile
    assert preparation.SDK_URL == sdk_profile.OFFICIAL_SDK_ARCHIVE_URL
    assert preparation.SDK_SHA256 == sdk_profile.OFFICIAL_SDK_ARCHIVE_SHA256
    assert preparation.SDK_BYTES == sdk_profile.OFFICIAL_SDK_ARCHIVE_BYTES
    assert preparation.SDK_VERSION == sdk_profile.OFFICIAL_SDK_VERSION
    assert preparation.PROTOBUF_VERSION == sdk_profile.OFFICIAL_PROTOBUF_VERSION
    assert preparation.SDK_SOURCE_SHA256 == sdk_profile.OFFICIAL_SDK_SOURCE_SHA256
    assert preparation.SDK_SOURCE_COUNT == sdk_profile.OFFICIAL_SDK_SOURCE_COUNT


def test_verified_copy_rejects_digest_size_and_budget_before_install(monkeypatch, tmp_path):
    data = archive_bytes()
    pin_fixture(monkeypatch, data)
    target = tmp_path / "archive.zip"
    preparation.copy_verified_archive(io.BytesIO(data), target)
    assert target.read_bytes() == data
    for index, changed in enumerate((data[:-1], data + b"x", b"x" + data[1:])):
        with pytest.raises(preparation.PreparationError, match="SDK_ARCHIVE"):
            preparation.copy_verified_archive(io.BytesIO(changed), tmp_path / (str(index) + ".zip"))
    clock = iter((0, 121))
    monkeypatch.setattr(preparation.time, "monotonic", lambda: next(clock))
    with pytest.raises(preparation.PreparationError, match="BUDGET"):
        preparation.copy_verified_archive(io.BytesIO(data), tmp_path / "late.zip")


@pytest.mark.parametrize("name", ["../outside.py", "/absolute.py", "C:/drive.py", "a\\b.py", "safe.py\x00hidden.py",
                                 preparation.PYTHON_PREFIX + "../escape.py",
                                 preparation.PYTHON_PREFIX + "nul.txt",
                                 preparation.PYTHON_PREFIX + "trailing."])
def test_unsafe_zip_paths_write_no_source(name, tmp_path):
    archive = tmp_path / "archive.zip"
    archive.write_bytes(archive_bytes(((name, "PRIVATE"),)))
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.infolist()[-1].orig_filename == name
    source = tmp_path / "source"
    with pytest.raises(preparation.PreparationError, match="UNSAFE_MEMBER"):
        preparation.extract_python_source(archive, source)
    assert not source.exists() and not (tmp_path / "outside.py").exists()


def test_zip_rejects_symlinks_duplicates_and_expansion(monkeypatch, tmp_path):
    for index, kind in enumerate(("symlink", "duplicate", "oversize")):
        archive = tmp_path / (kind + ".zip")
        with zipfile.ZipFile(archive, "w") as zipped:
            if kind == "symlink":
                member = zipfile.ZipInfo(preparation.PYTHON_PREFIX + "link")
                member.create_system = 3
                member.external_attr = (stat.S_IFLNK | 0o777) << 16
                zipped.writestr(member, "../private")
            elif kind == "duplicate":
                zipped.writestr("same.py", "x")
                zipped.writestr("SAME.py", "x")
            else:
                zipped.writestr("large.py", "x" * 20)
                monkeypatch.setattr(preparation, "MAX_EXPANDED_BYTES", 10)
        source = tmp_path / ("source-" + str(index))
        with pytest.raises(preparation.PreparationError, match="SDK_ARCHIVE"):
            preparation.extract_python_source(archive, source)
        assert not source.exists()


def test_preparation_is_new_environment_only_with_exact_local_sdk(monkeypatch, tmp_path):
    monkeypatch.setattr(preparation, "WINDOWS", True)
    monkeypatch.setattr(preparation, "WINDOWS_ROOT", tmp_path)
    base = tmp_path / "base"
    base.mkdir()
    python = base / "python.exe"
    python.write_bytes(b"BASE_INTERPRETER_UNCHANGED")
    old_sdk = base / "site-packages.txt"
    old_sdk.write_text("legacy SDK remains unchanged")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("ibapi>=9.81.1.post1\npytest>=7.4.0\n")
    data = archive_bytes()
    pin_fixture(monkeypatch, data)
    cached = tmp_path / "cached.zip"
    cached.write_bytes(data)
    root = tmp_path / "new-sdk-root"
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        assert kwargs == dict(capture_output=True, text=True, timeout=120 if len(calls) == 1 else 900 if len(calls) == 2 else 60, check=False)
        if len(calls) == 1:
            assert arguments == [str(python), "-I", "-B", "-m", "venv", str(root / "venv")]
            new_python = root / "venv/Scripts/python.exe"
            new_python.parent.mkdir(parents=True)
            new_python.write_bytes(b"NEW_INTERPRETER")
            return subprocess.CompletedProcess(arguments, 0, "", "")
        assert arguments[0] == str(root / "venv/Scripts/python.exe")
        if len(calls) == 2:
            assert "--isolated" in arguments and "--no-input" in arguments
            assert str(requirements) in arguments and str(root / "pythonclient") in arguments
            assert arguments[-1] == "protobuf==5.29.5"
            return subprocess.CompletedProcess(arguments, 0, "", "")
        assert "require_supported_sdk" in arguments[4]
        assert "ibkr_client" not in arguments[4] and "connect(" not in arguments[4]
        return subprocess.CompletedProcess(arguments, 0, json.dumps({
            "sdk_version": "10.50.2", "protobuf_version": "5.29.5",
            "source_count": preparation.SDK_SOURCE_COUNT, "source_sha256": preparation.SDK_SOURCE_SHA256}), "")

    monkeypatch.setattr(preparation.subprocess, "run", run)
    monkeypatch.setattr(preparation.urllib.request, "build_opener", lambda *args: pytest.fail("Cached ZIP must not use network"))
    result = preparation.prepare(python, root, requirements, cached)
    assert result["status"] == "SDK_ENVIRONMENT_PREPARED" and not result["PAPER_READY"]
    assert len(calls) == 3 and not (root / "pythonclient/DO_NOT_RUN.py").exists()
    assert python.read_bytes() == b"BASE_INTERPRETER_UNCHANGED"
    assert old_sdk.read_text() == "legacy SDK remains unchanged" and cached.read_bytes() == data
    with pytest.raises(preparation.PreparationError, match="NEW_PRIVATE_ROOT"):
        preparation.prepare(python, root, requirements, cached)
    assert len(calls) == 3


def test_bad_archive_or_existing_root_starts_no_subprocess(monkeypatch, tmp_path):
    monkeypatch.setattr(preparation, "WINDOWS", True)
    monkeypatch.setattr(preparation, "WINDOWS_ROOT", tmp_path)
    python = tmp_path / "python.exe"
    python.write_bytes(b"base")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("ibapi>=9.81.1.post1")
    archive = tmp_path / "bad.zip"
    archive.write_bytes(b"wrong")
    monkeypatch.setattr(preparation.subprocess, "run", lambda *args, **kwargs: pytest.fail("No process for invalid archive"))
    with pytest.raises(preparation.PreparationError, match="DIGEST_OR_SIZE"):
        preparation.prepare(python, tmp_path / "fresh", requirements, archive)
    with pytest.raises(preparation.PreparationError, match="NEW_PRIVATE_ROOT"):
        preparation.prepare(python, tmp_path / "missing-parent/elsewhere", requirements, archive)
    assert python.read_bytes() == b"base"


@pytest.mark.parametrize("changed", [{"protobuf_version": "0.0"}, {"sdk_version": "9.81.1.post1"},
                                     {"source_sha256": "0" * 64}])
def test_preparation_rejects_wrong_installed_profile(monkeypatch, tmp_path, changed):
    monkeypatch.setattr(preparation, "WINDOWS", True)
    monkeypatch.setattr(preparation, "WINDOWS_ROOT", tmp_path)
    python = tmp_path / "python.exe"
    python.write_bytes(b"BASE")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("ibapi>=9.81.1.post1")
    data = archive_bytes()
    pin_fixture(monkeypatch, data)
    archive = tmp_path / "cached.zip"
    archive.write_bytes(data)
    root = tmp_path / "new-root"
    def run(arguments, stage, timeout):
        if stage == "SDK_VENV_CREATION":
            target = root / "venv/Scripts/python.exe"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"NEW")
        if stage == "SDK_PROFILE_VALIDATION":
            return json.dumps({"sdk_version": "10.50.2", "protobuf_version": "5.29.5",
                               "source_count": preparation.SDK_SOURCE_COUNT,
                               "source_sha256": preparation.SDK_SOURCE_SHA256, **changed})
        return ""
    monkeypatch.setattr(preparation, "run_checked", run)
    with pytest.raises(preparation.PreparationError, match="SDK_PROFILE_VALIDATION_FAILED"):
        preparation.prepare(python, root, requirements, archive)
    assert not (root / "sdk-environment.json").exists() and python.read_bytes() == b"BASE"


def test_download_rejects_redirects_and_pins_tls_origin(monkeypatch, tmp_path):
    data = archive_bytes()
    pin_fixture(monkeypatch, data)
    captured = {}

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(data))}
        def geturl(self): return preparation.SDK_URL
    class Opener:
        def open(self, request, timeout):
            captured.update(url=request.full_url, timeout=timeout)
            return Response(data)
    def build(*handlers):
        assert isinstance(handlers[0], preparation.urllib.request.HTTPSHandler)
        assert handlers[0]._context.verify_mode == preparation.ssl.CERT_REQUIRED
        assert handlers[0]._context.check_hostname
        assert isinstance(handlers[1], preparation.NoRedirect)
        return Opener()
    monkeypatch.setattr(preparation.urllib.request, "build_opener", build)
    preparation.obtain_archive(tmp_path / "download.zip")
    assert captured == {"url": preparation.SDK_URL, "timeout": 20}
    with pytest.raises(preparation.PreparationError, match="REDIRECT_REFUSED"):
        preparation.NoRedirect().redirect_request(None, None, 302, "", {}, "http://untrusted.invalid")
    monkeypatch.setattr(Response, "geturl", lambda self: "https://untrusted.invalid/file.zip")
    with pytest.raises(preparation.PreparationError, match="ORIGIN_MISMATCH"):
        preparation.obtain_archive(tmp_path / "wrong-origin.zip")
    assert not (tmp_path / "wrong-origin.zip").exists()


def test_cli_never_exports_exception_text(monkeypatch, capsys):
    monkeypatch.setattr(preparation, "prepare", lambda *args: (_ for _ in ()).throw(OSError("PRIVATE_PATH_OR_TOKEN")))
    assert preparation.main(["--base-python", "unused", "--new-root", "unused"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report == {"status": "SDK_ENVIRONMENT_NOT_PREPARED", "code": "SDK_PREPARATION_FAILED", "PAPER_READY": False}
