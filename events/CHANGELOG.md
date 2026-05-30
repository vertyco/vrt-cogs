# Events Changelog

## v0.2.6

- **Fix**: The minute event-check loop no longer dies permanently on the first error. Each event end is now wrapped in try/except, so one bad event (e.g. a deleted channel) can't stop auto-ending for every event in every guild.
- **Fix**: `_end_event` now bails gracefully when the submission channel was deleted — it closes the event instead of crashing with `AttributeError` and retrying forever.
- **Fix**: Ending an event is now guarded against running twice concurrently (manual `[p]events end` racing the auto loop), which could double-post results and double-deposit rewards. A fresh-state re-check also skips events already completed/deleted since they were queued.
- **Fix**: `[p]events view` no longer crashes when an event's required role was deleted (now filtered like the other role lists).
- **Fix**: Entering an event that ends mid-entry no longer raises `KeyError` when saving — the user is told the event ended instead.
- **Fix**: `[p]events remove` no longer crashes when the event channel was deleted, and tolerates `Forbidden`/`HTTPException` while deleting entries.
- **Fix**: Entry no longer crashes if `joined_at` is unavailable when a days-in-server requirement is set.
- **Fix**: Vote tally no longer raises `IndexError` if a fetched submission message has no embed.
- **Fix**: Entry confirmation only cancels when the reply starts with `n` (words like "fine"/"any" no longer false-cancel).
- **Fix**: DM reply acknowledgement reaction is now wrapped in a suppress, matching the guild branch.
- Minor wording fix ("No submissions sent").
