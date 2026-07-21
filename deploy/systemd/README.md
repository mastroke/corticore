# Local Composer-2.5 swarm (systemd)

Runs the daily maintenance loop on your laptop during **04:00–09:00 Asia/Kolkata**
using Cursor **local** agents (`composer-2.5` for every role). Commits land on
`main` after a green `pytest` + eval gate. On **Friday**, the loop also bumps
the version and CHANGELOG and pushes, which triggers
`.github/workflows/release.yml` (set repo variable `RELEASE_ENABLED=true` to
actually publish to PyPI).

At **09:30 Asia/Kolkata** a second timer digests today's swarm ledger and
sends you a Telegram summary of what every role did.

You should **not** need to start either job every day. After install, the
timers + user linger handle them while the laptop is on.

## Install once

```bash
cd /path/to/corticore
pip install -e ".[dev,orchestrate]"   # once
./deploy/systemd/install.sh           # seeds env, enables linger + both timers
```

That script:

1. Installs the user systemd units (swarm + Telegram report)
2. Seeds `~/.config/corticore-swarm/env` from the repo `.env` (`CURSOR_API_KEY`)
3. Appends `TELEGRAM_BOT_TOKEN=` / `TELEGRAM_CHAT_ID=` placeholders if missing
4. Runs `loginctl enable-linger` so timers fire without an active GUI login
5. Enables:
   - `corticore-swarm.timer` — 04:00 Asia/Kolkata (`Persistent=true`, `--catch-up`)
   - `corticore-swarm-report.timer` — 09:30 Asia/Kolkata (`Persistent=true`)

If the laptop was off at 04:00, `Persistent=true` starts the swarm after the
next boot. `--catch-up` still runs a bounded ~90m loop once that day if the
stamp is missing. The 09:30 report likewise catches up after a late boot.

## Telegram daily report (09:30 IST)

One-time BotFather setup:

1. Open Telegram and talk to [@BotFather](https://t.me/BotFather) → `/newbot`
   → copy the bot token.
2. Put it in `~/.config/corticore-swarm/env`:
   ```bash
   TELEGRAM_BOT_TOKEN=123456:ABC...
   ```
3. Open a chat with your new bot and send any message (e.g. `hi`).
4. Discover your chat id:
   ```bash
   cd /path/to/corticore
   set -a && source ~/.config/corticore-swarm/env && set +a
   python orchestrate/report_daily.py --print-chat-id
   ```
5. Add the printed id to the env file:
   ```bash
   TELEGRAM_CHAT_ID=123456789
   ```
6. Preview, then send a test:
   ```bash
   python orchestrate/report_daily.py --dry-run
   systemctl --user start corticore-swarm-report.service
   ```

If there was no swarm activity that day, you still get a short
“No swarm cycles today” ping so silence is not ambiguous.

## Manual runs (optional)

```bash
# Thinkers + judge only (safe smoke test)
python orchestrate/run_swarm.py --runtime local --no-write --ignore-window --skip-release

# Full write loop now
SWARM_ENABLED=true python orchestrate/run_swarm.py --runtime local --loop --catch-up

# Kick installed units
systemctl --user start corticore-swarm.service
systemctl --user start corticore-swarm-report.service
journalctl --user -u corticore-swarm-report.service -f
```

## Research fallback (competitor learning)

When there is no new paper/note ready to adopt, the `research_scout` role
reads `orchestrate/competitors.yml`, studies 1–2 peer repos (mem0, letta,
zep, langmem, Awesome-Self-Improving-Agents, …), and proposes a **small,
ADR-compatible port** of an idea — never a wholesale code copy.

## Layout

| Path | Purpose |
|------|---------|
| repo WorkingDirectory | Source of `run_swarm.py` / `report_daily.py` |
| `~/.local/share/corticore-swarm/checkout` | Dedicated clone agents edit |
| `~/.local/share/corticore-swarm/last_run_day` | Catch-up stamp (ISO date) |
| `orchestrate/.swarm_ledger.jsonl` | Swarm activity ledger (report input) |
| `~/.config/corticore-swarm/env` | `CURSOR_API_KEY`, `SWARM_ENABLED`, `TELEGRAM_*` |
| `~/.config/systemd/user/corticore-swarm*` | Installed units |

## Kill switch

- Set `SWARM_ENABLED=false` in `~/.config/corticore-swarm/env`, or
- `systemctl --user disable --now corticore-swarm.timer`
- Report only: `systemctl --user disable --now corticore-swarm-report.timer`

## Weekly release

On Friday (`release.weekday` in `orchestrate/swarm.yml`), after the loop the
orchestrator bumps `pyproject.toml` + CHANGELOG and pushes. That triggers
`.github/workflows/release.yml` when `RELEASE_ENABLED=true` on GitHub.
