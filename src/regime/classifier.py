from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from src.regime.baselines import BaselineStats
from src.regime.contracts import (
    FeatureVector,
    RegimeDataQualityFlag,
    RegimeEvidenceItem,
    RegimeLabel,
    RegimeSnapshot,
)


_SPREAD_BPS_HIGH = 120.0


@dataclass(frozen=True)
class RegimeClassifier:
    def classify(
        self,
        *,
        features: FeatureVector,
        baseline_stats: Dict[str, BaselineStats],
        data_quality_flags: List[RegimeDataQualityFlag],
        timestamp_utc: str | None,
    ) -> RegimeSnapshot:
        evidence: List[RegimeEvidenceItem] = []
        session = features.session

        if features.liquidity_thin_flag and session == "AFTER":
            evidence.append(
                _evidence_item(
                    "liquidity_thin_flag",
                    1.0,
                    0.0,
                    1.0,
                    "Thin liquidity in AFTER session",
                )
            )
            return RegimeSnapshot(
                label=RegimeLabel.AFTER_HOURS_THIN,
                confidence=0.9,
                session=session,
                features=features,
                evidence=evidence,
                data_quality_flags=data_quality_flags,
                baseline_stats=_baseline_payload(baseline_stats),
                timestamp_utc=timestamp_utc,
            )

        if features.pct_missing_prices > 0.5:
            evidence.append(
                _evidence_item(
                    "pct_missing_prices",
                    features.pct_missing_prices,
                    _baseline_mean(baseline_stats, "pct_missing_prices"),
                    -1.0,
                    "Missing price coverage exceeds 50%",
                )
            )
            return RegimeSnapshot(
                label=RegimeLabel.UNKNOWN,
                confidence=0.4,
                session=session,
                features=features,
                evidence=evidence,
                data_quality_flags=data_quality_flags,
                baseline_stats=_baseline_payload(baseline_stats),
                timestamp_utc=timestamp_utc,
            )

        if features.median_spread_bps is not None and features.median_spread_bps > _SPREAD_BPS_HIGH:
            evidence.append(
                _evidence_item(
                    "median_spread_bps",
                    features.median_spread_bps,
                    _baseline_mean(baseline_stats, "median_spread_bps"),
                    1.0,
                    "Spreads exceed high-risk threshold",
                )
            )
            return RegimeSnapshot(
                label=RegimeLabel.HIGH_VOL_RISK_OFF,
                confidence=0.7,
                session=session,
                features=features,
                evidence=evidence,
                data_quality_flags=data_quality_flags,
                baseline_stats=_baseline_payload(baseline_stats),
                timestamp_utc=timestamp_utc,
            )

        scores = {
            RegimeLabel.OPENING_MOMENTUM: _opening_momentum_score(features, baseline_stats),
            RegimeLabel.CHOP_LOW_VOL: _chop_low_vol_score(features, baseline_stats),
            RegimeLabel.TRENDING: _trending_score(features, baseline_stats),
            RegimeLabel.NEWS_DRIVEN: _news_driven_score(features, baseline_stats),
        }

        label = max(scores, key=scores.get)
        score = scores[label]
        confidence = _score_to_confidence(score)

        evidence.extend(_evidence_from_scores(features, baseline_stats))
        evidence = sorted(evidence, key=lambda item: abs(item.contribution), reverse=True)[:5]

        return RegimeSnapshot(
            label=label,
            confidence=confidence,
            session=session,
            features=features,
            evidence=evidence,
            data_quality_flags=data_quality_flags,
            baseline_stats=_baseline_payload(baseline_stats),
            timestamp_utc=timestamp_utc,
        )


def _baseline_payload(baseline_stats: Dict[str, BaselineStats]) -> Dict[str, Dict[str, float | None]]:
    return {name: stats.to_payload() for name, stats in baseline_stats.items()}


def _baseline_mean(baseline_stats: Dict[str, BaselineStats], key: str) -> float | None:
    stats = baseline_stats.get(key)
    if stats is None:
        return None
    return stats.rolling_mean


def _zscore(value: float | None, stats: BaselineStats | None) -> float:
    if value is None or stats is None:
        return 0.0
    mean = stats.rolling_mean
    std = stats.rolling_std
    if mean is None or std is None or std == 0:
        return 0.0
    return (value - mean) / std


def _opening_momentum_score(
    features: FeatureVector, baseline_stats: Dict[str, BaselineStats]
) -> float:
    if features.session != "REGULAR":
        return 0.0
    score = 0.0
    score += _zscore(features.median_gap_pct or 0.0, baseline_stats.get("median_gap_pct"))
    score += _zscore(features.median_rvol or 0.0, baseline_stats.get("median_rvol"))
    score += _zscore(
        features.range_expansion_proxy or 0.0,
        baseline_stats.get("range_expansion_proxy"),
    )
    return score


def _chop_low_vol_score(
    features: FeatureVector, baseline_stats: Dict[str, BaselineStats]
) -> float:
    score = 0.0
    score += -_zscore(
        features.return_volatility_proxy or 0.0,
        baseline_stats.get("return_volatility_proxy"),
    )
    score += -_zscore(
        features.median_spread_bps or 0.0,
        baseline_stats.get("median_spread_bps"),
    )
    score += -_zscore(
        features.median_rvol or 0.0,
        baseline_stats.get("median_rvol"),
    )
    return score


def _trending_score(
    features: FeatureVector, baseline_stats: Dict[str, BaselineStats]
) -> float:
    score = 0.0
    score += _zscore(
        features.top1_momentum_move_pct or 0.0,
        baseline_stats.get("top1_momentum_move_pct"),
    )
    score += _zscore(
        features.range_expansion_proxy or 0.0,
        baseline_stats.get("range_expansion_proxy"),
    )
    return score


def _news_driven_score(
    features: FeatureVector, baseline_stats: Dict[str, BaselineStats]
) -> float:
    return _zscore(
        features.news_density_proxy or 0.0,
        baseline_stats.get("news_density_proxy"),
    )


def _score_to_confidence(score: float) -> float:
    base = 0.5 + (score / 6.0)
    return max(0.05, min(0.95, round(base, 4)))


def _evidence_from_scores(
    features: FeatureVector, baseline_stats: Dict[str, BaselineStats]
) -> List[RegimeEvidenceItem]:
    items = []
    for feature_name, value in {
        "median_gap_pct": features.median_gap_pct,
        "median_rvol": features.median_rvol,
        "median_spread_bps": features.median_spread_bps,
        "top1_momentum_move_pct": features.top1_momentum_move_pct,
        "range_expansion_proxy": features.range_expansion_proxy,
        "return_volatility_proxy": features.return_volatility_proxy,
        "news_density_proxy": features.news_density_proxy,
    }.items():
        stats = baseline_stats.get(feature_name)
        contribution = _zscore(value or 0.0, stats)
        items.append(
            _evidence_item(
                feature_name,
                value,
                stats.rolling_mean if stats else None,
                contribution,
                "z-score vs baseline",
            )
        )
    return items


def _evidence_item(
    feature_name: str,
    value: float | None,
    baseline: float | None,
    contribution: float,
    note: str,
) -> RegimeEvidenceItem:
    return RegimeEvidenceItem(
        feature_name=feature_name,
        value=value,
        baseline=baseline,
        contribution=round(contribution, 4),
        note=note,
    )
