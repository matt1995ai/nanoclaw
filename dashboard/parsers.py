"""Fault-tolerant markdown parsers for the Sentinel Command Dashboard.

Every function returns structured data on success or an error dict on failure.
Dashboard renders warnings from error dicts — never crashes.
"""

import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path


def parse_status_md(status_path):
    """Parse master-plan/STATUS.md project table.

    Returns list of dicts: [{project, status, owner, next_action}, ...]
    """
    try:
        path = Path(status_path)
        text = path.read_text()
        lines = text.splitlines()

        projects = []
        in_table = False
        header_seen = False

        for line in lines:
            stripped = line.strip()
            if not stripped.startswith("|"):
                if in_table:
                    break
                continue

            in_table = True
            # Skip header row
            if not header_seen:
                header_seen = True
                continue
            # Skip separator row (|---|---|...)
            if set(stripped.replace("|", "").replace("-", "").strip()) <= set(" "):
                continue

            cells = [c.strip() for c in stripped.split("|")]
            # Split produces empty strings at start/end from leading/trailing |
            cells = [c for c in cells if c or cells.index(c) not in (0, len(cells) - 1)]
            cells = [c.strip() for c in stripped.strip("|").split("|")]

            if len(cells) >= 4:
                projects.append({
                    "project": cells[0].strip(),
                    "status": cells[1].strip(),
                    "owner": cells[2].strip(),
                    "next_action": cells[3].strip(),
                })
            elif len(cells) >= 2:
                projects.append({
                    "project": cells[0].strip(),
                    "status": cells[1].strip() if len(cells) > 1 else "",
                    "owner": cells[2].strip() if len(cells) > 2 else "",
                    "next_action": cells[3].strip() if len(cells) > 3 else "",
                })

        return projects if projects else {"error": "No project rows found in table", "raw_path": str(path)}

    except Exception as e:
        return {"error": f"Parse failed: {str(e)}", "raw_path": str(status_path)}


def parse_inbox(vault_path):
    """Parse vault/tasks/inbox.md for unchecked items.

    Returns list of dicts: [{text, date_header}, ...]
    """
    try:
        path = Path(vault_path) / "tasks" / "inbox.md"
        text = path.read_text()
        lines = text.splitlines()

        items = []
        current_date = ""

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                current_date = stripped[3:].strip()
            elif stripped.startswith("- [ ] "):
                task_text = stripped[6:].strip()
                if len(task_text) > 80:
                    task_text = task_text[:77] + "..."
                items.append({
                    "text": task_text,
                    "date": current_date,
                })

        return items

    except Exception as e:
        return {"error": f"Parse failed: {str(e)}", "raw_path": str(Path(vault_path) / "tasks" / "inbox.md")}


def parse_goals(vault_path):
    """Parse vault/GOALS.md for 180-day and This Month goals.

    Returns dict: {long_term: [...], this_month: [...]}
    """
    try:
        path = Path(vault_path) / "GOALS.md"
        text = path.read_text()
        lines = text.splitlines()

        result = {"long_term": [], "this_month": []}
        current_section = None

        for line in lines:
            stripped = line.strip()
            lower = stripped.lower()

            if stripped.startswith("## ") and "180" in stripped:
                current_section = "long_term"
                continue
            elif stripped.startswith("## ") and "month" in lower:
                current_section = "this_month"
                continue
            elif stripped.startswith("## "):
                current_section = None
                continue

            if current_section and (stripped.startswith("- [ ] ") or stripped.startswith("- [x] ")):
                checked = stripped.startswith("- [x] ")
                text = stripped[6:].strip()
                result[current_section].append({
                    "text": text,
                    "checked": checked,
                })

        return result

    except Exception as e:
        return {"error": f"Parse failed: {str(e)}", "raw_path": str(Path(vault_path) / "GOALS.md")}


def get_staging_files(vault_path):
    """List vault/staging/*.md files with modification times.

    Returns list of dicts: [{filename, mtime, age_days, stale}, ...]
    """
    try:
        staging = Path(vault_path) / "staging"
        if not staging.exists():
            return []

        files = []
        now = time.time()
        three_days = 3 * 24 * 60 * 60

        for f in sorted(staging.glob("*.md")):
            mtime = f.stat().st_mtime
            age_seconds = now - mtime
            age_days = age_seconds / (24 * 60 * 60)
            files.append({
                "filename": f.name,
                "mtime": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                "age_days": round(age_days, 1),
                "stale": age_seconds > three_days,
            })

        return files

    except Exception as e:
        return {"error": f"Parse failed: {str(e)}", "raw_path": str(Path(vault_path) / "staging")}


def load_state_json(vault_path):
    """Read vault/.dashboard/state.json.

    Returns parsed JSON or empty template.
    """
    try:
        path = Path(vault_path) / ".dashboard" / "state.json"
        if not path.exists():
            return {
                "last_updated": None,
                "research_signals": [],
                "scheduled_tasks": [],
            }
        return json.loads(path.read_text())

    except Exception as e:
        return {"error": f"Parse failed: {str(e)}", "raw_path": str(Path(vault_path) / ".dashboard" / "state.json")}


def get_vault_stats(vault_path):
    """Get vault git stats: last commit, file count, sessions this week.

    Returns dict with stats.
    """
    try:
        vault = Path(vault_path)
        stats = {}

        # Last commit
        try:
            result = subprocess.run(
                ["git", "-C", str(vault), "log", "-1", "--format=%ar: %s"],
                capture_output=True, text=True, timeout=5
            )
            stats["last_commit"] = result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            stats["last_commit"] = "unknown"

        # File count
        try:
            count = sum(1 for _ in vault.rglob("*.md"))
            stats["md_file_count"] = count
        except Exception:
            stats["md_file_count"] = "?"

        # Sessions this week
        try:
            sessions_dir = vault / "sessions"
            if sessions_dir.exists():
                cutoff = time.time() - 7 * 24 * 60 * 60
                stats["sessions_this_week"] = sum(
                    1 for f in sessions_dir.iterdir()
                    if f.is_file() and f.stat().st_mtime > cutoff
                )
            else:
                stats["sessions_this_week"] = 0
        except Exception:
            stats["sessions_this_week"] = "?"

        return stats

    except Exception as e:
        return {"error": f"Stats failed: {str(e)}"}


def get_vault_sync_age(vault_path):
    """Check how recently the vault was synced.

    Returns human-readable string like '5m ago' or '2h ago'.
    """
    try:
        vault = Path(vault_path)

        # Try FETCH_HEAD first
        fetch_head = vault / ".git" / "FETCH_HEAD"
        if fetch_head.exists():
            age_seconds = time.time() - fetch_head.stat().st_mtime
        else:
            # Fall back to last commit time
            result = subprocess.run(
                ["git", "-C", str(vault), "log", "-1", "--format=%ct"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                age_seconds = time.time() - int(result.stdout.strip())
            else:
                return "unknown"

        minutes = int(age_seconds / 60)
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        return f"{days}d ago"

    except Exception:
        return "unknown"
