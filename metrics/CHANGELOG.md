# Metrics Changelog

## v1.0.7

- **Fix**: `[p]metrics bank` was permanently unreachable when the economy is in global mode — it gated on the per-guild `track_bank` flag, which cannot be enabled while global. It now gates on the global tracking flag when showing global data.
- **Fix**: Performance snapshots no longer block the event loop. `psutil.cpu_percent(interval=0.1)` (a synchronous 100ms sleep) is now offloaded with `asyncio.to_thread`.
- **Fix**: Member snapshots now run at the configured interval. `configure_task_intervals` applied the stored value only when it differed from a hard-coded default, so a fresh install captured members every 10 minutes instead of the configured 15.
- **Fix**: Dashboard statistics no longer truncate sub-unit performance metrics to `0`. CPU/latency/duration now render with two decimals; member/economy values stay integer-formatted.
- **Fix**: Selecting the Performance category in the dashboard now forces global scope so the header label and scope buttons match the global-only data.
- **Fix**: Switching dashboard category no longer renders a blank graph — a sensible default metric selection is applied for the new category.
- **Fix**: `[p]metrics bank` no longer risks an `AttributeError` on a `None` timespan (now guarded like the member/performance commands).
- **Fix**: Outlier pruning now computes statistics per-guild for guild scope, so a large guild's normal values are no longer flagged as outliers against smaller guilds.
- **Fix**: `cleanup_old_snapshots` now logs failures instead of silently discarding them in a fire-and-forget task.
- **Fix**: `get_timespan` now tolerates out-of-range / malformed date input (`OverflowError`/`ValueError`) and falls back to the default window instead of erroring the command.
- **Perf**: Global member snapshot iteration now yields to the event loop via `AsyncIter`.
- **Perf**: Economy snapshot task skips loading all bank users / the per-guild settings query when that work would be discarded (global mode, or global tracking disabled).
- **Perf**: EconomyTrack import reads its settings file off the event loop.
- **UX**: The dashboard now disables its components on timeout and pushes that state to the message.
