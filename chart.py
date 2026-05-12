"""
Plotly chart builder.
Takes a DataFrame + chart spec dict, builds a chart, saves it as PNG.
Fully schema-agnostic — driven entirely by the spec.

Bar chart behaviour:
  - Data spanning > 45 days  → resampled to monthly averages (grouped bars)
  - Data spanning 8-45 days  → resampled to weekly averages  (grouped bars)
  - Data spanning <= 7 days  → daily bars
"""

import os
import uuid
import pandas as pd
import plotly.graph_objects as go

COLORS    = ["#2563eb", "#f97316", "#16a34a", "#dc2626", "#9333ea", "#0891b2"]
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "outputs", "charts")


def build_chart(df: pd.DataFrame, spec: dict) -> str:
    """
    Build a Plotly chart and return the absolute path to the saved PNG.
    spec keys: entities, columns, chart_type, title
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    name_col  = _find_name_col(df)
    x_col     = _find_time_col(df)
    chart_type = spec["chart_type"].lower()

    # Filter to requested entities
    plot_df = df.copy()
    if spec.get("entities") and name_col:
        plot_df = plot_df[plot_df[name_col].isin(spec["entities"])]

    # Filter to last N days if the user specified a time range
    if spec.get("last_days") and x_col:
        plot_df[x_col] = pd.to_datetime(plot_df[x_col], errors="coerce")
        cutoff = plot_df[x_col].max() - pd.Timedelta(days=spec["last_days"])
        plot_df = plot_df[plot_df[x_col] >= cutoff]

    # If no specific entities were requested and there are many entities,
    # aggregate (mean) across all entities to keep the chart readable.
    if name_col and name_col in plot_df.columns and plot_df[name_col].nunique() > 3:
        if not spec.get("entities"):  # user didn't specify particular entities
            valid_y = [c for c in spec["columns"] if c in plot_df.columns]
            # Floor to day so misaligned timestamps across entities (e.g. 09:05 vs 09:10)
            # collapse into the same groupby key — produces clean daily points.
            plot_df[x_col] = pd.to_datetime(plot_df[x_col], errors="coerce").dt.floor("D")
            plot_df = (
                plot_df.groupby(x_col)[valid_y]
                .mean()
                .reset_index()
            )
            name_col = None   # no per-entity dimension anymore

    # For bar charts resample to a sensible frequency so bars are readable
    # _resample_for_bar returns data already sorted chronologically
    ordered_x = None
    if chart_type == "bar" and x_col:
        plot_df, x_col = _resample_for_bar(
            plot_df, x_col, spec["columns"], name_col,
            user_freq=spec.get("resample_freq"),
        )
        # Capture chronological order NOW before any further sorting
        ordered_x = list(dict.fromkeys(plot_df[x_col].tolist()))

    # Guard: skip chart if none of the requested columns exist in the data
    valid_cols = [c for c in spec["columns"] if c in plot_df.columns]
    if not valid_cols:
        raise ValueError(
            f"No matching columns found for chart '{spec.get('title', '')}'. "
            f"Requested: {spec['columns']}. "
            f"Available: {[c for c in plot_df.columns if c not in (x_col, name_col)]}"
        )

    fig = go.Figure()
    color_idx = 0

    for y_col in spec["columns"]:
        if y_col not in plot_df.columns:
            continue

        if name_col and name_col in plot_df.columns and plot_df[name_col].nunique() > 1:
            for entity in plot_df[name_col].unique():
                edf = plot_df[plot_df[name_col] == entity]
                # Only sort by datetime columns — never sort Period strings
                if x_col and pd.api.types.is_datetime64_any_dtype(edf.get(x_col, pd.Series())):
                    edf = edf.sort_values(x_col)
                fig.add_trace(_make_trace(
                    chart_type,
                    x=edf[x_col] if x_col else list(range(len(edf))),
                    y=edf[y_col],
                    name=f"{entity} — {y_col}",
                    color=COLORS[color_idx % len(COLORS)],
                ))
                color_idx += 1
        else:
            # Only sort by datetime — not by string Period
            if x_col and pd.api.types.is_datetime64_any_dtype(plot_df.get(x_col, pd.Series())):
                plot_df = plot_df.sort_values(x_col)
            fig.add_trace(_make_trace(
                chart_type,
                x=plot_df[x_col] if x_col else list(range(len(plot_df))),
                y=plot_df[y_col],
                name=y_col,
                color=COLORS[color_idx % len(COLORS)],
            ))
            color_idx += 1

    # categoryorder/categoryarray only makes sense for bar charts with string
    # period labels. For line/area charts (datetime x-axis), setting
    # categoryorder="array" with categoryarray=None whitelists zero categories
    # and silently hides all data points — so we omit these keys entirely.
    xaxis_cfg = dict(
        showgrid=False,
        linecolor="#d1d5db",
        tickfont=dict(size=12),
    )
    if ordered_x is not None:
        xaxis_cfg["categoryorder"] = "array"
        xaxis_cfg["categoryarray"] = ordered_x

    # Only add % suffix when all plotted columns are percentage-based metrics
    is_pct = all(
        "%" in c or "workload" in c.lower() or "pct" in c.lower() or "usage" in c.lower()
        for c in valid_cols
    )
    yaxis_cfg = dict(
        showgrid=True,
        gridcolor="#e5e7eb",
        gridwidth=0.5,
        linecolor="#d1d5db",
        tickfont=dict(size=12),
    )
    if is_pct:
        yaxis_cfg["ticksuffix"] = "%"

    fig.update_layout(
        # No internal title — the PDF section heading above the chart is the title
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial", size=13, color="#111827"),
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right",  x=1,
            font=dict(size=12),
        ),
        barmode="group",          # grouped bars side-by-side (not stacked)
        bargap=0.25,              # gap between month groups
        bargroupgap=0.05,         # gap between bars within a group
        xaxis=xaxis_cfg,
        yaxis=yaxis_cfg,
        margin=dict(l=60, r=40, t=40, b=60),
    )

    out_path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4().hex}.png")
    fig.write_image(out_path, format="png", width=1100, height=900, scale=2)
    return out_path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resample_for_bar(
    df: pd.DataFrame,
    x_col: str,
    y_cols: list[str],
    name_col: str | None,
    user_freq: str | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    Resample time-series data to a human-readable frequency for bar charts.
    user_freq: 'daily' | 'weekly' | 'monthly' | None (auto-infer from span).
    Returns (resampled_df, new_x_col_name).
    """
    df = df.copy()
    df[x_col] = pd.to_datetime(df[x_col], errors="coerce")
    df = df.dropna(subset=[x_col])

    span_days = (df[x_col].max() - df[x_col].min()).days

    # User-specified frequency takes priority; fall back to auto-inference
    _freq_map = {
        "daily":   ("D",  "%d %b"),
        "weekly":  ("W",  "W/C %d %b"),
        "monthly": ("ME", "%b %Y"),
    }
    if user_freq and user_freq.lower() in _freq_map:
        freq, fmt = _freq_map[user_freq.lower()]
    elif span_days > 45:
        freq, fmt = "ME", "%b %Y"       # Monthly — e.g. "Dec 2025"
    elif span_days > 7:
        freq, fmt = "W",  "W/C %d %b"  # Weekly
    else:
        freq, fmt = "D",  "%d %b"       # Daily

    valid_y = [c for c in y_cols if c in df.columns]
    group_cols = [name_col] if name_col and name_col in df.columns else []

    frames = []
    if group_cols:
        for entity, edf in df.groupby(name_col):
            resampled = (
                edf.set_index(x_col)[valid_y]
                .resample(freq).mean()
                .reset_index()
                .sort_values(x_col)          # sort chronologically before labelling
            )
            resampled["Period"] = resampled[x_col].dt.strftime(fmt)
            resampled[name_col] = entity
            frames.append(resampled)
        result = pd.concat(frames, ignore_index=True)
        # Sort ALL rows by the original datetime column so that months from
        # different entities appear in a single consistent chronological sequence.
        result = result.sort_values(x_col).reset_index(drop=True)
    else:
        resampled = (
            df.set_index(x_col)[valid_y]
            .resample(freq).mean()
            .reset_index()
            .sort_values(x_col)              # sort chronologically before labelling
        )
        resampled["Period"] = resampled[x_col].dt.strftime(fmt)
        result = resampled

    return result, "Period"


def _make_trace(chart_type: str, x, y, name: str, color: str):
    if chart_type == "bar":
        return go.Bar(
            x=x, y=y, name=name,
            marker=dict(color=color, line=dict(color="white", width=0.5)),
        )
    if chart_type == "area":
        return go.Scatter(
            x=x, y=y, name=name, mode="lines",
            line=dict(color=color, width=2.5),
            fill="tozeroy",
            fillcolor=f"rgba({_hex_to_rgb(color)},0.15)",
        )
    # Default: line
    return go.Scatter(
        x=x, y=y, name=name, mode="lines",
        line=dict(color=color, width=2.5),
    )


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return ",".join(str(int(h[i:i+2], 16)) for i in (0, 2, 4))


def _find_time_col(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col
        if any(k in col.lower() for k in ("time", "date", "stamp")):
            return col
    return None


def _find_name_col(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if col.lower() in ("name", "entity", "resource", "object"):
            return col
    return None
