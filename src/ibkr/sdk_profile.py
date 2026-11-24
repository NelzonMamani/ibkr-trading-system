"""Explicit SDK profiles; modern support is READ_ONLY until execution is certified."""
from __future__ import annotations

import hashlib
import importlib.util
from importlib import metadata
from pathlib import Path

LEGACY_SDK_VERSION = "9.81.1.post1"
OFFICIAL_SDK_VERSION = "10.50.2"
OFFICIAL_PROTOBUF_VERSION = "5.29.5"
SUPPORTED_DIAGNOSTIC_SDKS = frozenset((LEGACY_SDK_VERSION, OFFICIAL_SDK_VERSION))
OFFICIAL_SDK_ARCHIVE_URL = "https://interactivebrokers.github.io/downloads/twsapi_macunix.1050.02.zip"
OFFICIAL_SDK_ARCHIVE_SHA256 = "673129e5cba58c4d77bc40647265f84ea42f605eccf88fa4c1221d62d12454f3"
OFFICIAL_SDK_ARCHIVE_BYTES = 11412955
OFFICIAL_SDK_SOURCE_COUNT = 235
OFFICIAL_SDK_SOURCE_SHA256 = "72dccfacba1295b3e4c45d5c97cf160cdb2e86d95b92de2ff408610f570b208b"


def sdk_source_facts(package_root):
    """Hash installed Python sources exactly as the pinned official ZIP contains them."""
    root = Path(package_root)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
    files = sorted(root.rglob("*.py"), key=lambda item: item.relative_to(root).as_posix())
    if len(files) > 500:
        raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
    digest, size = hashlib.sha256(), 0
    for item in files:
        if item.is_symlink() or item.stat().st_size > 2 * 1024 * 1024:
            raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
        value = item.read_bytes()
        size += len(value)
        if size > 16 * 1024 * 1024:
            raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
        digest.update((item.relative_to(root).as_posix() + "\0"
                       + hashlib.sha256(value).hexdigest() + "\n").encode("utf-8"))
    return {"source_count": len(files), "source_sha256": digest.hexdigest()}


def require_supported_sdk():
    """Return a verified profile version; perform no client import or acquisition."""
    try:
        version = metadata.version("ibapi")
        if version == LEGACY_SDK_VERSION:
            return version  # Existing legacy observer/commission checks stay authoritative.
        if version != OFFICIAL_SDK_VERSION or metadata.version("protobuf") != OFFICIAL_PROTOBUF_VERSION:
            raise RuntimeError("IBKR_SDK_PROFILE_UNSUPPORTED")
        spec = importlib.util.find_spec("ibapi")
        if spec is None or not spec.origin:
            raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
        facts = sdk_source_facts(Path(spec.origin).parent)
        if facts != {"source_count": OFFICIAL_SDK_SOURCE_COUNT,
                      "source_sha256": OFFICIAL_SDK_SOURCE_SHA256}:
            raise RuntimeError("IBKR_SDK_SOURCE_UNVERIFIED")
        return version
    except Exception:
        # Package/file errors may contain local paths. Never export their text.
        raise RuntimeError("IBKR_SDK_PROFILE_UNVERIFIED") from None


def require_sdk_execution_profile():
    """Modern SDK data compatibility cannot grant order/fee execution authority."""
    if require_supported_sdk() != LEGACY_SDK_VERSION:
        raise RuntimeError("IBKR_OFFICIAL_SDK_EXECUTION_NOT_CERTIFIED")
