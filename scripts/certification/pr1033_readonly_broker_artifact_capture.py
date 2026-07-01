#!/usr/bin/env python
"""PR1033 READ_ONLY broker artifact capture/assembly tool.

This script does not connect to IBKR, submit orders, cancel orders, flatten
positions, or fabricate missing broker artifacts. It validates a directory of
operator-provided JSON artifacts against the PR1032 capture contract, redacts
secret-like fields, writes normalized copies, computes SHA-256 hashes, and
emits a review manifest that keeps PAPER_READY=NO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "PR1033.readonly_broker_artifact_capture.v1"
PR1032_MANIFEST_PATH = Path(
    "docs/certification/PR1032_READ_ONLY_BROKER_RUNTIME_ARTIFACT_MANIFEST.example.json"
)
PR1032_RUNBOOK_PATH = Path(
    "docs/certification/PR1032_READ_ONLY_BROKER_CONNECTED_OPERATOR_RUNBOOK.md"
)

FALSE_VALUES = {"0", "false", "no", "off", ""}
TRUE_VALUES = {"1", "true", "yes", "on"}
REDACTED_VALUE = "REDACTED"
SAFE_REDACTED_VALUES = {REDACTED_VALUE, "<redacted>", "NO_SECRET_DATA_PRESENT", ""}
SECRET_KEY_FRAGMENTS = (
    "account_id",
    "accountid",
    "acct",
    "token",
    "credential",
    "password",
    "secret",
    "api_key",
)
FORBIDDEN_RUNTIME_VALUES = {
    "PAPER_READY: YES",
    "PAPER_READINESS_GATE: PASS",
    "RUN_MODE_EFFECTIVE=PAPER",
    "RUN_MODE_EFFECTIVE=LIVE",
    "EXECUTION_ENABLED_EFFECTIVE=true",
    "IBKR_ORDER_SUBMISSION_ENABLED=true",
    "FORCE_CLEAN_START=true",
    "submitted_orders_count>0",
    "cancelled_orders_count>0",
    "modified_orders_count>0",
    "fake trade",
    "synthetic broker order",
    "clean start",
    "flatten position",
    "cancel all orders",
}

REQUIRED_ARTIFACT_IDS = (
    "operator_runbook_acknowledgement",
    "runtime_config_snapshot",
    "broker_connection_snapshot",
    "scanner_cycle_artifact",
    "catalyst_news_artifact",
    "watchlist_focus_artifact",
    "pattern_input_artifact",
    "setup_decision_artifact",
    "risk_gate_artifact",
    "execution_gate_artifact",
    "broker_order_audit",
    "analytics_storage_artifact",
    "final_verdict",
)


class CaptureValidationError(RuntimeError):
    """Raised when the capture bundle is unsafe or incomplete."""


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_id: str
    minimum_fields: tuple[str, ...]
    must_prove: tuple[str, ...]


@dataclass(frozen=True)
class CapturedArtifact:
    artifact_id: str
    source_path: Path
    output_path: Path
    sha256: str
    redaction_status: str
    description: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return None


def _normalize_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_artifact_specs(template_path: Path) -> dict[str, ArtifactSpec]:
    template = load_json(template_path)
    specs: dict[str, ArtifactSpec] = {}
    for raw in template.get("required_artifacts", []):
        artifact_id = str(raw.get("id") or "")
        if not artifact_id:
            continue
        specs[artifact_id] = ArtifactSpec(
            artifact_id=artifact_id,
            minimum_fields=tuple(str(field) for field in raw.get("minimum_fields", [])),
            must_prove=tuple(str(item) for item in raw.get("must_prove", [])),
        )
    missing = sorted(set(REQUIRED_ARTIFACT_IDS) - set(specs))
    if missing:
        raise CaptureValidationError(f"PR1032 template missing artifact specs: {missing}")
    return specs


def assert_safe_runtime_environment(env: Mapping[str, str]) -> dict[str, Any]:
    snapshot = {
        "RUN_MODE": env.get("RUN_MODE"),
        "RUN_MODE_EFFECTIVE": env.get("RUN_MODE_EFFECTIVE"),
        "EXECUTION_ENABLED": env.get("EXECUTION_ENABLED"),
        "EXECUTION_ENABLED_EFFECTIVE": env.get("EXECUTION_ENABLED_EFFECTIVE"),
        "EVENT_REPLAY_MODE_EFFECTIVE": env.get("EVENT_REPLAY_MODE_EFFECTIVE"),
        "IBKR_API_WRITE_ALLOWED": env.get("IBKR_API_WRITE_ALLOWED"),
        "IBKR_ORDER_SUBMISSION_ENABLED": env.get("IBKR_ORDER_SUBMISSION_ENABLED"),
        "FORCE_CLEAN_START": env.get("FORCE_CLEAN_START"),
    }
    if _normalize_upper(snapshot["RUN_MODE"]) != "READ_ONLY":
        raise CaptureValidationError("RUN_MODE must be READ_ONLY before capture")
    if _normalize_upper(snapshot["RUN_MODE_EFFECTIVE"]) != "READ_ONLY":
        raise CaptureValidationError("RUN_MODE_EFFECTIVE must be READ_ONLY before capture")
    if _normalize_bool(snapshot["EXECUTION_ENABLED"]) is not False:
        raise CaptureValidationError("EXECUTION_ENABLED must be false before capture")
    if _normalize_bool(snapshot["EXECUTION_ENABLED_EFFECTIVE"]) is not False:
        raise CaptureValidationError("EXECUTION_ENABLED_EFFECTIVE must be false before capture")
    if _normalize_upper(snapshot["EVENT_REPLAY_MODE_EFFECTIVE"]) != "OFF":
        raise CaptureValidationError("EVENT_REPLAY_MODE_EFFECTIVE must be OFF before capture")
    if _normalize_bool(snapshot["IBKR_API_WRITE_ALLOWED"]) is not False:
        raise CaptureValidationError("IBKR_API_WRITE_ALLOWED must be false before capture")
    if _normalize_bool(snapshot["IBKR_ORDER_SUBMISSION_ENABLED"]) is not False:
        raise CaptureValidationError("IBKR_ORDER_SUBMISSION_ENABLED must be false before capture")
    if _normalize_bool(snapshot["FORCE_CLEAN_START"]) is not False:
        raise CaptureValidationError("FORCE_CLEAN_START must be false before capture")
    return {key: ("" if value is None else str(value)) for key, value in snapshot.items()}


def _looks_secret_key(key: str) -> bool:
    normalized = key.lower()
    if normalized.endswith("_redacted") or normalized.endswith("redacted"):
        return False
    return any(fragment in normalized for fragment in SECRET_KEY_FRAGMENTS)


def redact_payload(value: Any) -> tuple[Any, bool]:
    changed = False

    def redact_inner(item: Any, parent_key: str | None = None) -> Any:
        nonlocal changed
        if isinstance(item, dict):
            redacted: dict[str, Any] = {}
            for key, child in item.items():
                if _looks_secret_key(str(key)):
                    if child not in SAFE_REDACTED_VALUES:
                        changed = True
                    redacted[str(key)] = REDACTED_VALUE
                else:
                    redacted[str(key)] = redact_inner(child, str(key))
            return redacted
        if isinstance(item, list):
            return [redact_inner(child, parent_key) for child in item]
        if parent_key and _looks_secret_key(parent_key):
            if item not in SAFE_REDACTED_VALUES:
                changed = True
            return REDACTED_VALUE
        return item

    return redact_inner(deepcopy(value)), changed


def _string_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        values: list[str] = []
        for key, child in value.items():
            values.append(str(key))
            values.extend(_string_values(child))
        return values
    if isinstance(value, list):
        values = []
        for child in value:
            values.extend(_string_values(child))
        return values
    return [str(value)]


def assert_no_forbidden_evidence(payload: Any, artifact_id: str) -> None:
    joined = "\n".join(_string_values(payload))
    joined_lower = joined.lower()
    for forbidden in FORBIDDEN_RUNTIME_VALUES:
        if forbidden.lower() in joined_lower:
            # Broker order audit fields legitimately contain zero-count field names;
            # only nonzero evidence is forbidden there.
            if forbidden.endswith(">0"):
                continue
            raise CaptureValidationError(f"{artifact_id} contains forbidden evidence: {forbidden}")


def require_fields(payload: Mapping[str, Any], spec: ArtifactSpec) -> None:
    missing = [field for field in spec.minimum_fields if field not in payload]
    if missing:
        raise CaptureValidationError(f"{spec.artifact_id} missing required fields: {missing}")


def _require_false(payload: Mapping[str, Any], key: str, artifact_id: str) -> None:
    if _normalize_bool(payload.get(key)) is not False:
        raise CaptureValidationError(f"{artifact_id}.{key} must be false")


def _require_zero(payload: Mapping[str, Any], key: str, artifact_id: str) -> None:
    try:
        value = int(payload.get(key, -1))
    except (TypeError, ValueError) as exc:
        raise CaptureValidationError(f"{artifact_id}.{key} must be numeric zero") from exc
    if value != 0:
        raise CaptureValidationError(f"{artifact_id}.{key} must be zero")


def assert_artifact_policy(artifact_id: str, payload: Mapping[str, Any]) -> None:
    if artifact_id == "operator_runbook_acknowledgement":
        if payload.get("paper_ready") != "NO":
            raise CaptureValidationError("operator acknowledgement must keep paper_ready=NO")
        if str(payload.get("pre_run_checklist_status") or "").upper() != "PASS":
            raise CaptureValidationError("operator pre-run checklist must be PASS")
        if _normalize_bool(payload.get("abort_conditions_reviewed")) is not True:
            raise CaptureValidationError("operator abort conditions must be reviewed")
    elif artifact_id == "runtime_config_snapshot":
        if _normalize_upper(payload.get("RUN_MODE")) != "READ_ONLY":
            raise CaptureValidationError("runtime RUN_MODE must be READ_ONLY")
        if _normalize_upper(payload.get("RUN_MODE_EFFECTIVE")) != "READ_ONLY":
            raise CaptureValidationError("runtime RUN_MODE_EFFECTIVE must be READ_ONLY")
        _require_false(payload, "EXECUTION_ENABLED", artifact_id)
        _require_false(payload, "EXECUTION_ENABLED_EFFECTIVE", artifact_id)
        if _normalize_upper(payload.get("EVENT_REPLAY_MODE_EFFECTIVE")) != "OFF":
            raise CaptureValidationError("runtime EVENT_REPLAY_MODE_EFFECTIVE must be OFF")
        _require_false(payload, "IBKR_API_WRITE_ALLOWED", artifact_id)
        _require_false(payload, "IBKR_ORDER_SUBMISSION_ENABLED", artifact_id)
        _require_false(payload, "FORCE_CLEAN_START", artifact_id)
    elif artifact_id == "execution_gate_artifact":
        _require_false(payload, "execution_enabled", artifact_id)
        _require_false(payload, "order_submission_enabled", artifact_id)
        _require_false(payload, "api_write_allowed", artifact_id)
        _require_zero(payload, "order_attempt_count", artifact_id)
    elif artifact_id == "broker_order_audit":
        _require_zero(payload, "submitted_orders_count", artifact_id)
        _require_zero(payload, "cancelled_orders_count", artifact_id)
        _require_zero(payload, "modified_orders_count", artifact_id)
    elif artifact_id == "final_verdict":
        if payload.get("paper_ready") != "NO":
            raise CaptureValidationError("final verdict must keep paper_ready=NO")
        if payload.get("paper_readiness_gate") != "FAIL":
            raise CaptureValidationError("final verdict must keep paper_readiness_gate=FAIL")


def _artifact_source_path(source_dir: Path, artifact_id: str) -> Path:
    return source_dir / f"{artifact_id}.json"


def assert_output_dir_ready(output_dir: Path, force: bool) -> None:
    if output_dir.exists():
        if not output_dir.is_dir():
            raise CaptureValidationError(f"output path is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            if not force:
                raise CaptureValidationError(f"output directory is not empty: {output_dir}")
            shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def capture_bundle(
    *,
    source_dir: Path,
    output_dir: Path,
    operator: str,
    template_path: Path = PR1032_MANIFEST_PATH,
    runbook_path: Path = PR1032_RUNBOOK_PATH,
    env: Mapping[str, str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    runtime_env = assert_safe_runtime_environment(env or os.environ)
    if not template_path.exists():
        raise CaptureValidationError(f"manifest template not found: {template_path}")
    if not runbook_path.exists():
        raise CaptureValidationError(f"operator runbook not found: {runbook_path}")
    specs = load_artifact_specs(template_path)
    assert_output_dir_ready(output_dir, force=force)

    captured_at = utc_now_iso()
    captured_artifacts: list[CapturedArtifact] = []
    try:
        for artifact_id in REQUIRED_ARTIFACT_IDS:
            spec = specs[artifact_id]
            source_path = _artifact_source_path(source_dir, artifact_id)
            if not source_path.exists():
                raise CaptureValidationError(f"missing required artifact file: {source_path}")
            raw_payload = load_json(source_path)
            if not isinstance(raw_payload, dict):
                raise CaptureValidationError(f"{artifact_id} must be a JSON object")
            require_fields(raw_payload, spec)
            assert_artifact_policy(artifact_id, raw_payload)
            redacted_payload, changed = redact_payload(raw_payload)
            assert_no_forbidden_evidence(redacted_payload, artifact_id)
            output_path = output_dir / f"{artifact_id}.json"
            write_json(output_path, redacted_payload)
            captured_artifacts.append(
                CapturedArtifact(
                    artifact_id=artifact_id,
                    source_path=source_path,
                    output_path=output_path,
                    sha256=sha256_file(output_path),
                    redaction_status="REDACTED" if changed else "NO_SECRET_DATA_PRESENT",
                    description=f"PR1033 captured {artifact_id}",
                )
            )

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "source_schema_version": load_json(template_path).get("schema_version"),
            "status": "CAPTURE_BUNDLE_VALIDATED_PENDING_HUMAN_REVIEW",
            "paper_ready": "NO",
            "paper_readiness_gate": "FAIL",
            "broker_connected_runtime_artifact_captured": True,
            "operator": operator,
            "captured_at_utc": captured_at,
            "operator_runbook": str(runbook_path.as_posix()),
            "runtime_environment_snapshot": runtime_env,
            "artifacts": [
                {
                    "id": item.artifact_id,
                    "path": item.output_path.name,
                    "sha256": item.sha256,
                    "captured_at_utc": captured_at,
                    "source": str(item.source_path.as_posix()),
                    "redaction_status": item.redaction_status,
                    "description": item.description,
                }
                for item in captured_artifacts
            ],
            "acceptance_gates": [
                {"id": "operator_runbook_acknowledged", "verdict": "PASS"},
                {"id": "readonly_mode_only", "verdict": "PASS"},
                {"id": "clean_start_disabled", "verdict": "PASS"},
                {"id": "zero_broker_order_mutations", "verdict": "PASS"},
                {"id": "redaction_and_hashing_complete", "verdict": "PASS"},
            ],
            "blockers": [
                "Human review required before any readiness decision.",
                "PAPER_READY remains NO by script policy.",
            ],
        }
        write_json(output_dir / "capture_manifest.json", manifest)
        return manifest
    except Exception:
        # Preserve partial artifacts for audit only if the operator chose --force and
        # the directory existed; otherwise leave already-written files visible for debugging.
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and assemble a PR1033 READ_ONLY broker artifact bundle."
    )
    parser.add_argument("--source-dir", required=True, type=Path, help="Directory containing <artifact_id>.json files")
    parser.add_argument("--output-dir", required=True, type=Path, help="Fresh destination directory for normalized artifacts")
    parser.add_argument("--operator", required=True, help="Operator name or initials for manifest metadata")
    parser.add_argument("--manifest-template", default=PR1032_MANIFEST_PATH, type=Path)
    parser.add_argument("--runbook", default=PR1032_RUNBOOK_PATH, type=Path)
    parser.add_argument("--force", action="store_true", help="Replace a non-empty output directory")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = capture_bundle(
            source_dir=args.source_dir,
            output_dir=args.output_dir,
            operator=args.operator,
            template_path=args.manifest_template,
            runbook_path=args.runbook,
            force=args.force,
        )
    except CaptureValidationError as exc:
        print(f"[PR1033][ABORT] {exc}", file=sys.stderr)
        return 2
    print(
        "[PR1033][CAPTURE] "
        f"status={manifest['status']} paper_ready={manifest['paper_ready']} "
        f"artifacts={len(manifest['artifacts'])} output={args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
