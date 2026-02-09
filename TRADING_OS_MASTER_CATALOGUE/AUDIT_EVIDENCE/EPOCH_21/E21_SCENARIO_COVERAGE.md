# E21 Scenario Coverage

| Scenario ID | Description | Validations |
| --- | --- | --- |
| SCN_BULL_FLAG_COMPRESSION | Bull flag with compressing ranges. | compression_structure, detect_setup_family |
| SCN_GAP_AND_GO_BASIC | Gap up with bullish continuation and opening range break. | detect_setup_family, level_interaction, opening_range |
| SCN_HEAD_AND_SHOULDERS_BASIC | Head and shoulders baseline swing structure. | detect_setup_family, range_structure |
| SCN_LIQUIDITY_SWEEP_RECLAIM | Sweep and reclaim near demand zone. | detect_setup_family, zone_interaction |
| SCN_MODE_PARITY_SIM_PAPER_READONLY | Mode parity placeholder across SIM/PAPER/READ_ONLY/LIVE. | mode_parity_matrix |
| SCN_NO_TRADE_CONTEXT_VETO | No-trade context veto at portfolio normalisation. | no_trade_veto |
| SCN_PORTFOLIO_NON_INTERFERENCE | Portfolio arbitration does not mutate strategy signals. | non_interference |
| SCN_RANGE_BREAK_AND_FAIL | Range break and failure back into the band. | range_structure, detect_setup_family |
| SCN_VWAP_RECLAIM_BASIC | Price reclaims VWAP with steady bid. | detect_setup_family, vwap_structure |
