"""Readiness checks for statistical intraday momentum strategy."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.config.config_resolver import get_config
from src.storage.storage_engine import StorageEngine
from src.utils.time_utils import to_ny_time


@dataclass
class ReadinessArtifact:
    name: str
    path: str
    loaded: bool
    session_date: str | None = None
    created_at_utc: str | None = None
    version: str | None = None
    count: int | None = None
    notes: str | None = None


@dataclass
class ReadinessReport:
    strategy_key: str
    run_mode: str
    session_date: str
    is_pass: bool
    fail_reasons: List[str] = field(default_factory=list)
    artifacts: List[ReadinessArtifact] = field(default_factory=list)

    def to_text(self) -> str:
        lines = [
            "[READINESS] Statistical Intraday Momentum readiness report",
            f"[READINESS] strategy={self.strategy_key} mode={self.run_mode} session_date={self.session_date}",
            f"[READINESS] status={'PASS' if self.is_pass else 'FAIL'}",
        ]
        for reason in self.fail_reasons:
            lines.append(f"[READINESS][FAIL] {reason}")
        for artifact in self.artifacts:
            status = "LOADED" if artifact.loaded else "MISSING"
            lines.append(
                "[READINESS][ARTEFACT] "
                f"name={artifact.name} status={status} path={artifact.path}"
            )
            if artifact.loaded:
                lines.append(
                    "[READINESS][ARTEFACT] "
                    f"session_date={artifact.session_date} created_at_utc={artifact.created_at_utc} "
                    f"version={artifact.version} count={artifact.count}"
                )
            if artifact.notes:
                lines.append(f"[READINESS][ARTEFACT] notes={artifact.notes}")
        return "\n".join(lines)


def _repo_relative_path(relative_path: str) -> str:
    return StorageEngine._resolve_repo_relative_path(relative_path)


def _load_json(path: str) -> Dict[str, Any] | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _current_session_date() -> str:
    now_ny = to_ny_time(datetime.now(timezone.utc))
    return now_ny.date().isoformat()


def _artifact_path(prefix: str, session_date: str) -> str:
    filename = f"{prefix}_{session_date}.json"
    return _repo_relative_path(os.path.join("data", "cache", "statistical_intraday_momentum", filename))


def _validate_artifact(
    name: str, path: str, payload: Dict[str, Any] | None, session_date: str, count_field: str
) -> tuple[ReadinessArtifact, List[str]]:
    failures: List[str] = []
    if payload is None:
        failures.append(f"Missing {name} artefact at {path}.")
        return ReadinessArtifact(name=name, path=path, loaded=False), failures

    artefact_session = str(payload.get("session_date") or "")
    if artefact_session != session_date:
        failures.append(
            f"{name} session_date mismatch (expected {session_date}, got {artefact_session})."
        )
    count = payload.get(count_field)
    if isinstance(count, int) and count <= 0:
        failures.append(f"{name} count is zero.")
    elif count is None:
        failures.append(f"{name} missing count field '{count_field}'.")

    return (
        ReadinessArtifact(
            name=name,
            path=path,
            loaded=True,
            session_date=artefact_session or None,
            created_at_utc=str(payload.get("created_at_utc") or ""),
            version=str(payload.get("version") or ""),
            count=count if isinstance(count, int) else None,
        ),
        failures,
    )


def run_readiness_check() -> ReadinessReport:
    strategy_key = str(get_config("SELECTED_STRATEGY") or "")
    run_mode = str(get_config("RUN_MODE_EFFECTIVE") or "")
    session_date = _current_session_date()
    fail_reasons: List[str] = []
    artifacts: List[ReadinessArtifact] = []

    if strategy_key != "statistical_intraday_momentum":
        fail_reasons.append(
            "Selected strategy is not statistical_intraday_momentum; "
            "use --strategy statistical_intraday_momentum."
        )

    if not bool(get_config("STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED")):
        fail_reasons.append(
            "STATISTICAL_INTRADAY_MOMENTUM_STRATEGY_ENABLED is False; enable before readiness."
        )

    baseline_path = _artifact_path("baseline_universe", session_date)
    baseline_payload = _load_json(baseline_path)
    baseline_artifact, baseline_failures = _validate_artifact(
        "baseline_universe",
        baseline_path,
        baseline_payload,
        session_date,
        count_field="count",
    )
    artifacts.append(baseline_artifact)
    fail_reasons.extend(baseline_failures)
    if baseline_payload is not None:
        sample = baseline_payload.get("symbols", [])[:5]
        if not sample:
            fail_reasons.append("baseline_universe has empty symbols list.")
        else:
            baseline_artifact.notes = f"sample_symbols={sample}"

    distribution_path = _artifact_path("intraday_distributions", session_date)
    distribution_payload = _load_json(distribution_path)
    distribution_artifact, distribution_failures = _validate_artifact(
        "intraday_distributions",
        distribution_path,
        distribution_payload,
        session_date,
        count_field="series_count",
    )
    artifacts.append(distribution_artifact)
    fail_reasons.extend(distribution_failures)

    readiness_path = _artifact_path("session_readiness", session_date)
    readiness_payload = _load_json(readiness_path)
    readiness_artifact, readiness_failures = _validate_artifact(
        "session_readiness",
        readiness_path,
        readiness_payload,
        session_date,
        count_field="eligible_symbols",
    )
    artifacts.append(readiness_artifact)
    fail_reasons.extend(readiness_failures)
    if readiness_payload is not None:
        phase = str(readiness_payload.get("session_phase") or "")
        allowed = readiness_payload.get("allow_trading")
        if phase:
            readiness_artifact.notes = f"session_phase={phase} allow_trading={allowed}"
        if allowed is False:
            fail_reasons.append("session_readiness indicates allow_trading=False.")

    is_pass = not fail_reasons
    return ReadinessReport(
        strategy_key=strategy_key or "unknown",
        run_mode=run_mode,
        session_date=session_date,
        is_pass=is_pass,
        fail_reasons=fail_reasons,
        artifacts=artifacts,
    )
