"""Sentinel Command Dashboard — Phase 1 (Local)

Four-quadrant layout showing project status, research signals,
decision queue, agent status, and goals. Auto-refreshes every 5 minutes.
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from pathlib import Path

from parsers import (
    parse_status_md,
    parse_inbox,
    parse_goals,
    get_staging_files,
    load_state_json,
    get_vault_stats,
    get_vault_sync_age,
)

# --- Config ---
VAULT_PATH = Path.home() / "dev" / "sentinel" / "vault"
STATUS_PATH = Path.home() / "dev" / "master-plan" / "STATUS.md"

# --- Auto-refresh every 5 minutes ---
st_autorefresh(interval=5 * 60 * 1000, key="dashboard_refresh")

# --- Page config ---
st.set_page_config(
    page_title="Sentinel Command",
    page_icon="\U0001F531",
    layout="wide",
)

# --- Custom CSS ---
st.markdown("""
<style>
    .block-container { padding-top: 1rem; }
    .stale-file { color: #b8860b; font-weight: bold; }
    div[data-testid="stMetricValue"] { font-size: 1.1rem; }
</style>
""", unsafe_allow_html=True)


# --- Helper to show error dict ---
def show_error(data, section_name):
    """If data is an error dict, show warning and return True."""
    if isinstance(data, dict) and "error" in data:
        st.warning(f"\u26a0\ufe0f {section_name} parse failed \u2014 check {data.get('raw_path', 'source file')}")
        st.caption(data["error"])
        return True
    return False


def vscode_link(abs_path, display_name):
    """Return an HTML anchor tag that opens a file in VS Code."""
    return f'<a href="vscode://file/{abs_path}" target="_blank">{display_name}</a>'


def file_expander(abs_path, label="\U0001F4C4 View"):
    """Show an expandable section that renders file content as markdown."""
    with st.expander(label, expanded=False):
        try:
            content = Path(abs_path).read_text()
            st.markdown(content)
        except FileNotFoundError:
            st.warning(f"\u26a0\ufe0f File not found: {abs_path}")
        except Exception as e:
            st.warning(f"\u26a0\ufe0f Could not read file: {e}")


def resolve_archive_path(relative_path):
    """Resolve a relative archive_file path to an absolute host path."""
    if not relative_path:
        return None
    if relative_path.startswith("vault/"):
        return VAULT_PATH / relative_path[len("vault/"):]
    elif relative_path.startswith("master-plan/"):
        return Path.home() / "dev" / "master-plan" / relative_path[len("master-plan/"):]
    elif relative_path.startswith("Marketing/"):
        return Path.home() / "dev" / "Marketing" / relative_path[len("Marketing/"):]
    return VAULT_PATH / relative_path


# ============================================================
# HEADER
# ============================================================
sync_age = get_vault_sync_age(VAULT_PATH)
now = datetime.now()

header_left, header_right = st.columns([1, 2])
with header_left:
    st.markdown("# \U0001F531 SENTINEL COMMAND")
with header_right:
    st.markdown(
        f"**{now.strftime('%A, %B %d %Y')}** &nbsp;&nbsp; "
        f"`{now.strftime('%I:%M %p')}`  &nbsp;&nbsp; "
        f"Vault sync: **{sync_age}**"
    )

st.divider()

# ============================================================
# ROW 1: Project Status | Research Signals
# ============================================================
col1, col2 = st.columns(2)

# --- Project Status ---
with col1:
    st.markdown("### \U0001F4CA Project Status")
    projects = parse_status_md(STATUS_PATH)
    if not show_error(projects, "Project Status"):
        if isinstance(projects, list) and projects:
            for p in projects:
                with st.container():
                    st.markdown(f"**{p['project']}**")
                    st.caption(f"{p['status'][:120]}")
                    cols = st.columns(2)
                    cols[0].markdown(f"*Owner:* {p['owner']}")
                    cols[1].markdown(f"*Next:* {p['next_action'][:80]}")
                    st.markdown("---")
        else:
            st.info("No projects found in STATUS.md")

# --- Research Signals ---
with col2:
    st.markdown("### \U0001F52C Research Signals")
    state = load_state_json(VAULT_PATH)
    if show_error(state, "Research Signals"):
        pass
    else:
        signals = state.get("research_signals", [])
        if signals:
            for sig in signals:
                status_icon = "\U0001F7E2" if sig.get("status") == "fresh" else "\U0001F7E1"
                st.markdown(f"{status_icon} **{sig.get('agent', 'Unknown')}** \u2014 {sig.get('last_run', '?')}")
                st.caption(sig.get("headline", "No headline"))
                if sig.get("archive_file"):
                    abs_path = resolve_archive_path(sig["archive_file"])
                    link = vscode_link(abs_path, sig["archive_file"])
                    st.markdown(f"\U0001F4C1 {link}", unsafe_allow_html=True)
                    file_expander(abs_path)
        else:
            st.info("No research data yet \u2014 Sentinel will populate after next research run")

st.divider()

# ============================================================
# ROW 2: Decision Queue | Agent Status
# ============================================================
col3, col4 = st.columns(2)

# --- Decision Queue ---
with col3:
    st.markdown("### \U0001F4CB Decision Queue")

    # Staging files
    st.markdown("**Staging Files**")
    staging = get_staging_files(VAULT_PATH)
    if show_error(staging, "Staging Files"):
        pass
    elif isinstance(staging, list) and staging:
        for sf in staging:
            abs_path = VAULT_PATH / "staging" / sf["filename"]
            age_label = f" \u26a0\ufe0f **STALE ({sf['age_days']}d)**" if sf["stale"] else ""
            link = vscode_link(abs_path, sf["filename"])
            st.markdown(f"- {link} \u2014 {sf['mtime']}{age_label}", unsafe_allow_html=True)
            file_expander(abs_path)
    else:
        st.caption("No staging files")

    st.markdown("")

    # Inbox tasks
    inbox_path = VAULT_PATH / "tasks" / "inbox.md"
    inbox_link = vscode_link(inbox_path, "Inbox Tasks (unchecked)")
    st.markdown(f"**{inbox_link}**", unsafe_allow_html=True)
    inbox = parse_inbox(VAULT_PATH)
    if show_error(inbox, "Inbox Tasks"):
        pass
    elif isinstance(inbox, list) and inbox:
        for item in inbox:
            st.markdown(f"- \u2610 {item['text']}")
            if item.get("date"):
                st.caption(f"  Captured: {item['date']}")
    else:
        st.caption("Inbox clear \u2014 no unchecked items")
    file_expander(inbox_path, "\U0001F4C4 View inbox.md")

# --- Agent Status ---
with col4:
    st.markdown("### \u2699\ufe0f Agent Status")

    # Scheduled tasks
    st.markdown("**Scheduled Tasks**")
    if show_error(state, "Scheduled Tasks"):
        pass
    else:
        tasks = state.get("scheduled_tasks", [])
        if tasks:
            for t in tasks:
                # Check if stale (last run > 48h ago)
                stale = ""
                if t.get("last_run"):
                    try:
                        lr = datetime.fromisoformat(t["last_run"].replace("Z", "+00:00"))
                        if (datetime.now(lr.tzinfo) - lr).total_seconds() > 48 * 3600:
                            stale = " \U0001F534 **STALE**"
                    except Exception:
                        pass
                st.markdown(f"- **{t.get('name', '?')}**{stale}")
                st.caption(f"  Last: {t.get('last_run', '?')} \u2014 Next: {t.get('next_run', '?')}")
        else:
            st.info("No scheduled tasks yet \u2014 Sentinel will populate after next operation")

    st.markdown("")

    # Vault stats
    st.markdown("**Vault Stats**")
    stats = get_vault_stats(VAULT_PATH)
    if show_error(stats, "Vault Stats"):
        pass
    else:
        st.markdown(f"- Last commit: {stats.get('last_commit', '?')}")
        st.markdown(f"- Markdown files: {stats.get('md_file_count', '?')}")
        st.markdown(f"- Sessions this week: {stats.get('sessions_this_week', '?')}")

    st.markdown("")

    # Research — Last Run
    st.markdown("**\U0001F4D6 Research \u2014 Last Run**")
    try:
        research_signals = state.get("research_signals", []) if isinstance(state, dict) and "error" not in state else []
        if research_signals:
            today = datetime.now().date()
            for sig in research_signals:
                agent_name = sig.get("agent", "Unknown")
                last_run = sig.get("last_run")
                if last_run:
                    try:
                        run_date = datetime.strptime(last_run, "%Y-%m-%d").date()
                        days_ago = (today - run_date).days
                        if days_ago <= 3:
                            badge = "\U0001F7E2"
                        elif days_ago <= 7:
                            badge = "\U0001F7E1"
                        else:
                            badge = "\U0001F534"
                    except ValueError:
                        badge = "\U0001F534"
                        days_ago = "?"
                else:
                    badge = "\U0001F534"
                    days_ago = None

                age_text = f"{days_ago}d ago" if days_ago is not None and days_ago != "?" else "never"
                line = f"{badge} **{agent_name}** \u2014 {last_run or 'never'} ({age_text})"

                if sig.get("archive_file"):
                    abs_path = resolve_archive_path(sig["archive_file"])
                    link = vscode_link(abs_path, "\U0001F4C2 open")
                    line += f" {link}"

                st.markdown(line, unsafe_allow_html=True)
        else:
            st.caption("No research signal data available")
    except Exception as e:
        st.warning(f"\u26a0\ufe0f Research last-run display failed: {e}")

st.divider()

# ============================================================
# ROW 3: Goals
# ============================================================
st.markdown("### \U0001F3AF Goals")
goals = parse_goals(VAULT_PATH)
if not show_error(goals, "Goals"):
    gcol1, gcol2 = st.columns(2)

    with gcol1:
        st.markdown("**180-Day Goals (Sep 2026)**")
        for g in goals.get("long_term", []):
            icon = "\u2611\ufe0f" if g["checked"] else "\u2610"
            st.markdown(f"{icon} {g['text']}")

    with gcol2:
        st.markdown("**This Month (March 2026)**")
        for g in goals.get("this_month", []):
            icon = "\u2611\ufe0f" if g["checked"] else "\u2610"
            st.markdown(f"{icon} {g['text']}")

# --- Footer ---
st.markdown("")
st.caption(f"Dashboard refreshes every 5 minutes \u2014 Last render: {now.strftime('%H:%M:%S')}")
