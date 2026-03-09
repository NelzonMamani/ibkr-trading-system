from src.scanner.session_pct_change import compute_phase_aware_rvol

for phase in ["PRE", "RTH_OPEN", "RTH_MID", "RTH_LATE", "AH", "OVN"]:
    payload = compute_phase_aware_rvol(
        session_label=phase,
        session_volume=50_000,
        avg_volume_20d=1_000_000,
    )
    print(
        f"phase={phase} ratio={payload.phase_ratio} expected_phase_volume={payload.expected_phase_volume} "
        f"rvol_phase={payload.rvol_phase}"
    )
