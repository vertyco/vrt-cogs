# Tickets Changelog

## v3.8.0

- **New**: `[p]ticketpings` lets each staff member turn on (or off) being pinged when a new ticket opens. You are only pinged for tickets you can see, and never for a ticket you opened yourself. Only ticket staff (global or any panel support role) or admins can turn it on; anyone can turn it off.
- **New**: `[p]tickets view` lists who has new-ticket pings turned on.
- **Change**: Red's delete-my-data request now removes the user from the new-ticket ping list.

## v3.7.0

- **New**: `[p]tickets selfescalate` toggles whether ticket owners can escalate their own ticket to admins only (off by default, shown in `[p]tickets view`). It works like `selfrename`/`selfmanage`: a locked ticket can't be escalated by its owner.
- **New**: An **Escalate** button next to the Close button on new tickets. It does the same thing as `[p]escalate` and follows the same permission check.
- **Change**: `[p]escalate` is no longer admin-only. Admins (and anyone with Manage Server) can still always use it, and ticket owners can use it on their own ticket when `selfescalate` is on. Escalating an already escalated ticket now says so instead of running again.

## v3.6.0

- **New**: `[p]tickets overviewhide <panel>` toggles hiding a panel's tickets from the active ticket overview, so long-running tickets (like staff onboarding) don't clutter it. Hidden panels are listed in `[p]tickets view`.
- **Fix**: `[p]tickets overview <channel>` crashed before saving, so the overview channel never got set.

## v3.5.1

- **Change**: Opening a ticket now dispatches a `ticket_opened` bot event (server, member, ticket channel, panel name) so other cogs, such as Assistant jobs, can react to new tickets.

## v3.4.0

- **New**: `[p]lockticket` and `[p]unlockticket`. Staff (support roles or admins) can lock a ticket so the owner can no longer close, rename, or add users to it; staff and admins keep full control. The lock is enforced in the shared `can_close` check, so both the `[p]close` command and the Close button respect it. The bot posts a channel notice when a ticket is locked or unlocked.
