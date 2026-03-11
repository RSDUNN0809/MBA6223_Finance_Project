"""
ml_model.py — Trend-informed signal model.

Trains a logistic-regression classifier on the relationship between Google
Trends features and 3-month price return labels, then predicts a directional
vote for each ticker:

    +1  bullish  — rising, above-average search interest
     0  neutral  — mixed / inconclusive signal
    -1  bearish  — falling, below-average search interest

If fewer than MIN_TRAINING_SAMPLES labelled examples are available the model
falls back to a transparent rule-based scorer that uses the same features with
pre-defined weights derived from domain knowledge.

Typical usage
-------------
    from src.ml_model import get_model
    from src.trends import compute_trend_features

    features = compute_trend_features(trend_series)
    vote = get_model().predict_vote(features)   # +1 / 0 / -1
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

_LOG = logging.getLogger(__name__)

# Feature column order — must match trends.compute_trend_features output keys
_FEATURE_COLS = ["level_ratio", "slope_4w", "acceleration", "current_level"]

# Label thresholds on 3-month price return
_BULLISH_RETURN_THRESHOLD = 0.05   # +5 %
_BEARISH_RETURN_THRESHOLD = -0.05  # -5 %

_MIN_TRAINING_SAMPLES = 10  # fall back to rules below this


class TrendSignalModel:
    """
    Logistic-regression wrapper: Google Trends features → directional vote.

    The model is trained on demand using price-return labels derived from
    yfinance 3-month history.  When insufficient data is available it degrades
    gracefully to the rule-based fallback (still the same feature space, just
    with fixed analytical weights).
    """

    def __init__(self) -> None:
        self._pipeline: Optional[object] = None
        self._trained: bool = False

    # ── Training ──────────────────────────────────────────────────────────────

    def train(
        self,
        trend_features: dict[str, dict],  # ticker → feature dict
        price_returns: dict[str, float],  # ticker → 3-month return (decimal)
    ) -> None:
        """
        Fit the logistic regression on available aligned samples.

        Labels
        ------
        return > +5 %  → +1 (bullish)
        return < -5 %  → -1 (bearish)
        otherwise      →  0 (neutral)
        """
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            _LOG.warning("scikit-learn not installed — trend model unavailable.")
            return

        rows, labels = [], []
        for ticker, feats in trend_features.items():
            ret = price_returns.get(ticker)
            if ret is None:
                continue
            row   = [feats.get(c, 0.0) for c in _FEATURE_COLS]
            label = (
                 1 if ret >  _BULLISH_RETURN_THRESHOLD else
                -1 if ret <  _BEARISH_RETURN_THRESHOLD else
                 0
            )
            rows.append(row)
            labels.append(label)

        n = len(rows)
        if n < _MIN_TRAINING_SAMPLES:
            _LOG.warning(
                "Only %d samples — trend model will use rule-based fallback.", n
            )
            self._trained = False
            return

        X = np.array(rows,   dtype=float)
        y = np.array(labels, dtype=int)

        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf",    LogisticRegression(max_iter=500, C=1.0, multi_class="ovr")),
        ])
        pipeline.fit(X, y)
        self._pipeline = pipeline
        self._trained  = True
        _LOG.info("Trend model trained on %d samples.", n)

    # ── Prediction ────────────────────────────────────────────────────────────

    def predict_vote(self, features: dict) -> int:
        """Return +1 / 0 / −1 for the supplied trend feature dict."""
        if self._trained and self._pipeline is not None:
            row = np.array([[features.get(c, 0.0) for c in _FEATURE_COLS]])
            return int(self._pipeline.predict(row)[0])
        return _rule_based_vote(features)

    def predict_proba(self, features: dict) -> dict[int, float]:
        """
        Return probability estimates for each class.

        Returns
        -------
        dict mapping class label → probability, e.g.
            {1: 0.72, 0: 0.18, -1: 0.10}
        """
        if self._trained and self._pipeline is not None:
            row    = np.array([[features.get(c, 0.0) for c in _FEATURE_COLS]])
            probs  = self._pipeline.predict_proba(row)[0]
            classes = self._pipeline.named_steps["clf"].classes_
            return {int(c): float(p) for c, p in zip(classes, probs)}
        return _rule_based_proba(features)

    @property
    def is_trained(self) -> bool:
        return self._trained


# ── Rule-based fallback ───────────────────────────────────────────────────────

def _rule_based_proba(features: dict) -> dict[int, float]:
    """
    Convert the rule-based linear score to soft probability estimates using
    a pair of logistic (sigmoid) functions.

    A strongly positive score pushes p_bullish toward 1; strongly negative
    pushes p_bearish toward 1; near-zero leaves neutral dominant.
    """
    import math

    score = (
        (features.get("level_ratio",  1.0) - 1.0) * 2.0
        + features.get("slope_4w",     0.0)        * 3.0
        + features.get("acceleration", 0.0)        * 1.5
    )
    p_bull = 1.0 / (1.0 + math.exp(-2.0 * score))
    p_bear = 1.0 / (1.0 + math.exp( 2.0 * score))
    p_neut = max(0.0, 1.0 - p_bull - p_bear)
    total  = p_bull + p_bear + p_neut
    return {
         1: round(p_bull / total, 4),
         0: round(p_neut / total, 4),
        -1: round(p_bear / total, 4),
    }


def _rule_based_vote(features: dict) -> int:
    """
    Transparent, parameter-free fallback scorer.

    Weights
    -------
    level_ratio  : ×2.0  — above-average interest is mildly bullish
    slope_4w     : ×3.0  — rising trend is the strongest signal
    acceleration : ×1.5  — accelerating momentum adds confirmation

    Thresholds: score ≥ +0.5 → bullish, ≤ -0.5 → bearish.
    """
    score = (
        (features.get("level_ratio",  1.0) - 1.0) * 2.0
        + features.get("slope_4w",     0.0)        * 3.0
        + features.get("acceleration", 0.0)        * 1.5
    )
    if score >=  0.5:
        return  1
    if score <= -0.5:
        return -1
    return 0


# ── Module-level singleton ────────────────────────────────────────────────────

_MODEL = TrendSignalModel()


def get_model() -> TrendSignalModel:
    """Return the shared TrendSignalModel instance."""
    return _MODEL
