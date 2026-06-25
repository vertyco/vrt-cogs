# Tickets Changelog

## v3.4.0

- **New**: `[p]lockticket` and `[p]unlockticket`. Staff (support roles or admins) can lock a ticket so the owner can no longer close, rename, or add users to it; staff and admins keep full control. The lock is enforced in the shared `can_close` check, so both the `[p]close` command and the Close button respect it. The bot posts a channel notice when a ticket is locked or unlocked.
