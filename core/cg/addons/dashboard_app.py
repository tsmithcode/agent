from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

try:
    from cg.data.env import get_openai_api_key, load_project_dotenv
    from cg.addons.dashboard_data import (
        load_event_overview,
        load_memory_overview,
        load_policy_overview,
        load_reports_overview,
        summarize_user_goal_from_memories,
        load_workspace_overview,
    )
except ModuleNotFoundError as e:
    if e.name != "cg":
        raise
    core_root = Path(__file__).resolve().parents[2]
    if str(core_root) not in sys.path:
        sys.path.insert(0, str(core_root))
    from cg.data.env import get_openai_api_key, load_project_dotenv  # type: ignore
    from cg.addons.dashboard_data import (  # type: ignore
        load_event_overview,
        load_memory_overview,
        load_policy_overview,
        load_reports_overview,
        summarize_user_goal_from_memories,
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
          overflow: hidden !important;
        }
        [data-testid="stDataFrame"] * {
          color: var(--cad-text) !important;
          font-size: 0.97rem !important;
        }
        [data-testid="stDataFrame"] [class*="glideDataEditor"] {
          --gdg-bg-cell: #0f1020;
          --gdg-bg-cell-medium: #13152a;
          --gdg-bg-header: #1a1d38;
          --gdg-text-dark: #f3f4f6;
          --gdg-text-medium: #d5d8e3;
          --gdg-accent-color: #a78bfa;
          --gdg-horizontal-border-color: rgba(167, 139, 250, 0.22);
          --gdg-vertical-border-color: rgba(167, 139, 250, 0.16);
          --gdg-selection-color: rgba(167, 139, 250, 0.24);
        }
        [data-testid="stDataFrame"] [class*="gdg-header"] {
          background: #1a1d38 !important;
          color: #f3f4f6 !important;
          font-weight: 700 !important;
          font-size: 0.98rem !important;
          border-bottom: 1px solid var(--cad-border) !important;
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


def _bar_chart_from_dict(data: dict[str, int | float], *, y_title: str, max_label_chars: int = 18) -> alt.Chart:
    def _short(s: str, n: int = 18) -> str:
        return s if len(s) <= n else (s[: n - 1] + "…")

    rows = [{"label": str(k), "label_short": _short(str(k), max_label_chars), "value": float(v)} for k, v in (data or {}).items()]
    if not rows:
        rows = [{"label": "(none)", "label_short": "(none)", "value": 0.0}]
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color="#8b5cf6", cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(
                "label_short:N",
                sort=None,
                axis=alt.Axis(
                    title=None,
                    labelAngle=0,
                    labelColor="#f3f4f6",
                    labelFontSize=13,
                    labelPadding=10,
                    labelLimit=170,
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
                alt.Tooltip("label_short:N", title="Shown Label"),
                alt.Tooltip("value:Q", title="Value"),
            ],
        )
        .configure_view(fill="#15172a", stroke="#312e81", cornerRadius=8)
        .configure_axis(domainColor="#4c1d95", tickColor="#4c1d95")
        .configure(background="transparent")
        .properties(height=300)
    )
    return chart


def _needs_full_row(data: dict[str, int | float], *, max_label_chars: int = 18) -> bool:
    labels = [str(k) for k in (data or {}).keys()]
    if not labels:
        return False
    return any(len(lbl) > max_label_chars for lbl in labels) or len(labels) > 8


def _to_df(rows: list[dict[str, object]] | dict[str, object] | list[object] | None) -> pd.DataFrame:
    if rows is None:
        return pd.DataFrame()
    if isinstance(rows, dict):
        return pd.DataFrame([rows])
    if isinstance(rows, list):
        if not rows:
            return pd.DataFrame()
        if isinstance(rows[0], dict):
            return pd.DataFrame(rows)
        return pd.DataFrame({"value": rows})
    return pd.DataFrame([{"value": rows}])


def _to_mb(size_bytes: object) -> str:
    try:
        size = float(size_bytes)
    except (TypeError, ValueError):
        return str(size_bytes)
    return f"{(size / (1024 * 1024)):,.2f} MB"


def _humanize_key(name: object) -> str:
    raw = str(name or "")
    overrides = {
        "ts_utc": "Timestamp (UTC)",
        "oldest_ts_utc": "Oldest Timestamp (UTC)",
        "newest_ts_utc": "Newest Timestamp (UTC)",
        "duration_ms": "Duration (ms)",
        "llm_used": "LLM Used",
        "size_mb": "Size (MB)",
    }
    if raw in overrides:
        return overrides[raw]
    return raw.replace("_", " ").strip().title()


def _humanize_value(key: str, value: object) -> object:
    if value is None:
        return ""
    key_l = key.lower()
    if key_l in {"bytes", "bytes_total"}:
        return _to_mb(value)
    if key_l.endswith("_ms"):
        try:
            return f"{int(value):,} ms"
        except (TypeError, ValueError):
            return str(value)
    if key_l == "llm_used" and isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return value


def _humanize_dict_for_json(data: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out[_humanize_key(key)] = _humanize_dict_for_json(value)
            continue
        if isinstance(value, list):
            out[_humanize_key(key)] = [(_humanize_dict_for_json(v) if isinstance(v, dict) else v) for v in value]
            continue
        out[_humanize_key(key)] = _humanize_value(str(key), value)
    return out


def _largest_files_rows_with_units(rows: list[dict[str, object]] | None) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in rows or []:
        formatted = dict(row)
        if "bytes" in formatted:
            formatted["size_mb"] = _to_mb(formatted.pop("bytes"))
        out.append(formatted)
    return out


def _show_scroll_table(rows: list[dict[str, object]] | dict[str, object] | list[object] | None, *, height: int) -> None:
    df = _to_df(rows).copy()
    if not df.empty:
        source_columns = list(df.columns)
        for col in source_columns:
            df[col] = df[col].map(lambda v, k=str(col): _humanize_value(k, v))
        df = df.rename(columns={col: _humanize_key(col) for col in source_columns})
    st.dataframe(df, use_container_width=True, height=height, hide_index=True)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_goal_summary(chroma_dir: str, api_key: str, cache_key: str) -> dict[str, object]:
    return summarize_user_goal_from_memories(
        Path(chroma_dir),
        openai_api_key=(api_key or None),
    )


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
    load_project_dotenv()
    _inject_brand_theme()
    st.title("CAD Guardian Live Dashboard")
    st.caption("Telemetry + memory + workspace + policy + report health")
    st.caption("Ownership: CAD Guardian brand product.")

    _autorefresh(live, refresh_seconds)
    if live:
        st.info(f"Live mode ON. Refresh every {refresh_seconds}s")

    t0 = time.perf_counter()
    event_data = load_event_overview(logs_dir, limit=event_limit)
    mem_data = load_memory_overview(chroma_dir)
    goal_summary = _cached_goal_summary(
        str(chroma_dir),
        (get_openai_api_key() or ""),
        f"{mem_data.get('items_total', 0)}|{mem_data.get('newest_ts_utc', '')}",
    )
    ws_data = load_workspace_overview(workspace)
    policy_data = load_policy_overview(policy_path)
    rep_data = load_reports_overview(workspace)
    elapsed = int((time.perf_counter() - t0) * 1000)

    summary = event_data["summary"]
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("Events", f"{int(summary.get('events_total', 0)):,}")
    kpi2.metric("LLM Used Rate", f"{float(summary.get('llm_used_rate', 0.0)) * 100:.1f}%")
    kpi3.metric("Memory Items", f"{int(mem_data.get('items_total', 0)):,}")
    kpi4.metric("Workspace Files", f"{int(ws_data.get('files_total', 0)):,}")
    kpi5.metric("Render Time", f"{elapsed:,} ms")

    st.subheader("Route and Outcome")
    route_data = event_data["route_distribution"]
    outcome_data = event_data["outcome_distribution"]
    route_outcome_full = _needs_full_row(route_data) or _needs_full_row(outcome_data)
    label_cap = 32 if route_outcome_full else 18
    if route_outcome_full:
        st.write("Route Distribution")
        st.altair_chart(
            _bar_chart_from_dict(route_data, y_title="events", max_label_chars=label_cap),
            use_container_width=True,
        )
        st.write("Outcome Distribution")
        st.altair_chart(
            _bar_chart_from_dict(outcome_data, y_title="events", max_label_chars=label_cap),
            use_container_width=True,
        )
    else:
        c1, c2 = st.columns(2)
        c1.write("Route Distribution")
        c1.altair_chart(
            _bar_chart_from_dict(route_data, y_title="events", max_label_chars=label_cap),
            use_container_width=True,
        )
        c2.write("Outcome Distribution")
        c2.altair_chart(
            _bar_chart_from_dict(outcome_data, y_title="events", max_label_chars=label_cap),
            use_container_width=True,
        )

    st.subheader("Command Mix and Timing")
    by_command_data = summary.get("by_command") or {}
    avg_duration_data = summary.get("avg_duration_ms_by_command") or {}
    command_timing_full = _needs_full_row(by_command_data) or _needs_full_row(avg_duration_data)
    label_cap = 32 if command_timing_full else 18
    if command_timing_full:
        st.write("By Command")
        st.altair_chart(
            _bar_chart_from_dict(by_command_data, y_title="events", max_label_chars=label_cap),
            use_container_width=True,
        )
        st.write("Avg Duration (ms) by Command")
        st.altair_chart(
            _bar_chart_from_dict(avg_duration_data, y_title="ms", max_label_chars=label_cap),
            use_container_width=True,
        )
    else:
        c3, c4 = st.columns(2)
        c3.write("By Command")
        c3.altair_chart(
            _bar_chart_from_dict(by_command_data, y_title="events", max_label_chars=label_cap),
            use_container_width=True,
        )
        c4.write("Avg Duration (ms) by Command")
        c4.altair_chart(
            _bar_chart_from_dict(avg_duration_data, y_title="ms", max_label_chars=label_cap),
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
        _humanize_dict_for_json(
            {
                "items_total": mem_data.get("items_total"),
                "oldest_ts_utc": mem_data.get("oldest_ts_utc"),
                "newest_ts_utc": mem_data.get("newest_ts_utc"),
                "status": mem_data.get("status"),
                "error": mem_data.get("error"),
            }
        )
    )
    st.write("Recent Memory Items")
    _show_scroll_table(mem_data.get("latest_items") or [], height=320)
    st.write("User Goal Summary (Memories Only)")
    goal_text = str(goal_summary.get("summary") or "").strip()
    goal_status = str(goal_summary.get("status") or "ok").strip().lower()
    if goal_status == "ok":
        st.success(goal_text or "No goal summary available.")
    elif goal_status == "unavailable":
        st.warning(goal_text or "Goal summary unavailable.")
    else:
        st.error(goal_text or "Goal summary failed.")
        err = str(goal_summary.get("error") or "").strip()
        if err:
            st.caption(f"error={err}")

    st.subheader("Workspace Health")
    w1, w2 = st.columns(2)
    w1.json(
        _humanize_dict_for_json(
            {
                "files_total": ws_data.get("files_total"),
                "dirs_total": ws_data.get("dirs_total"),
                "bytes_total": ws_data.get("bytes_total"),
                "changed_last_24h_total": ws_data.get("changed_last_24h_total"),
            }
        )
    )
    w2.write("Top Extensions")
    with w2:
        _show_scroll_table(ws_data.get("top_extensions") or [], height=300)
    st.write("Largest Files")
    _show_scroll_table(_largest_files_rows_with_units(ws_data.get("largest_files") or []), height=320)

    st.subheader("Policy Posture")
    p1, p2 = st.columns(2)
    p1.json(
        _humanize_dict_for_json(
            {
                "command_allowlist_count": policy_data.get("command_allowlist_count"),
                "command_denylist_count": policy_data.get("command_denylist_count"),
                "denied_paths_count": policy_data.get("denied_paths_count"),
                "routing_controls": policy_data.get("routing_controls"),
            }
        )
    )
    p2.json(
        _humanize_dict_for_json(
            {
                "execution_limits": policy_data.get("execution_limits"),
                "network_controls": policy_data.get("network_controls"),
            }
        )
    )

    st.subheader("Report Artifacts")
    r1, r2 = st.columns(2)
    r1.json(
        _humanize_dict_for_json(
            {
                "ui_snapshot_runs_total": rep_data.get("ui_snapshot_runs_total"),
                "ui_snapshot_runs_latest": rep_data.get("ui_snapshot_runs_latest"),
            }
        )
    )
    r2.json(
        _humanize_dict_for_json(
            {
                "metrics_runs_total": rep_data.get("metrics_runs_total"),
                "metrics_runs_latest": rep_data.get("metrics_runs_latest"),
            }
        )
    )

    st.subheader("Latest Events")
    _show_scroll_table(event_data.get("latest_events") or [], height=360)
    st.caption("CAD Guardian | Product ownership: CAD Guardian brand.")


if __name__ == "__main__":
    main()
