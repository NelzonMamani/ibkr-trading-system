from __future__ import annotations

import json
import os
from typing import Optional, Set


class SubmissionGuard:
    """
    Enforces a strict single-order-per-run policy with optional persistence.
    """

    def __init__(self, max_orders_per_run: int = 1, persist_path: Optional[str] = None):
        self.max_orders_per_run = max_orders_per_run
        self.persist_path = persist_path
        self._submitted_count = 0
        self._submitted_ids: Set[str] = set()
        self._load()

    def can_submit(self) -> bool:
        return self._submitted_count < self.max_orders_per_run

    def mark_submitted(self, client_order_id: str) -> None:
        if self.already_submitted(client_order_id):
            return

        self._submitted_ids.add(client_order_id)
        self._submitted_count += 1
        self._persist()

    def submitted_count(self) -> int:
        return self._submitted_count

    def already_submitted(self, client_order_id: str) -> bool:
        return client_order_id in self._submitted_ids

    def _load(self) -> None:
        if not self.persist_path:
            return

        try:
            with open(self.persist_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[SUBMISSION_GUARD] Failed to load state: {exc}")
            return

        client_order_ids = data.get("client_order_ids") or []
        if isinstance(client_order_ids, list):
            self._submitted_ids = set(client_order_ids)

        submitted_count = data.get("submitted_count")
        if isinstance(submitted_count, int):
            self._submitted_count = max(submitted_count, len(self._submitted_ids))
        else:
            self._submitted_count = len(self._submitted_ids)

    def _persist(self) -> None:
        if not self.persist_path:
            return

        directory = os.path.dirname(self.persist_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        payload = {
            "submitted_count": self._submitted_count,
            "client_order_ids": sorted(self._submitted_ids),
        }
        try:
            with open(self.persist_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[SUBMISSION_GUARD] Failed to persist state: {exc}")
