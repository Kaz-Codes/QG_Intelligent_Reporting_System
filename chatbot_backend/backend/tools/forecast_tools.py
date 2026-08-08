"""
Forecasting and trend maths - adaptive model selection.

The engine does NOT commit to one method. It builds a small bank of candidate
models, backtests each on a held-out tail of the series, and keeps the one with
the lowest error - then refits that model on the full series for the actual
projection. This means the SAME code:

  * uses a plain linear trend when history is short (a few months),
  * upgrades to SARIMA / Prophet once there are 2+ seasonal cycles (e.g. 2-3
    years of monthly data) and they actually backtest better,
  * uses Croston's method for intermittent (many-zero) per-item demand.

The heavy libraries (statsmodels, prophet) are lazy-imported inside their model
functions. If a library is missing, that candidate simply returns None and is
skipped - so the engine always works, and automatically gets stronger as data
and libraries become available.

The LLM never does any of this arithmetic - it decides *that* a forecast is
needed and on which columns; the maths here is deterministic and reproducible.
"""

import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from backend.config import ENABLE_PROPHET, FORECAST_SEASONAL_PERIODS

MIN_POINTS = 4          # below this, any trend line is noise
ARIMA_MIN_POINTS = 8    # enough to fit a non-seasonal ARIMA(p,d,q)
INTERMITTENT_ZERO_FRAC = 0.35   # >= this share of zero periods = intermittent
DAYS_PER_MONTH = 30.44  # average, for converting a monthly rate to a daily one
LONG_COVER_DAYS = 730   # beyond ~2 years of cover, a projected date is not a plan

# A model function: (values, steps, seasonal_periods) -> projections or None.
ModelFn = Callable[[List[float], int, int], Optional[List[float]]]

# Columns that identify a distinct series (an item, a branch, ...) - the exact
# vocabulary the SQL prompt already uses when it says to aggregate across
# these rather than break a series down by them. If one of these has more
# than one distinct value within the same period, the rows are an
# un-aggregated panel (multiple items/branches/etc.), not one series - see
# detect_panel(). An incidental column like a transaction/serial id is NOT in
# this set on purpose: multiple transaction rows in the same period for the
# SAME item are fine and expected to be summed, not flagged.
_GROUPING_COLUMNS = {
    "item_code", "item", "item_name", "branch", "supplier", "department",
    "customer", "item_category", "group_name",
}


# ======================================================================
#  Series preparation
# ======================================================================
def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def detect_panel(rows: List[Dict[str, Any]], period_column: str) -> Optional[Dict[str, Any]]:
    """
    None for a genuine single series; a description of the problem when the
    rows are actually a panel - more than one distinct item/branch/supplier/
    etc. sharing the same period, which a single trend cannot honestly be
    fitted across (it would silently blend distinct things together).
    """
    by_column: Dict[str, Dict[str, set]] = {}
    for row in rows:
        period = row.get(period_column)
        if period is None:
            continue
        period = str(period)
        for col in _GROUPING_COLUMNS:
            if col not in row:
                continue
            value = row.get(col)
            if value is None:
                continue
            by_column.setdefault(col, {}).setdefault(period, set()).add(value)

    for col, periods in by_column.items():
        distinct_in_a_period = max((len(vals) for vals in periods.values()), default=1)
        if distinct_in_a_period > 1:
            all_values = {v for vals in periods.values() for v in vals}
            return {"column": col, "distinct_count": len(all_values)}
    return None


def extract_series(
    rows: List[Dict[str, Any]], period_column: str, value_column: str
) -> Tuple[List[str], List[float]]:
    """
    Pull a clean (periods, values) series out of the query rows.

    Multiple transaction rows can legitimately share a period (several
    purchases in the same month for the same item), so periods repeat and get
    totalled here rather than treated as separate points. This assumes the
    rows are already ONE series - call detect_panel() first to catch rows
    that are actually several distinct items/branches/etc. sharing a period,
    which this function would otherwise blend together silently.
    """
    totals: Dict[str, float] = {}
    for row in rows:
        if period_column not in row or value_column not in row:
            continue
        value = _to_float(row[value_column])
        period = row[period_column]
        if value is None or period is None:
            continue
        key = str(period)
        totals[key] = totals.get(key, 0.0) + value

    periods = sorted(totals)  # ISO dates and YYYY-MM both sort correctly
    return periods, [totals[p] for p in periods]


def moving_average(values: List[float], window: int = 3) -> List[float]:
    if not values:
        return []
    return [
        float(np.mean(values[max(0, i - window + 1): i + 1]))
        for i in range(len(values))
    ]


def summarise_trend(periods: List[str], values: List[float]) -> Dict[str, Any]:
    """Plain descriptive stats, useful even when a projection is not warranted."""
    if not values:
        return {}
    y = np.asarray(values, dtype=float)
    first, last = values[0], values[-1]
    change_pct = round((last - first) / abs(first) * 100, 1) if first else None
    peak_i, trough_i = int(np.argmax(y)), int(np.argmin(y))
    return {
        "points": len(values),
        "first_period": periods[0] if periods else None,
        "last_period": periods[-1] if periods else None,
        "first_value": round(first, 2),
        "last_value": round(last, 2),
        "change_pct": change_pct,
        "average": round(float(y.mean()), 2),
        "peak": {"period": periods[peak_i] if periods else None, "value": round(float(y[peak_i]), 2)},
        "trough": {"period": periods[trough_i] if periods else None, "value": round(float(y[trough_i]), 2)},
        "moving_average_3": [round(v, 2) for v in moving_average(values, 3)],
    }


def _clip_nonneg(values) -> List[float]:
    """Quantities and money cannot go negative."""
    return [max(0.0, float(v)) for v in values]


# ======================================================================
#  Candidate models  (each returns projections, or None if it can't fit)
# ======================================================================
def _project_mean(values: List[float], steps: int, m: int = 12) -> Optional[List[float]]:
    if not values:
        return None
    return _clip_nonneg([float(np.mean(values))] * steps)


def _project_linear(values: List[float], steps: int, m: int = 12) -> Optional[List[float]]:
    n = len(values)
    if n < 2:
        return None
    x = np.arange(n, dtype=float)
    y = np.asarray(values, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    future = np.arange(n, n + steps, dtype=float)
    return _clip_nonneg(slope * future + intercept)


def _project_seasonal_naive(values: List[float], steps: int, m: int = 12) -> Optional[List[float]]:
    """Repeat the last full season - a strong, honest seasonal baseline."""
    if not m or len(values) < m:
        return None
    last_season = values[-m:]
    return _clip_nonneg([last_season[i % m] for i in range(steps)])


def _estimate_d(values: np.ndarray, max_d: int = 1) -> int:
    """
    0 or 1: does the series need first-differencing to look stationary?

    An Augmented Dickey-Fuller test on the raw series, then (if still
    non-stationary) on the once-differenced series. Business series here are
    short (12-36 points), so we cap at one difference - a second difference
    on that little data tends to just fit noise.
    """
    try:
        from statsmodels.tsa.stattools import adfuller
    except Exception:
        return 1  # ADF unavailable - 1 is the safer default for trending data

    series = values
    for d in range(max_d + 1):
        if len(series) < 4:
            return d
        try:
            pvalue = adfuller(series, autolag="AIC")[1]
        except Exception:
            return d
        if pvalue < 0.05:  # stationary at this differencing level
            return d
        series = np.diff(series)
    return max_d


def _search_arima_order(
    values: List[float], m: int, seasonal: bool
) -> Tuple[Tuple[int, int, int], Tuple[int, int, int, int]]:
    """
    Pick (p, d, q)(P, D, Q, m) for THIS series by AIC, instead of one fixed
    guess for every series.

    Differencing (d, D) is decided once via a stationarity test / a fixed
    seasonal default, then a small grid of AR/MA orders is fit and scored by
    AIC - the standard "test first, then search" approach (what
    statsmodels/pmdarima's auto_arima does). A seasonal fit is much more
    expensive than a non-seasonal one (the state vector is far larger), so
    the AR/MA range is narrower there to keep total search time reasonable
    for an interactive chat response: 9 fits non-seasonal, 16 seasonal.
    Convergence warnings are expected and ignored here - most of the grid is
    deliberately bad candidates, filtered out by the AIC comparison itself.
    """
    import warnings

    from statsmodels.tsa.statespace.sarimax import SARIMAX

    y = np.asarray(values, dtype=float)
    d = _estimate_d(y)
    D = 1 if seasonal else 0

    best_aic = float("inf")
    best_order = (1, d, 1)
    best_seasonal_order = (1, D, 0, m) if seasonal else (0, 0, 0, 0)

    pq_range = range(0, 2) if seasonal else range(0, 3)
    P_range = range(0, 2) if seasonal else (0,)
    Q_range = range(0, 2) if seasonal else (0,)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for p in pq_range:
            for q in pq_range:
                if p == 0 and q == 0 and d == 0:
                    continue  # a pure white-noise model tells us nothing useful
                for P in P_range:
                    for Q in Q_range:
                        order = (p, d, q)
                        seasonal_order = (P, D, Q, m) if seasonal else (0, 0, 0, 0)
                        try:
                            fit = SARIMAX(
                                y, order=order, seasonal_order=seasonal_order,
                                enforce_stationarity=False, enforce_invertibility=False,
                            ).fit(disp=False)
                        except Exception:
                            continue
                        if fit.aic < best_aic:
                            best_aic, best_order, best_seasonal_order = fit.aic, order, seasonal_order

    return best_order, best_seasonal_order


def _project_sarima(
    values: List[float],
    steps: int,
    m: int = 12,
    order: Optional[Tuple[int, int, int]] = None,
    seasonal_order: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[List[float]]:
    """
    Seasonal ARIMA via statsmodels. Seasonal terms only with >= 2 cycles.

    Pass `order`/`seasonal_order` to skip the search and fit directly (used
    by forecast(), which searches once on the full series and reuses the
    result for both the backtest fit and the final refit, rather than paying
    for the search twice). Searches for itself when called standalone.
    """
    n = len(values)
    if n < MIN_POINTS:
        return None
    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
    except Exception:
        return None

    seasonal = bool(m and n >= 2 * m)
    if order is None or seasonal_order is None:
        try:
            order, seasonal_order = _search_arima_order(values, m, seasonal)
        except Exception:
            order = (1, 1, 1)
            seasonal_order = (1, 1, 0, m) if seasonal else (0, 0, 0, 0)

    try:
        model = SARIMAX(
            np.asarray(values, dtype=float),
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        fit = model.fit(disp=False)
        return _clip_nonneg(fit.forecast(steps))
    except Exception:
        return None


def _project_prophet(
    values: List[float], steps: int, m: int = 12, periods: Optional[List[str]] = None
) -> Optional[List[float]]:
    """Facebook Prophet. Optional - skipped if disabled or not installed."""
    if not ENABLE_PROPHET or len(values) < MIN_POINTS:
        return None
    try:
        import pandas as pd
        from prophet import Prophet
    except Exception:
        return None
    try:
        if periods:
            ds = pd.to_datetime([str(p) for p in periods], errors="coerce")
        else:
            ds = pd.date_range(periods=len(values), freq="MS", end=pd.Timestamp.today().normalize())
        df = pd.DataFrame({"ds": ds, "y": values}).dropna()
        if len(df) < MIN_POINTS:
            return None
        model = Prophet(
            yearly_seasonality=(m == 12 and len(df) >= 2 * m),
            weekly_seasonality=False,
            daily_seasonality=False,
        )
        model.fit(df)
        future = model.make_future_dataframe(periods=steps, freq="MS")
        forecast_df = model.predict(future)
        return _clip_nonneg(forecast_df["yhat"].tail(steps).tolist())
    except Exception:
        return None


def _project_croston(values: List[float], steps: int, m: int = 12, alpha: float = 0.1) -> Optional[List[float]]:
    """Croston's method for intermittent demand: a constant future rate."""
    if sum(1 for v in values if v and v > 0) < 2:
        return None
    z = x = None          # demand-size and interval estimates
    gap = 1               # periods since last non-zero demand
    for v in values:
        if v and v > 0:
            if z is None:
                z, x = float(v), float(gap)
            else:
                z += alpha * (v - z)
                x += alpha * (gap - x)
            gap = 1
        else:
            gap += 1
    rate = (z / x) if (z is not None and x) else 0.0
    return _clip_nonneg([rate] * steps)


# ======================================================================
#  Backtesting + selection
# ======================================================================
def _mae(pred: List[float], actual: List[float]) -> float:
    p = np.asarray(pred, dtype=float)
    a = np.asarray(actual, dtype=float)
    return float(np.mean(np.abs(p - a)))


def _backtest(values: List[float], fn: ModelFn, h: int, m: int) -> Optional[float]:
    """Hold out the last h periods, fit on the rest, score the forecast."""
    train, test = values[:-h], values[-h:]
    if len(train) < 3:
        return None
    try:
        pred = fn(train, h, m)
    except Exception:
        return None
    if not pred or len(pred) < h:
        return None
    return _mae(pred[:h], test)


def _is_intermittent(values: List[float]) -> bool:
    if not values:
        return False
    zeros = sum(1 for v in values if not v or v == 0)
    return zeros / len(values) >= INTERMITTENT_ZERO_FRAC


def _candidate_models(n: int, m: int, intermittent: bool) -> List[Tuple[str, ModelFn]]:
    """Which models are worth trying for a series of this length/shape."""
    cands: List[Tuple[str, ModelFn]] = [
        ("mean baseline", _project_mean),
        ("linear trend", _project_linear),
    ]
    if m and n >= m + 2:
        cands.append(("seasonal naive", _project_seasonal_naive))
    if intermittent:
        cands.append(("Croston", _project_croston))

    # ARIMA only needs a short run to model trend + autocorrelation, and on a
    # real series it usually beats a flat mean - which is what a per-item
    # question (often ~10 months of history) would otherwise fall back to.
    # SEASONAL terms are a separate matter: they need 2 full cycles, and
    # _project_sarima decides that for itself, so the label follows suit rather
    # than claiming "SARIMA" when no seasonal term was actually fitted.
    if n >= ARIMA_MIN_POINTS:
        seasonal = bool(m and n >= 2 * m)
        cands.append(("SARIMA" if seasonal else "ARIMA", _project_sarima))

    # Prophet is slow to fit and is built around seasonality, so it stays gated
    # behind a longer history where it can actually earn its cost.
    if n >= max(int(1.5 * m), 12):
        cands.append(("Prophet", _project_prophet))
    return cands


def _confidence(best_err: float, values: List[float]) -> str:
    denom = float(np.mean(np.abs(values))) or 1.0
    rel = best_err / denom
    if rel < 0.15:
        return "high"
    if rel < 0.35:
        return "moderate"
    return "low"


def _select_and_forecast(
    values: List[float],
    steps: int,
    m: int,
    prophet_fn: Optional[ModelFn] = None,
    sarima_fn: Optional[ModelFn] = None,
) -> Dict[str, Any]:
    """
    Backtest the candidate models, keep the best, refit it on the full series.

    `prophet_fn` optionally overrides the default (dateless) Prophet with a
    date-aware one - the public forecast() passes the real periods through so
    Prophet can use them. `sarima_fn` similarly overrides SARIMA with one that
    reuses an order already searched once on the full series, rather than
    paying for a fresh order search on both the backtest fit and the refit.
    """
    n = len(values)
    if n < MIN_POINTS:
        return {"ok": False, "reason": f"Only {n} period(s); at least {MIN_POINTS} are needed."}

    intermittent = _is_intermittent(values)
    candidates = _candidate_models(n, m, intermittent)
    if prophet_fn is not None:
        candidates = [(name, prophet_fn if name == "Prophet" else fn) for name, fn in candidates]
    if sarima_fn is not None:
        # Non-seasonal series name this candidate "ARIMA" rather than "SARIMA"
        # (see _candidate_models) - both must reuse the pre-searched order.
        candidates = [
            (name, sarima_fn if name in ("SARIMA", "ARIMA") else fn) for name, fn in candidates
        ]

    # Hold out a sensible tail: up to `steps`, capped at 6 and a quarter of the
    # series so enough training data remains.
    h = max(1, min(steps, 6, n // 4))

    scored: List[Tuple[float, str, ModelFn]] = []
    for name, fn in candidates:
        err = _backtest(values, fn, h, m)
        if err is not None:
            scored.append((err, name, fn))

    if not scored:
        proj = _project_linear(values, steps, m) or _project_mean(values, steps, m)
        return {
            "ok": True,
            "method": "linear trend",
            "projections": [round(v, 2) for v in (proj or [])],
            "periods_ahead": steps,
            "confidence": "low",
            "note": "Not enough history to backtest; used a simple trend.",
        }

    scored.sort(key=lambda t: t[0])
    best_err, best_name, best_fn = scored[0]
    proj = best_fn(values, steps, m) or _project_linear(values, steps, m) or _project_mean(values, steps, m)

    return {
        "ok": True,
        "method": best_name,
        "projections": [round(v, 2) for v in (proj or [])[:steps]],
        "periods_ahead": steps,
        "confidence": _confidence(best_err, values),
        "backtest_mae": round(best_err, 2),
        "backtest_horizon": h,
        "models_compared": [{"model": name, "backtest_mae": round(err, 2)} for err, name, _ in scored],
        "seasonal_periods": m,
        "intermittent": intermittent,
        "history_points": n,
    }


# ======================================================================
#  Period labelling + public entry point
# ======================================================================
def _next_period_labels(periods: List[str], count: int) -> List[str]:
    """Label the projected points. Increment monthly when the periods are dates."""
    if periods:
        last = str(periods[-1])
        for fmt, cut in (("%Y-%m-%d", 10), ("%Y-%m", 7)):
            try:
                d = datetime.datetime.strptime(last[:cut], fmt).date()
                labels, y, mo = [], d.year, d.month
                for _ in range(count):
                    mo += 1
                    if mo > 12:
                        mo, y = 1, y + 1
                    labels.append(f"{y}-{mo:02d}")
                return labels
            except ValueError:
                continue
    return [f"period +{i + 1}" for i in range(count)]


def forecast(
    rows: List[Dict[str, Any]],
    period_column: str,
    value_column: str,
    periods_ahead: int = 3,
    seasonal_periods: int = FORECAST_SEASONAL_PERIODS,
) -> Dict[str, Any]:
    """
    Full forecast payload for the response agent.

    Always returns a dict. When the data does not support a projection, `ok` is
    False and `reason` explains why - the response agent passes that on rather
    than guessing.
    """
    panel = detect_panel(rows, period_column)
    if panel:
        return {
            "ok": False,
            "reason": (
                f"The rows have {panel['distinct_count']} different {panel['column']} "
                f"values sharing the same {period_column}, not one aggregated series - "
                "a trend cannot be fitted across distinct items/branches/etc. mixed "
                "together. Ask about one of them specifically, or a total across all "
                "of them."
            ),
        }

    periods, values = extract_series(rows, period_column, value_column)
    if not values:
        return {
            "ok": False,
            "reason": (
                f"Could not read a numeric series from columns "
                f"'{period_column}' / '{value_column}'."
            ),
        }

    result: Dict[str, Any] = {
        "period_column": period_column,
        "value_column": value_column,
        "history": summarise_trend(periods, values),
    }

    # Prophet does better with the real dates; give it the periods it fit on.
    def _prophet_with_dates(vals, steps, m):
        return _project_prophet(vals, steps, m, periods=periods[-len(vals):] if periods else None)

    # Search the ARIMA order once, on the full series (the most information
    # available), and reuse it for both the backtest fit and the final refit -
    # searching fresh each time would double the cost for no real benefit,
    # since dropping a handful of points rarely changes the best order.
    arima_order = arima_seasonal_order = None
    seasonal_engaged = bool(seasonal_periods and len(values) >= 2 * seasonal_periods)
    try:
        arima_order, arima_seasonal_order = _search_arima_order(
            values, seasonal_periods, seasonal_engaged
        )
    except Exception:
        pass

    def _sarima_with_order(vals, steps, m):
        return _project_sarima(vals, steps, m, order=arima_order, seasonal_order=arima_seasonal_order)

    result.update(
        _select_and_forecast(
            values, periods_ahead, seasonal_periods,
            prophet_fn=_prophet_with_dates,
            sarima_fn=_sarima_with_order if arima_order else None,
        )
    )

    if result.get("ok"):
        result["projected_periods"] = _next_period_labels(periods, len(result.get("projections", [])))

        # A dormant item's series ends long before today, so projecting forward
        # from its LAST data point produces "future" periods that are already
        # in the past (history to Dec-2025, projected Jan-Mar 2026, today
        # Jul-2026). The numbers are right for the series; presenting them as
        # upcoming is not. Flag it so the answer says what the data actually
        # covers instead of quietly forecasting backwards.
        last_period = _parse_date(periods[-1]) if periods else None
        if last_period:
            today = datetime.date.today()
            months_stale = (today.year - last_period.year) * 12 + (
                today.month - last_period.month
            )
            result["history_ends"] = periods[-1]
            if months_stale >= 2:
                result["months_since_last_data"] = months_stale
                result["stale_warning"] = (
                    f"The most recent record for this series is {periods[-1]} - "
                    f"about {months_stale} months ago. The projected periods "
                    "continue from there, so they are NOT upcoming months: say "
                    "plainly that the data stops at that date and that a "
                    "current projection needs newer records."
                )
        if result.get("method") in ("SARIMA", "ARIMA") and arima_order:
            result["arima_order"] = arima_order
            result["arima_seasonal_order"] = arima_seasonal_order
    return result


def days_of_cover(available_qty: float, daily_consumption: float) -> Optional[float]:
    """
    How many days current stock lasts at the observed consumption rate.

    Returns None when consumption is zero - "infinite cover" is misleading; the
    honest answer is that the item is not moving.
    """
    if not daily_consumption or daily_consumption <= 0:
        return None
    return round(available_qty / daily_consumption, 1)


_MAX_PROJECTION_DAYS = 365 * 200  # 200 years - beyond this a date is meaningless


def _safe_date_add(base: datetime.date, days: float) -> Optional[datetime.date]:
    """
    base + days, clamped so it cannot overflow datetime.date.

    A slow-moving item (large stock, tiny burn rate) yields a days-of-cover in
    the millions, and datetime raises OverflowError past year 9999 - which would
    crash the whole request. Clamping keeps the calculation honest (the
    horizon_warning already tells the user the date is not a plan) instead of
    turning an extreme-but-valid number into an error.
    """
    try:
        clamped = max(-_MAX_PROJECTION_DAYS, min(float(days), _MAX_PROJECTION_DAYS))
        return base + datetime.timedelta(days=int(clamped))
    except (OverflowError, ValueError, TypeError):
        return None


def _parse_date(value: Any) -> Optional[datetime.date]:
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def purchase_timing_projection(
    monthly_consumption: List[float],
    purchase_events: List[Dict[str, Any]],
    total_issued: Optional[float] = None,
    recent_periods: int = 3,
    as_of: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    "When will I next have to purchase this item" answered from the item's OWN
    issuance and purchase behaviour - no current stock row required.

    Two independent signals, because either can be the honest one:

      DEPLETION  - how long the last purchased batch lasts at the recent burn
                   rate (batch qty / avg daily consumption). This is the signal
                   the user means by "from the trend of issuances".
      CADENCE    - the median gap between past purchase dates, i.e. how often
                   this item actually gets bought. A robust median is used, not
                   a mean, so one long pause does not distort it.

    Also reports `coverage_ratio` (purchased / issued over the same window).
    Well below 1 means local purchasing does NOT account for consumption - the
    item is largely supplied another way (e.g. imports), so a purchase date
    derived from purchases alone would understate reality. Surfacing that is
    the point; the caller states it rather than quietly projecting a wrong date.
    """
    as_of = as_of or datetime.date.today()
    result: Dict[str, Any] = {"as_of": as_of.isoformat(), "ok": False}

    dated = [
        (d, float(e.get("qty") or 0))
        for e in (purchase_events or [])
        if (d := _parse_date(e.get("purchase_date"))) is not None
    ]
    dated.sort(key=lambda t: t[0])

    if not monthly_consumption:
        result["reason"] = "No issuance history for this item."
        return result
    if not dated:
        result["reason"] = "No purchase history for this item."
        return result

    recent = monthly_consumption[-recent_periods:]
    daily_rate = float(np.mean(recent)) / DAYS_PER_MONTH
    result.update({
        "avg_monthly_consumption": round(float(np.mean(recent)), 2),
        "avg_daily_consumption": round(daily_rate, 2),
        "recent_months_used": len(recent),
        "purchase_events": len(dated),
        "first_purchase": dated[0][0].isoformat(),
        "last_purchase_date": dated[-1][0].isoformat(),
        "last_purchase_qty": round(dated[-1][1], 2),
        "days_since_last_purchase": (as_of - dated[-1][0]).days,
    })

    # CADENCE: median gap between distinct purchase dates.
    if len(dated) >= 2:
        gaps = [
            (dated[i][0] - dated[i - 1][0]).days
            for i in range(1, len(dated))
            if (dated[i][0] - dated[i - 1][0]).days > 0
        ]
        if gaps:
            median_gap = float(np.median(gaps))
            result["median_days_between_purchases"] = round(median_gap, 1)
            cadence_date = _safe_date_add(dated[-1][0], round(median_gap))
            if cadence_date:
                result["cadence_next_purchase_date"] = cadence_date.isoformat()

    # DEPLETION: how long the last batch covers at the recent burn rate.
    if daily_rate > 0 and dated[-1][1] > 0:
        cover_days = dated[-1][1] / daily_rate
        depletion_date = _safe_date_add(dated[-1][0], cover_days)
        result["last_batch_cover_days"] = round(cover_days, 1)
        if depletion_date:
            result["depletion_next_purchase_date"] = depletion_date.isoformat()
            result["overdue_days"] = max(0, (as_of - depletion_date).days)

    # Which date to lead with: depletion when we have it, else cadence.
    due = result.get("depletion_next_purchase_date") or result.get("cadence_next_purchase_date")
    if due:
        due_date = _parse_date(due)
        result["next_purchase_due"] = due
        result["is_overdue"] = bool(due_date and due_date <= as_of)
        result["ok"] = True

    # Does local purchasing actually account for consumption?
    total_purchased = sum(q for _, q in dated)
    result["total_purchased"] = round(total_purchased, 2)
    if total_issued:
        result["total_issued"] = round(float(total_issued), 2)
        ratio = total_purchased / float(total_issued) if total_issued else None
        if ratio is not None:
            result["coverage_ratio"] = round(ratio, 3)
            if ratio < 0.8:
                result["coverage_warning"] = (
                    f"Recorded purchases cover only {ratio:.0%} of what was issued, so "
                    "this item is largely supplied by another route (e.g. imports). A "
                    "purchase date based on purchase records alone understates the real "
                    "replenishment cycle."
                )
    return result


def reorder_projection(
    values: List[float],
    available_qty: Optional[float],
    lead_time_days: Optional[float],
    safety_days: Optional[float],
    recent_periods: int = 3,
    as_of: Optional[datetime.date] = None,
) -> Dict[str, Any]:
    """
    Answer "when will we run out / when must we reorder" from a monthly
    consumption series plus the planning parameters.

        reorder level  = avg daily consumption x (lead_time_days + safety_days)
        days of cover  = available_qty / avg daily consumption
        run-out date   = today + days of cover
        reorder-by     = when stock falls TO the reorder level, i.e.
                         (available_qty - reorder_level) / avg daily consumption

    Every input is optional because real data has gaps (an item with no stock
    row, or too little purchase history to observe a lead time; safety days
    have no source at all). Whatever can be computed is returned, and
    `missing` names what could not be - so the answer states the gap instead of
    inventing a date. Uses the RECENT burn rate (last `recent_periods` months)
    rather than the full-history average, which is what planners actually
    reorder against.
    """
    as_of = as_of or datetime.date.today()
    missing: List[str] = []

    # Coerce to numbers first: these come from the database (and, for a taught
    # mapping, possibly from text), so a numeric-looking STRING would otherwise
    # reach the arithmetic below - where '45' + '60' concatenates to '4560' and
    # then raises TypeError, failing the whole request.
    available_qty = _to_float(available_qty)
    lead_time_days = _to_float(lead_time_days)
    safety_days = _to_float(safety_days)

    if not values:
        missing.append("consumption history")
    if available_qty is None:
        missing.append("current stock")
    if lead_time_days is None:
        missing.append("lead time")
    if safety_days is None:
        missing.append("safety days")

    result: Dict[str, Any] = {"as_of": as_of.isoformat(), "missing": missing}

    if not values:
        result["ok"] = False
        return result

    recent = values[-recent_periods:] if len(values) >= recent_periods else values
    monthly_rate = float(np.mean(recent))
    daily_rate = monthly_rate / DAYS_PER_MONTH

    result.update({
        "recent_months_used": len(recent),
        "avg_monthly_consumption": round(monthly_rate, 2),
        "avg_daily_consumption": round(daily_rate, 2),
    })

    if lead_time_days is not None and safety_days is not None:
        result["reorder_level"] = round(daily_rate * (lead_time_days + safety_days), 2)
        result["lead_time_days"] = lead_time_days
        result["safety_days"] = safety_days

    if available_qty is None or daily_rate <= 0:
        # Cannot place it on a calendar without stock on hand or any movement.
        result["ok"] = False
        if daily_rate <= 0 and values:
            result["note"] = "No consumption recorded recently, so a run-out date is not meaningful."
        return result

    result["available_qty"] = available_qty
    cover = days_of_cover(available_qty, daily_rate)
    result["days_of_cover"] = cover
    if cover is not None:
        stockout = _safe_date_add(as_of, cover)
        if stockout:
            result["projected_stockout_date"] = stockout.isoformat()

    reorder_level = result.get("reorder_level")
    if reorder_level is not None:
        days_to_reorder = (available_qty - reorder_level) / daily_rate
        result["days_until_reorder_point"] = round(days_to_reorder, 1)
        if days_to_reorder <= 0:
            result["reorder_by_date"] = as_of.isoformat()
            result["action"] = (
                "Order now - stock is already at or below the reorder level."
            )
        else:
            reorder_by = _safe_date_add(as_of, days_to_reorder)
            if reorder_by:
                result["reorder_by_date"] = reorder_by.isoformat()
            result["action"] = "Raise the purchase by the reorder-by date above."

    # A very slow-moving item produces an arithmetically correct but useless
    # date (stock / a tiny burn rate can land decades out). Say "no purchase
    # needed in any practical horizon" instead of quoting a year like 2047 as
    # if it were a plan.
    if cover is not None and cover > LONG_COVER_DAYS:
        result["horizon_warning"] = (
            f"At the current burn rate this stock covers about "
            f"{cover / 365.25:.1f} years, so no purchase is needed in any "
            "practical planning horizon - the projected dates are far outside "
            "one and should be read as 'not required soon', not as a plan. "
            "Slow-moving stock like this is usually an overstock question, not "
            "a replenishment one."
        )

    result["ok"] = True
    return result
