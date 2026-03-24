# Sentinel Command Dashboard

Local Streamlit dashboard showing Sentinel vault status at a glance.

## Quick Start

```bash
# Activate venv
source ~/dev/sentinel/dashboard/.venv/bin/activate

# Run
streamlit run ~/dev/sentinel/dashboard/dashboard.py \
  --server.port 8080 --server.address 0.0.0.0 --server.headless true
```

Access at `http://localhost:8080` or `http://[mac-mini-ip]:8080`.

## Auto-Start (launchd)

The plist at `~/Library/LaunchAgents/com.sentinel.dashboard.plist` keeps the dashboard running.

```bash
# Load
launchctl load ~/Library/LaunchAgents/com.sentinel.dashboard.plist

# Unload
launchctl unload ~/Library/LaunchAgents/com.sentinel.dashboard.plist

# Check logs
tail -f ~/dev/sentinel/dashboard/logs/dashboard.log
tail -f ~/dev/sentinel/dashboard/logs/dashboard-error.log
```

## Data Sources

| Section | Source | Parser |
|---------|--------|--------|
| Project Status | `~/dev/master-plan/STATUS.md` | `parse_status_md()` |
| Research Signals | `vault/.dashboard/state.json` | `load_state_json()` |
| Staging Files | `vault/staging/*.md` | `get_staging_files()` |
| Inbox Tasks | `vault/tasks/inbox.md` | `parse_inbox()` |
| Scheduled Tasks | `vault/.dashboard/state.json` | `load_state_json()` |
| Vault Stats | git + filesystem | `get_vault_stats()` |
| Goals | `vault/GOALS.md` | `parse_goals()` |

## Maintenance

- **Dashboard reads, never writes.** Sentinel updates `state.json`.
- All parsers are fault-tolerant — section shows warning on parse failure, never crashes.
- If a source file moves, update the path in `parsers.py`.
- Logs at `~/dev/sentinel/dashboard/logs/`.
