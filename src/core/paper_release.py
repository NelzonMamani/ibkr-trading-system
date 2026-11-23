"""Bounded, operator-attested PAPER entry for the standalone ABCD setup."""

import os
import re
from datetime import datetime, timezone
from threading import Lock

from src.config.config_resolver import get_config
from src.config.runtime_config import RunMode, get_force_clean_start
from src.execution.position_truth import PositionTruthConfig, collect_broker_position_snapshot
from src.core.acquisition import AcquisitionCancelled, AcquisitionDeadlineExceeded
from src.market_data.session_pct_change import covered_opening_window


class PaperRelease:
    def __init__(self, expected_account):
        self.expected_account = expected_account
        self.scope = None
        self.attempted = False
        self.rejection = None
        self.last_gate = None
        self.lock = Lock()

    @classmethod
    def from_environment(cls, mode, allow_orders, strategy_keys):
        enabled = os.environ.get("ROSS_PAPER_RELEASE_ENABLED", "0")
        if enabled == "0":
            return None
        if (enabled != "1" or mode != RunMode.PAPER or not allow_orders
                or get_config("RISK_PROFILE") != "MICRO" or strategy_keys != ["ross_momentum"]):
            raise RuntimeError("PAPER_RELEASE_REQUIRES_PAPER_MICRO_ROSS")
        if (get_force_clean_start()
                or os.environ.get("FLATTEN_ON_STARTUP", "").strip().lower() == "true"):
            raise RuntimeError("PAPER_RELEASE_STARTUP_MUTATION_CONFIGURED")
        if (get_config("SCANNER_DATA_SOURCE") == "MOCK"
                or get_config("FORCE_EXECUTION_ON_TRADE_READY") is True
                or get_config("FORCE_RISK_APPROVAL_FOR_TRADE_READY") is True):
            raise RuntimeError("PAPER_RELEASE_VALIDATION_OVERRIDE_ACTIVE")
        if os.environ.get("ROSS_PAPER_EXCLUSIVE_START_ATTESTED") != "1":
            raise RuntimeError("PAPER_RELEASE_OPERATOR_ATTESTATION_REQUIRED")
        account = os.environ.get("ROSS_PAPER_EXPECTED_ACCOUNT", "")
        if re.fullmatch(r"DUK?[0-9]+", account) is None:
            raise RuntimeError("PAPER_RELEASE_EXPECTED_ACCOUNT_REQUIRED")
        return cls(account)

    def _observe(self, event):
        event_type = event.get("event_type")
        if event_type in {"openOrder", "orderStatus", "execDetails"} or (
                event_type == "position" and event.get("position") != 0):
            with self.lock:
                if not self.attempted:
                    self.rejection = "PAPER_RELEASE_UNEXPECTED_ACTIVITY"

    def _scope(self, client):
        if (client is None or not client.is_connected()
                or tuple(client._managed_accounts) != (self.expected_account,)):
            raise RuntimeError("PAPER_RELEASE_NATIVE_SCOPE_UNAVAILABLE")
        return (client, client.client_id, client._position_connection_epoch,
                getattr(client, "_managed_accounts_generation", 0))

    def _check(self, client, engine, now):
        if self.attempted:
            raise RuntimeError("PAPER_RELEASE_ENTRY_ATTEMPT_USED")
        if self.rejection:
            raise RuntimeError(self.rejection)
        if (not engine.startup_recovery_complete() or engine._failsafe_block_new_entries
                or engine._native_quarantined):
            raise RuntimeError("PAPER_RELEASE_RECOVERY_NOT_CLEAR")
        window = covered_opening_window(now)
        if window is None or window.phase != "RTH_OPEN":
            raise RuntimeError("PAPER_RELEASE_REVIEWED_OPENING_REQUIRED")
        try:
            scope = self._scope(client)
        except RuntimeError:
            if self.scope is None:
                raise
            scope = None
        if self.scope is not None and scope != self.scope:
            self.rejection = "PAPER_RELEASE_NATIVE_SCOPE_CHANGED"
            raise RuntimeError(self.rejection)
        return scope

    def check_start(self, client, engine, now):
        scope = self._check(client, engine, now)
        if self.scope is None:
            client.register_reconciliation_callback(self._observe)
            self.scope = scope
        positions = collect_broker_position_snapshot(
            client, as_of=now, config=PositionTruthConfig(broker_required=True, run_mode=RunMode.PAPER))
        if positions.status != "COMPLETE" or positions.account != self.expected_account:
            raise RuntimeError("PAPER_RELEASE_POSITION_TRUTH_UNAVAILABLE")
        if positions:
            self.rejection = "PAPER_RELEASE_START_NOT_FLAT"
            raise RuntimeError(self.rejection)
        try:
            orders = client.openOrders(require_complete=True)
        except (AcquisitionCancelled, AcquisitionDeadlineExceeded):
            raise
        except RuntimeError:
            raise RuntimeError("PAPER_RELEASE_CURRENT_CLIENT_ORDERS_UNAVAILABLE") from None
        if orders:
            self.rejection = "PAPER_RELEASE_CURRENT_CLIENT_ORDERS_PRESENT"
            raise RuntimeError(self.rejection)
        self._check(client, engine, datetime.now(timezone.utc))

    def authorize(self, request, client, contract, order, now, engine):
        if (request.setup_family_id != "ABCD" or request.relationship_context
                or request.quantity != 1 or order.totalQuantity != 1 or order.action != "BUY"
                or order.account != self.expected_account or contract.secType != "STK"
                or not request.stop_loss_price or request.take_profit_price is not None):
            raise RuntimeError("PAPER_RELEASE_REQUIRES_STANDALONE_ABCD_ONE_SHARE")
        self.check_start(client, engine, now)
        def consume():
            with self.lock:
                self._check(client, engine, datetime.now(timezone.utc))
                self.attempted = True
        return consume
