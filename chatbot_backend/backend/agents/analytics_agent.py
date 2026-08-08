"""
Analytics / Forecast agent - two nodes.

    analytics_agent : looks at the rows that came back and decides what kind of
                      analysis the answer needs, and whether a forecast is
                      justified at all
    forecast_agent  : runs the actual maths in backend/tools/forecast_tools.py

The LLM decides *whether* to forecast and *on which columns*; it never computes
the numbers. That keeps projections reproducible and stops the model inventing
a trend that is not in the data.
"""

from decimal import Decimal
from typing import List, Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.config import EFFORT_FAST, ENABLE_COMPUTE, structured_llm
from backend.prompts.analytics_prompt import (
    ANALYTICS_SYSTEM_PROMPT,
    build_analytics_prompt,
)
from backend.tools import forecast_tools
from backend.tools.postgres_tools import get_purchase_history, get_reorder_inputs


class ChartSpec(BaseModel):
    type: Literal["bar", "line", "pie"] = Field(description="Chart type.")
    x: str = Field(description="Category/time column (x-axis, or pie labels).")
    y: List[str] = Field(
        description="Numeric column(s) to plot - one for pie, one or more for bar/line, all on a COMPARABLE scale."
    )
    title: str = Field(default="", description="Short chart title.")


class AnalyticsDecision(BaseModel):
    analysis_type: Literal[
        "reporting", "aggregation", "trend", "forecast", "recommendation"
    ] = Field(description="What kind of analysis the answer needs.")
    forecast_needed: bool = Field(
        description="True only for a forward-looking question over a real time series."
    )
    period_column: Optional[str] = Field(
        default=None, description="Date/period column to forecast over."
    )
    value_column: Optional[str] = Field(
        default=None, description="Numeric column to project."
    )
    periods_ahead: int = Field(default=3, description="How many periods to project.")
    reorder_analysis: bool = Field(
        default=False,
        description=(
            "True when the user is asking WHEN to buy / reorder / replenish an "
            "item, or when it will run out or hit its reorder level - a question "
            "about TIMING, not just how much will be consumed. Requires a "
            "consumption series for a specific item."
        ),
    )
    needs_computation: bool = Field(
        default=False,
        description=(
            "True when answering needs a custom calculation over the rows that "
            "SQL did not already produce and a forecast does not cover - e.g. a "
            "correlation, variability/coefficient of variation, distribution, "
            "custom score or ranking by a derived measure. False when the rows "
            "already answer the question or a plain forecast covers it."
        ),
    )
    computation_task: Optional[str] = Field(
        default=None,
        description="If needs_computation, one line describing what to compute from the rows.",
    )
    charts: List["ChartSpec"] = Field(
        default_factory=list,
        description=(
            "Zero or more charts to draw from the rows. Empty unless the user "
            "explicitly asked for a chart/graph/plot. Use SEPARATE charts for "
            "measures on different scales - never one chart mixing them. See the "
            "chart rules."
        ),
    )
    focus_points: List[str] = Field(
        default_factory=list,
        description="Up to three concrete things the answer should call out.",
    )


# Words that mean this agent actually has a decision to make. Without one of
# these AND with only a handful of rows, every field it returns is the default,
# so the round-trip buys nothing.
_ANALYTICS_TRIGGER_WORDS = (
    "forecast", "predict", "project", "expect", "future", "next month",
    "next quarter", "next year", "trend", "run out", "stockout", "reorder",
    "replenish", "when will", "when should", "when do", "chart", "graph",
    "plot", "visuali", "correlat", "distribution", "variability", "compare",
    "recommend", "should we", "why",
)
_TRIVIAL_ROW_COUNT = 3


def _analytics_is_trivial(question: str, rows: list) -> bool:
    """
    True when the analytics call cannot change the outcome.

    A turn is 4-5 SEQUENTIAL model calls and latency is dominated by
    round-trips, so a call that can only return defaults is pure waiting. With
    a couple of rows and no forecast/chart/reorder intent in the question there
    is nothing for it to decide - the answer is 'report these rows'.
    """
    if len(rows) > _TRIVIAL_ROW_COUNT:
        return False
    lowered = (question or "").lower()
    return not any(word in lowered for word in _ANALYTICS_TRIGGER_WORDS)


def analytics_agent(state: dict) -> dict:
    rows = state.get("retrieved_data") or []

    # Nothing to analyse - skip the LLM call entirely.
    if not rows:
        return {"analysis_type": "reporting", "forecast_needed": False}

    question = state.get("rewritten_query") or state.get("user_query", "")
    columns = state.get("columns") or list(rows[0].keys())

    # Small result, no forecast/chart/reorder intent - nothing to decide, so
    # skip a full model round-trip and report the rows directly.
    if _analytics_is_trivial(question, rows):
        return {
            "analysis_type": "reporting",
            "forecast_needed": False,
            "needs_computation": False,
            "charts": [],
        }

    try:
        llm = structured_llm(AnalyticsDecision, effort=EFFORT_FAST)
        result = llm.invoke(
            [
                SystemMessage(content=ANALYTICS_SYSTEM_PROMPT),
                HumanMessage(
                    content=build_analytics_prompt(
                        question, columns, rows, state.get("row_count", len(rows))
                    )
                ),
            ]
        )
    except Exception:
        # Analysis is optional polish; the response agent can work without it.
        return {"analysis_type": "reporting", "forecast_needed": False}

    # Guard the model's own choice. It can ask for a forecast on columns that
    # do not exist, or on three data points. Count distinct periods rather than
    # rows, because a per-item-per-month panel has many rows but few periods.
    skipped_reason = ""
    needs_forecast = result.forecast_needed
    requested_periods = max(1, result.periods_ahead)
    effective_periods = min(requested_periods, 24)
    periods_note = ""

    if needs_forecast:
        if result.period_column not in columns or result.value_column not in columns:
            needs_forecast = False
            skipped_reason = "The query did not return a usable time series."
        else:
            distinct_periods = {
                row.get(result.period_column)
                for row in rows
                if row.get(result.period_column) is not None
            }
            if len(distinct_periods) < forecast_tools.MIN_POINTS:
                needs_forecast = False
                skipped_reason = (
                    f"Only {len(distinct_periods)} period(s) of history are "
                    f"available; at least {forecast_tools.MIN_POINTS} are needed "
                    "to project a trend."
                )
            else:
                # The user can ask for any horizon they want, but projecting
                # much further out than the available history is honestly
                # supportable - the number would look precise while meaning
                # little. Generous (up to half the history) rather than a flat
                # cap, capped at 24 periods (two years of monthly data) so a
                # request for, say, 10 years ahead on 3 years of history
                # cannot silently produce a number nobody should trust.
                period_cap = max(3, min(24, len(distinct_periods) // 2))
                effective_periods = min(requested_periods, period_cap)
                if effective_periods < requested_periods:
                    periods_note = (
                        f"You asked for {requested_periods} periods ahead, but "
                        f"only {effective_periods} are projected here - only "
                        f"{len(distinct_periods)} periods of history are "
                        "available, and forecasting much further than that "
                        "would not be reliable."
                    )

    # Forecast wins over computation when both look true - a projection is the
    # more specific path. Otherwise honour a computation request, unless the
    # code interpreter is disabled entirely.
    needs_computation = bool(
        ENABLE_COMPUTE and result.needs_computation and not needs_forecast
    )

    # Validate each chart against the columns actually returned - the model can
    # name a column that is not there. Drop bad specs rather than send them to
    # the UI. Cap the count so a request cannot spawn a wall of charts.
    charts = []
    for spec in (result.charts or [])[:4]:
        valid = _validate_chart(spec, columns, rows)
        if valid:
            charts.append(valid)

    focus_points = list(result.focus_points or [])
    if periods_note:
        focus_points.append(periods_note)

    return {
        "analysis_type": result.analysis_type,
        "focus_points": focus_points,
        "forecast_needed": needs_forecast,
        "forecast_skipped_reason": skipped_reason,
        "forecast_spec": {
            "period_column": result.period_column,
            "value_column": result.value_column,
            "periods_ahead": effective_periods,
            # "when do we reorder / when does it run out" - answered from stock,
            # lead time and purchase cadence, NOT from the projection. So it is
            # deliberately NOT gated on needs_forecast: an item with only one or
            # two months of issuance cannot be forecast, but its stock level,
            # lead time and last purchase date are still real and worth
            # reporting. Gating this on a successful forecast would make the
            # answer claim those inputs are "unavailable" without ever looking.
            "reorder_analysis": bool(result.reorder_analysis),
        },
        "needs_computation": needs_computation,
        "computation_task": result.computation_task or "",
        "charts": charts,
    }


def _is_plottable(column: str, rows: list) -> bool:
    """
    True only if the column holds NUMBERS - something with a magnitude that can
    be a bar height or a line height.

    Checking the column merely EXISTS is not enough. The model asked for
    `line x=etd y=[eta, eta_works]` on a consignment listing - three date
    columns, so the "value" plotted was an arrival date. That renders, and it
    is meaningless. Dates arrive as ISO strings once the rows are made
    JSON-safe, so an isinstance check rejects them; a numeric-looking string
    would also be rejected, which is the safe direction.
    """
    for row in rows:
        value = row.get(column)
        if value is None:
            continue
        return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
    return False  # every value NULL - nothing to plot


def _validate_chart(spec, columns, rows=()) -> dict:
    """Keep the chart only if its columns exist, and the series are numeric."""
    if spec.type not in ("bar", "line", "pie") or not spec.x or not spec.y:
        return {}
    if spec.x not in columns:
        return {}
    series = [col for col in spec.y if col in columns]
    # The y-axis must be a measure, not another label or date.
    if rows:
        series = [col for col in series if _is_plottable(col, rows)]
    if not series:
        return {}
    # A pie shows one series; extra columns would be meaningless.
    if spec.type == "pie":
        series = series[:1]
    return {
        "type": spec.type,
        "x": spec.x,
        "y": series,
        "title": spec.title or "",
    }


def forecast_agent(state: dict) -> dict:
    spec = state.get("forecast_spec") or {}
    rows = state.get("retrieved_data") or []

    result = forecast_tools.forecast(
        rows=rows,
        period_column=spec.get("period_column", ""),
        value_column=spec.get("value_column", ""),
        periods_ahead=spec.get("periods_ahead", 3),
    )

    out = {"forecast_result": result}

    # "When must we reorder / when does it run out" needs stock and lead time,
    # which the trend query cannot carry (it must return one row per period).
    # Look them up directly and compute the dates.
    if spec.get("reorder_analysis"):
        reorder = _reorder_for_item(state, rows, spec)
        if reorder:
            out["reorder_result"] = reorder

    # If the user asked for a chart (analytics populated `charts` from the same
    # explicit-request rule) and the projection succeeded, replace it with a
    # forecast chart that shows the actual history AND the projected points -
    # the plain rows chart would only show history.
    if result.get("ok") and state.get("charts"):
        chart = _build_forecast_chart(rows, spec, result)
        if chart:
            out["charts"] = [chart]

    return out


_PERIOD_NAME_HINTS = ("period", "month", "date", "week", "quarter", "year")


def _infer_period_column(rows: list) -> str:
    """The column holding the time period: by name first, then by parsing."""
    if not rows:
        return ""
    keys = list(rows[0].keys())
    for key in keys:
        if any(hint in key.lower() for hint in _PERIOD_NAME_HINTS):
            return key
    for key in keys:
        if forecast_tools._parse_date(rows[0].get(key)) is not None:
            return key
    return ""


def _infer_value_column(rows: list, period_col: str) -> str:
    """The numeric measure to consume - the first numeric non-period column."""
    if not rows:
        return ""
    for key, value in rows[0].items():
        if key == period_col:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return key
    return ""


def _reorder_for_item(state: dict, rows: list, spec: dict) -> dict:
    """Fetch stock/lead-time for the question's item and project the reorder date."""
    entities = state.get("entities") or {}
    item_code = (entities.get("item_code") or "").strip()
    if not item_code:
        # Without a specific item there is no single stock level to run out of.
        return {}

    # The analytics agent only names these columns when it asked for a forecast,
    # so on a short series (forecast impossible, reorder still meaningful) they
    # arrive as None - infer them from the rows rather than giving up, which
    # would wrongly report stock and lead time as "unavailable" without looking.
    period_col = spec.get("period_column") or _infer_period_column(rows)
    value_col = spec.get("value_column") or _infer_value_column(rows, period_col)

    _, values = forecast_tools.extract_series(rows, period_col or "", value_col or "")
    if not values:
        return {}

    inputs = get_reorder_inputs(item_code, branch=(entities.get("branch") or "").strip())
    projection = forecast_tools.reorder_projection(
        values=values,
        available_qty=inputs.get("available_qty"),
        lead_time_days=inputs.get("lead_time_days"),
        safety_days=inputs.get("safety_days"),
    )
    projection["item_code"] = item_code
    projection["uom"] = inputs.get("uom")
    projection["stock_by_branch"] = inputs.get("branches") or []

    # Purchase timing from the item's OWN issuance + purchase behaviour. This
    # needs no stock row, so it still answers "when must I buy this" for the
    # many items that have no stock snapshot - which is exactly where the
    # stock-based reorder calculation above goes silent.
    timing = forecast_tools.purchase_timing_projection(
        monthly_consumption=values,
        purchase_events=get_purchase_history(item_code),
        total_issued=sum(values),
    )
    if timing:
        projection["purchase_timing"] = timing
    return projection


def _build_forecast_chart(rows: list, spec: dict, result: dict) -> dict:
    """
    A line chart carrying its own data: the actual series over history, then a
    separate 'forecast' series continuing from the last actual point through the
    projected periods. Rendered by ChartView, which uses spec['data'] when present.
    """
    periods, values = forecast_tools.extract_series(
        rows, spec.get("period_column", ""), spec.get("value_column", "")
    )
    if not periods:
        return {}

    projections = result.get("projections") or []
    proj_periods = result.get("projected_periods") or [
        f"+{i + 1}" for i in range(len(projections))
    ]

    data = [{"period": p, "actual": round(v, 2), "forecast": None} for p, v in zip(periods, values)]
    if data:
        # Seed the forecast line at the last actual point so it connects visually.
        data[-1]["forecast"] = data[-1]["actual"]
    data += [{"period": fp, "actual": None, "forecast": fv} for fp, fv in zip(proj_periods, projections)]

    measure = spec.get("value_column", "value")
    method = result.get("method", "forecast")
    return {
        "type": "line",
        "x": "period",
        "y": ["actual", "forecast"],
        "title": f"{measure} — history & {method} forecast",
        "data": data,
    }
