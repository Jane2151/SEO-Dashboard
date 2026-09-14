"""Reusable Plotly figure builders. These take plain values in and return a
figure — no Streamlit calls here, so pages just do st.plotly_chart(fig)."""

import math

import plotly.graph_objects as go

# Shared per-metric colors so Clicks/Impressions read as the same metric
# whether they're plotted alone or together in clicks_impressions_dual_axis_chart.
CLICKS_COLOR = "#1f77b4"
IMPRESSIONS_COLOR = "#9467bd"


def _nice_axis_ticks(max_val, n_ticks: int = 6) -> list:
    """n_ticks evenly-spaced round values from 0 up to at least max_val
    (e.g. 0, 5, 10, 15... rather than an arbitrary decimal step), using the
    standard 1/2/2.5/5/10-per-decade 'nice number' rounding. Used to give
    two independent y-axes the same tick *count* over a 0..max range, so
    their gridlines land on the same rows despite plotting different-scale
    metrics — see clicks_impressions_dual_axis_chart.
    """
    if max_val <= 0:
        max_val = 1
    raw_step = max_val / (n_ticks - 1)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    step = 10 * magnitude
    for mult in (1, 2, 2.5, 5, 10):
        candidate = mult * magnitude
        if candidate * (n_ticks - 1) >= max_val:
            step = candidate
            break
    return [round(step * i, 10) for i in range(n_ticks)]


def trend_line_chart(
    x_values,
    y_values,
    title: str,
    y_title: str,
    invert_y: bool = False,
    show_x_labels: bool = True,
    x_range=None,
    dark_mode: bool = False,
    line_color: str | None = None,
) -> go.Figure:
    """Line chart for one metric across uploaded periods.

    invert_y=True flips the y-axis so an upward-looking line always reads as
    'better' — used for average position, where a lower number is better.

    show_x_labels=False hides the x-axis's tick labels/title — used to stack
    two charts (e.g. Impressions above Clicks) without repeating the same
    date axis twice. x_range, when given, is applied as an explicit x-axis
    range so two charts built from the same dates line up exactly rather
    than relying on their autoranges happening to agree. Margins are fixed
    (not auto-sized to tick label width) for the same reason: two stacked
    charts with different y-value digit counts would otherwise get slightly
    different left offsets and no longer align vertically.

    dark_mode picks a white-based (vs. black-based) gridline tint — a
    black gridline at low opacity is essentially invisible against
    Streamlit's dark theme background, so this can't be one fixed color.
    """
    gridcolor = "rgba(255, 255, 255, 0.18)" if dark_mode else "rgba(0, 0, 0, 0.08)"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=y_values,
            mode="lines+markers",
            name=y_title,
            line=dict(color=line_color) if line_color else None,
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Date" if show_x_labels else None,
        yaxis_title=y_title,
        showlegend=False,
        margin=dict(l=60, r=20, t=40, b=55 if show_x_labels else 10),
        transition=dict(duration=500, easing="cubic-in-out"),
    )
    fig.update_xaxes(showgrid=False, showticklabels=show_x_labels, ticks="outside" if show_x_labels else "", automargin=False)
    fig.update_yaxes(showgrid=True, gridcolor=gridcolor, zeroline=False, automargin=False, ticklabelposition="outside", tickfont=dict(size=12))
    if x_range is not None:
        fig.update_xaxes(range=x_range)
    if invert_y:
        fig.update_yaxes(autorange="reversed")
    return fig


def trend_line_chart_with_markers(x_values, y_values, title: str, y_title: str, markers=None, invert_y: bool = False) -> go.Figure:
    """Trend line chart with optional vertical marker lines overlaid — e.g.
    SEO change log dates on a page's performance history. `markers` is an
    iterable of (x_value, label) pairs; x_value must be on the same axis
    type as x_values (e.g. both ISO date strings) so it aligns correctly.
    """
    fig = trend_line_chart(x_values, y_values, title, y_title, invert_y=invert_y)
    for x_value, label in markers or []:
        fig.add_vline(x=x_value, line_dash="dash", line_color="gray", annotation_text=label, annotation_position="top")
    return fig


def trend_line_chart_with_change_markers(
    x_values,
    y_values,
    title: str,
    y_title: str,
    changes,
    invert_y: bool = False,
    show_x_labels: bool = True,
    x_range=None,
    dark_mode: bool = False,
    line_color: str | None = None,
) -> go.Figure:
    """Single-metric trend line with SEO Change Log entries overlaid as
    vertical markers — one thin dashed line per change date, spanning the
    full chart height, with a small hoverable point showing the change's
    category and description (no permanent text label). `changes` is an
    iterable of (date_str, entries) where entries is a list of
    {"category", "description"} dicts for every change recorded on that
    date, grouped so same-day changes share one marker instead of
    overlapping. Calling this once per metric with the same `changes` list,
    the same x_values, and the same x_range keeps the marker at the same
    date lined up across charts. This is a visual reference only — it does
    not imply the change caused whatever the metric did afterward.
    """
    x_values = list(x_values)
    y_values = list(y_values)
    date_index = {x: i for i, x in enumerate(x_values)}

    fig = trend_line_chart(
        x_values,
        y_values,
        title,
        y_title,
        invert_y=invert_y,
        show_x_labels=show_x_labels,
        x_range=x_range,
        dark_mode=dark_mode,
        line_color=line_color,
    )

    for change_date, entries in changes:
        fig.add_shape(
            type="line",
            xref="x",
            yref="paper",
            x0=change_date,
            x1=change_date,
            y0=0,
            y1=1,
            line=dict(color="gray", dash="dash", width=1),
        )

        idx = date_index.get(change_date)
        if idx is None:
            continue

        entry_lines = [f"<b>{entry['category']}</b><br>{entry['description'] or ''}" for entry in entries]
        hover_text = f"<b>{change_date}</b><br>" + "<br><br>".join(entry_lines)

        fig.add_trace(
            go.Scatter(
                x=[change_date],
                y=[y_values[idx]],
                mode="markers",
                marker=dict(size=6, color="gray", symbol="circle"),
                hovertext=hover_text,
                hoverinfo="text",
                name="SEO Change",
                showlegend=False,
            )
        )

    fig.update_layout(hovermode="x unified")
    return fig


def clicks_impressions_dual_axis_chart(
    x_values, clicks_values, impressions_values, changes=None, x_range=None, dark_mode: bool = False
) -> go.Figure:
    """Clicks and Impressions together on one chart: same x-axis dates, but
    each metric keeps its own independent y-axis (Clicks on the left,
    Impressions on the right) so neither is rescaled to fit the other's
    range. Axis identity is shown via small colored labels in the top
    corners (matching each line's color) instead of legend entries or
    rotated axis titles, since a legend/vertical title would repeat
    information the corner labels already make clear at a glance.

    dark_mode picks a white-based (vs. black-based) gridline tint — a
    black gridline at low opacity is essentially invisible against
    Streamlit's dark theme background, so this can't be one fixed color.
    """
    gridcolor = "rgba(255, 255, 255, 0.22)" if dark_mode else "rgba(0, 0, 0, 0.12)"

    x_values = list(x_values)
    clicks_values = list(clicks_values)
    impressions_values = list(impressions_values)

    # Both axes get the same number of ticks over a 0..max range, so tick i
    # sits at the same fractional height on both axes (i / (n_ticks - 1))
    # regardless of Clicks and Impressions being on totally different
    # scales. Only the Clicks (primary) axis draws gridlines, but because
    # the two tick sets share that fractional spacing, each gridline row
    # lines up with both a Clicks value and an Impressions value — same
    # idea as Search Console's own combined chart.
    clicks_ticks = _nice_axis_ticks(max(clicks_values) if clicks_values else 0)
    impressions_ticks = _nice_axis_ticks(max(impressions_values) if impressions_values else 0)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=clicks_values,
            mode="lines",
            name="Clicks",
            line=dict(color=CLICKS_COLOR, width=2),
            yaxis="y1",
            hovertemplate="Clicks: %{y:,}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=impressions_values,
            mode="lines",
            name="Impressions",
            line=dict(color=IMPRESSIONS_COLOR, width=2),
            yaxis="y2",
            hovertemplate="Impressions: %{y:,}<extra></extra>",
        )
    )

    fig.update_layout(
        showlegend=False,
        hovermode="x unified",
        margin=dict(l=60, r=60, t=50, b=55),
        transition=dict(duration=500, easing="cubic-in-out"),
        xaxis=dict(title="Date", showgrid=False, ticks="outside", automargin=False),
        yaxis=dict(
            tickmode="array",
            tickvals=clicks_ticks,
            range=[clicks_ticks[0], clicks_ticks[-1]],
            showgrid=True,
            gridcolor=gridcolor,
            zeroline=False,
            tickfont=dict(color=CLICKS_COLOR),
            automargin=False,
        ),
        yaxis2=dict(
            tickmode="array",
            tickvals=impressions_ticks,
            range=[impressions_ticks[0], impressions_ticks[-1]],
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=False,
            tickfont=dict(color=IMPRESSIONS_COLOR),
            automargin=False,
        ),
        annotations=[
            dict(text="Clicks", xref="paper", yref="paper", x=0, y=1.1, xanchor="left", showarrow=False, font=dict(color=CLICKS_COLOR, size=13)),
            dict(text="Impressions", xref="paper", yref="paper", x=1, y=1.1, xanchor="right", showarrow=False, font=dict(color=IMPRESSIONS_COLOR, size=13)),
        ],
    )

    if x_range is not None:
        fig.update_xaxes(range=x_range)

    date_index = {x: i for i, x in enumerate(x_values)}
    for change_date, entries in changes or []:
        fig.add_shape(
            type="line",
            xref="x",
            yref="paper",
            x0=change_date,
            x1=change_date,
            y0=0,
            y1=1,
            line=dict(color="gray", dash="dash", width=1),
        )

        idx = date_index.get(change_date)
        if idx is None:
            continue

        entry_lines = [f"<b>{entry['category']}</b><br>{entry['description'] or ''}" for entry in entries]
        hover_text = f"<b>{change_date}</b><br>" + "<br><br>".join(entry_lines)

        fig.add_trace(
            go.Scatter(
                x=[change_date],
                y=[clicks_values[idx]],
                mode="markers",
                marker=dict(size=6, color="gray", symbol="circle"),
                hovertext=hover_text,
                hoverinfo="text",
                name="SEO Change",
                yaxis="y1",
                showlegend=False,
            )
        )

    return fig


def before_after_bar_chart(labels, before_values, after_values, title: str, y_title: str) -> go.Figure:
    """Grouped bar chart comparing two periods across one or more metrics."""
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Before", x=labels, y=before_values))
    fig.add_trace(go.Bar(name="After", x=labels, y=after_values))
    fig.update_layout(title=title, yaxis_title=y_title, barmode="group")
    return fig
