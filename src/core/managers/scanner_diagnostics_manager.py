from __future__ import annotations

from typing import Iterable

from src.scanner.result_models import CandidateMetrics
from src.scanner.session_pct_change import normalize_session_label


class ScannerDiagnosticsManager:
    """Prints scanner diagnostics tables and drop reasons."""

    def print_top_50(self, observations: Iterable[CandidateMetrics]) -> None:
        rows = list(observations)[:50]
        print("[SCANNER][DIAGNOSTICS] Top 50 observations (extended columns)")
        self._print_table(rows)

    def print_watchlist(
        self,
        watchlist: Iterable[CandidateMetrics],
        observations: Iterable[CandidateMetrics],
    ) -> None:
        watchlist_rows = list(watchlist)[:15]
        print("[SCANNER][DIAGNOSTICS] Watchlist (top 15, same columns preserved)")
        self._print_table(watchlist_rows)
        self._print_drop_reasons(observations, watchlist_rows)

    def _print_table(self, rows: list[CandidateMetrics]) -> None:
        for idx, row in enumerate(rows, start=1):
            session_label = normalize_session_label(row.session_label or "")
            pct_source = row.pct_source or "UNKNOWN_REF"
            data_quality = ",".join(row.data_quality_flags or []) or "OK"
            drop_reasons = ",".join(row.drop_reasons or []) or "-"
            print(
                "[SCANNER][ROW] "
                f"rank={idx} symbol={row.symbol} conId={row.con_id} exchange={row.exchange} "
                f"session={session_label} "
                f"last={self._fmt(row.last_price)} "
                f"ref_close={self._fmt(row.ref_close_rth or row.prev_close)} "
                f"pct_change={self._fmt(row.pct_change)} "
                f"pct_ref={pct_source} "
                f"volume={self._fmt_int(row.volume)} "
                f"avg_volume_20d={self._fmt_int(row.avg_volume_20d)} "
                f"rvol={self._fmt(row.rvol)} "
                f"bid={self._fmt(row.bid)} ask={self._fmt(row.ask)} "
                f"spread={self._fmt(row.spread)} spread_pct={self._fmt(row.spread_pct)} "
                f"dollar_volume={self._fmt(row.dollar_volume)} "
                f"float_m={self._fmt(row.float_millions)} "
                f"halted={row.halted} ssr={row.ssr} "
                f"data_quality={data_quality} drop_reasons={drop_reasons}"
            )

    def _print_drop_reasons(
        self,
        observations: Iterable[CandidateMetrics],
        watchlist: list[CandidateMetrics],
    ) -> None:
        watchlist_symbols = {row.symbol for row in watchlist}
        dropped = [row for row in observations if row.symbol not in watchlist_symbols]
        if not dropped:
            print("[SCANNER][DIAGNOSTICS] Drop reasons: none")
            return
        print("[SCANNER][DIAGNOSTICS] Drop reasons (top50 -> watchlist)")
        for row in dropped:
            reasons = list(row.drop_reasons or [])
            if not reasons:
                reasons = self._infer_drop_reasons(row)
            reason_text = ",".join(reasons) if reasons else "DROP_RANK_BELOW_WATCHLIST"
            print(f"[SCANNER][DROP] symbol={row.symbol} reason={reason_text}")

    @staticmethod
    def _infer_drop_reasons(row: CandidateMetrics) -> list[str]:
        if not row.gate_checks:
            return []
        failures = [name for name, passed in row.gate_checks.items() if not passed]
        return [f"GATE_FAIL:{name}" for name in failures]

    @staticmethod
    def _fmt(value: float | None) -> str:
        if value is None:
            return "NA"
        return f"{value:.2f}"

    @staticmethod
    def _fmt_int(value: int | float | None) -> str:
        if value is None:
            return "NA"
        try:
            return str(int(value))
        except (TypeError, ValueError):
            return "NA"
