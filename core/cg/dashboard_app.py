from __future__ import annotations

import argparse
import time
from pathlib import Path

import altair as alt
import streamlit as st

try:
    from cg.dashboard_data import (
        load_event_overview,
        load_memory_overview,
        load_policy_overview,
        load_reports_overview,
        load_workspace_overview,
    )
except ModuleNotFoundError as e:
    if e.name != "cg":
        raise
    from dashboard_data import (  # type: ignore
        load_event_overview,
        load_memory_overview,
        load_policy_overview,
        load_reports_overview,
        load_workspace_overview,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--chroma-dir", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--live", default="1")
    parser.add_argument("--refresh-seconds", default="5")
    parser.add_argument("--event-limit", default="5000")
    return parser.parse_args()


def _autorefresh(live: bool, refresh_seconds: int) -> None:
    if not live:
        return
    refresh_ms = max(1000, int(refresh_seconds) * 1000)
    st.markdown(
        f"""
        <script>
        setTimeout(function() {{ window.location.reload(); }}, {refresh_ms});
        </script>
        """,
        unsafe_allow_html=True,
    )


def _inject_brand_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
          --cad-bg: #050506;
          --cad-card: #0f1020;
          --cad-card-2: #15172a;
          --cad-text: #f3f4f6;
          --cad-subtle: #c2c6d0;
          --cad-muted: #9aa0ad;
          --cad-accent: #a78bfa;
          --cad-border: rgba(167, 139, 250, 0.35);
        }
        .stApp {
          background: radial-gradient(circle at 70% 20%, rgba(167,139,250,0.22), transparent 45%), var(--cad-bg);
          color: var(--cad-text);
          font-size: 17px;
        }
        h1, h2, h3, h4, h5, h6, p, label, span, div {
          color: var(--cad-text);
        }
        h1 {
          font-size: clamp(2rem, 2.8vw, 3rem) !important;
          letter-spacing: 0.2px;
        }
        h2 {
          font-size: clamp(1.35rem, 2vw, 2rem) !important;
        }
        [data-testid="stCaptionContainer"], .stCaption {
          color: var(--cad-subtle) !important;
          font-size: 1rem !important;
          line-height: 1.45;
        }
        .stAlert {
          background-color: var(--cad-card) !important;
          border: 1px solid var(--cad-border) !important;
          color: var(--cad-text) !important;
        }
        [data-testid="stMetric"] {
          background: linear-gradient(180deg, rgba(167,139,250,0.12), rgba(167,139,250,0.04));
          border: 1px solid var(--cad-border);
          border-radius: 12px;
          padding: 0.55rem 0.75rem 0.6rem 0.75rem;
        }
        [data-testid="stMetricLabel"] {
          color: var(--cad-subtle) !important;
          font-size: 1rem !important;
        }
        [data-testid="stMetricValue"] {
          color: var(--cad-text) !important;
          font-size: clamp(1.75rem, 2.4vw, 2.3rem) !important;
          font-weight: 700 !important;
        }

        /* JSON blocks: fix unreadable white background */
        [data-testid="stJson"] {
          background: var(--cad-card) !important;
          border: 1px solid var(--cad-border) !important;
          border-radius: 10px !important;
          padding: 0.5rem 0.5rem 0.35rem 0.5rem !important;
        }
        [data-testid="stJson"] * {
          background: transparent !important;
          color: var(--cad-text) !important;
          font-size: 0.98rem !important;
          line-height: 1.45 !important;
        }

        /* Dataframe/table readability */
        [data-testid="stDataFrame"] {
          background: var(--cad-card) !important;
          border: 1px solid var(--cad-border) !important;
          border-radius: 10px !important;
        }
        [data-testid="stDataFrame"] * {
          color: var(--cad-text) !important;
          font-size: 0.97rem !important;
        }
        [data-testid="stTable"] * {
          color: var(--cad-text) !important;
          font-size: 0.97rem !important;
        }

        /* Chart containers */
        [data-testid="stVegaLiteChart"],
        [data-testid="stPlotlyChart"] {
          background: var(--cad-card) !important;
          border: 1px solid var(--cad-border) !important;
          border-radius: 10px !important;
          padding: 0.35rem 0.35rem 0.25rem 0.35rem !important;
        }
        [data-testid="stVegaLiteChart"] canvas {
          background: var(--cad-card-2) !important;
          border-radius: 8px !important;
        }
        .vega-embed .vega-actions {
          display: none !important;
        }
        [data-testid="stElementToolbar"] {
          display: none !important;
        }

        /* Mobile accessibility spacing */
        @media (max-width: 900px) {
          .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
          }
          [data-testid="stMetricValue"] {
            font-size: 1.6rem !important;
          }
          [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 0.75rem !important;
          }
          [data-testid="column"] {
            min-width: 100% !important;
            flex: 1 1 100% !important;
          }
          [data-testid="stVegaLiteChart"] {
            min-height: 260px !important;
          }
        }
        @media (min-width: 901px) and (max-width: 1200px) {
          [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
          }
          [data-testid="column"] {
            min-width: calc(50% - 0.75rem) !important;
            flex: 1 1 calc(50% - 0.75rem) !important;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _bar_chart_from_dict(data: dict[str, int | float], *, y_title: str) -> alt.Chart:
    rows = [{"label": str(k), "value": float(v)} for k, v in (data or {}).items()]
    if not rows:
        rows = [{"label": "(none)", "value": 0.0}]
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color="#8b5cf6", cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(
                "label:N",
                sort=None,
                axis=alt.Axis(
                    title=None,
                    labelAngle=-90,
                    labelColor="#f3f4f6",
                    labelFontSize=13,
                    labelPadding=10,
                ),
            ),
            y=alt.Y(
                "value:Q",
                title=y_title,
                axis=alt.Axis(
                    titleColor="#f3f4f6",
                    titleFontSize=14,
                    labelColor="#f3f4f6",
                    labelFontSize=13,
                    grid=True,
                    gridColor="rgba(243, 244, 246, 0.16)",
                ),
            ),
            tooltip=[
                alt.Tooltip("label:N", title="Category"),
                alt.Tooltip("value:Q", title="Value"),
            ],
        )
        .configure_view(fill="#15172a", stroke="#312e81", cornerRadius=8)
        .configure_axis(domainColor="#4c1d95", tickColor="#4c1d95")
        .configure(background="transparent")
        .properties(height=300)
    )
    return chart


def main() -> None:
    args = _parse_args()
    workspace = Path(args.workspace).resolve()
    logs_dir = Path(args.logs_dir).resolve()
    chroma_dir = Path(args.chroma_dir).resolve()
    policy_path = Path(args.policy).resolve()
    live = str(args.live).strip() == "1"
    refresh_seconds = int(args.refresh_seconds)
    event_limit = int(args.event_limit)

    st.set_page_config(page_title="CAD Guardian Dashboard", layout="wide")
    _inject_brand_theme()
    st.title("CAD Guardian Live Dashboard")
    st.caption("Telemetry + memory + workspace + policy + report health")

    _autorefresh(live, refresh_seconds)
    if live:
        st.info(f"Live mode ON. Refresh every {refresh_seconds}s")

    t0 = time.perf_counter()
    event_data = load_event_overview(logs_dir, limit=event_limit)
    mem_data = load_memory_overview(chroma_dir)
    ws_data = load_workspace_overview(workspace)
    policy_data = load_policy_overview(policy_path)
    rep_data = load_reports_overview(workspace)
    elapsed = int((time.perf_counter() - t0) * 1000)

    summary = event_data["summary"]
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("Events", int(summary.get("events_total", 0)))
    kpi2.metric("LLM Used Rate", f"{float(summary.get('llm_used_rate', 0.0)) * 100:.1f}%")
    kpi3.metric("Memory Items", int(mem_data.get("items_total", 0)))
    kpi4.metric("Workspace Files", int(ws_data.get("files_total", 0)))
    kpi5.metric("Render ms", elapsed)

    st.subheader("Route and Outcome")
    c1, c2 = st.columns(2)
    c1.write("Route Distribution")
    c1.altair_chart(
        _bar_chart_from_dict(event_data["route_distribution"], y_title="events"),
        use_container_width=True,
    )
    c2.write("Outcome Distribution")
    c2.altair_chart(
        _bar_chart_from_dict(event_data["outcome_distribution"], y_title="events"),
        use_container_width=True,
    )

    st.subheader("Command Mix and Timing")
    c3, c4 = st.columns(2)
    c3.write("By Command")
    c3.altair_chart(
        _bar_chart_from_dict(summary.get("by_command") or {}, y_title="events"),
        use_container_width=True,
    )
    c4.write("Avg Duration (ms) by Command")
    c4.altair_chart(
        _bar_chart_from_dict(summary.get("avg_duration_ms_by_command") or {}, y_title="ms"),
        use_container_width=True,
    )

    st.subheader("Memory Health")
    m1, m2 = st.columns(2)
    m1.write("Memory By Kind")
    m1.altair_chart(
        _bar_chart_from_dict(mem_data.get("by_kind") or {}, y_title="items"),
        use_container_width=True,
    )
    m2.json(
        {
            "items_total": mem_data.get("items_total"),
            "oldest_ts_utc": mem_data.get("oldest_ts_utc"),
            "newest_ts_utc": mem_data.get("newest_ts_utc"),
            "status": mem_data.get("status"),
            "error": mem_data.get("error"),
        }
    )
    st.write("Recent Memory Items")
    st.dataframe(
        mem_data.get("latest_items") or [],
        use_container_width=True,
        height=320,
    )

    st.subheader("Workspace Health")
    w1, w2 = st.columns(2)
    w1.json(
        {
            "files_total": ws_data.get("files_total"),
            "dirs_total": ws_data.get("dirs_total"),
            "bytes_total": ws_data.get("bytes_total"),
            "changed_last_24h_total": ws_data.get("changed_last_24h_total"),
        }
    )
    w2.write("Top Extensions")
    w2.dataframe(
        ws_data.get("top_extensions") or [],
        use_container_width=True,
        height=300,
    )
    st.write("Largest Files")
    st.dataframe(
        ws_data.get("largest_files") or [],
        use_container_width=True,
        height=320,
    )

    st.subheader("Policy Posture")
    p1, p2 = st.columns(2)
    p1.json(
        {
            "command_allowlist_count": policy_data.get("command_allowlist_count"),
            "command_denylist_count": policy_data.get("command_denylist_count"),
            "denied_paths_count": policy_data.get("denied_paths_count"),
            "routing_controls": policy_data.get("routing_controls"),
        }
    )
    p2.json(
        {
            "execution_limits": policy_data.get("execution_limits"),
            "network_controls": policy_data.get("network_controls"),
        }
    )

    st.subheader("Report Artifacts")
    r1, r2 = st.columns(2)
    r1.json(
        {
            "ui_snapshot_runs_total": rep_data.get("ui_snapshot_runs_total"),
            "ui_snapshot_runs_latest": rep_data.get("ui_snapshot_runs_latest"),
        }
    )
    r2.json(
        {
            "metrics_runs_total": rep_data.get("metrics_runs_total"),
            "metrics_runs_latest": rep_data.get("metrics_runs_latest"),
        }
    )

    st.subheader("Latest Events")
    st.dataframe(
        event_data.get("latest_events") or [],
        use_container_width=True,
        height=360,
    )


if __name__ == "__main__":
    main()
