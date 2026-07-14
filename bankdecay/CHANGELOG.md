# Changelog

## 0.5.0

- Decay warning DM now uses the server's own bank currency name instead of the hardcoded "VertCoin" title, so the cog reads correctly on any server.
- Log a warning when a decay warning DM fails to send (user has DMs closed or blocked) instead of failing silently.
- Post a notice to the configured log channel when a decay warning DM fails, so staff can see the user never got warned.
