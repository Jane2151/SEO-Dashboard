"""Reusable Plotly figure builders. These take plain values in and return a
figure — no Streamlit calls here, so pages just do st.plotly_chart(fig)."""

import plotly.graph_objects as go


def trend_line_chart(x_values, y_values, title: str, y_title: str, invert_y: bool = False) -> go.Figure:
    """Line chart for one metric across uploaded periods.

    invert_y=True flips the y-axis so an upward-looking line always reads as
    'better' — used for average position, where a lower number is better.
    """
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x_values, y=y_values, mode="lines+markers"))
    fig.update_layout(title=title, xaxis_title="Period", yaxis_title=y_title)
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


def trend_line_chart_with_change_markers(x_values, y_values, title: str, y_title: str, changes, invert_y: bool = False) -> go.Figure:
    """Single-metric trend line with SEO Change Log entries overlaid as
    vertical markers — one dashed line per change date, spanning the full
    chart height, with a hoverable point showing the change's category and
    description. `changes` is an iterable of (date_str, entries) where
    entries is a list of {"category", "description"} dicts for every change
    recorded on that date, grouped so same-day changes share one marker
    instead of overlapping. Calling this once per metric (Clicks,
    Impressions, Average Position) with the same `changes` list and the same
    x_values keeps the marker at the same date lined up across all three
    charts. This is a visual reference only — it does not imply the change
    caused whatever the metric did afterward.
    """
    x_values = list(x_values)
    y_values = list(y_values)
    date_index = {x: i for i, x in enumerate(x_values)}

    fig = trend_line_chart(x_values, y_values, title, y_title, invert_y=invert_y)

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
                marker=dict(size=10, color="gray", symbol="diamond"),
                hovertext=hover_text,
                hoverinfo="text",
                name="SEO Change",
                showlegend=False,
            )
        )

    fig.update_layout(hovermode="x unified")
    return fig


def before_after_bar_chart(labels, before_values, after_values, title: str, y_title: str) -> go.Figure:
    """Grouped bar chart comparing two periods across one or more metrics."""
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Before", x=labels, y=before_values))
    fig.add_trace(go.Bar(name="After", x=labels, y=after_values))
    fig.update_layout(title=title, yaxis_title=y_title, barmode="group")
    return fig
