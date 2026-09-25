# Tickets Changelog

## v3.6.0

- **New**: `[p]tickets overviewhide <panel>` toggles hiding a panel's tickets from the active ticket overview, so long-running tickets (like staff onboarding) don't clutter it. Hidden panels are listed in `[p]tickets view`.
- **Fix**: `[p]tickets overview <channel>` crashed before saving, so the overview channel never got set.

## v3.5.1

- **Change**: Opening a ticket now dispatches a `ticket_opened` bot event (server, member, ticket channel, panel name) so other cogs, such as Assistant jobs, can react to new tickets.

## v3.4.0

- **New**: `[p]lockticket` and `[p]unlockticket`. Staff (support roles or admins) can lock a ticket so the owner can no longer close, rename, or add users to it; staff and admins keep full control. The lock is enforced in the shared `can_close` check, so both the `[p]close` command and the Close button respect it. The bot posts a channel notice when a ticket is locked or unlocked.
