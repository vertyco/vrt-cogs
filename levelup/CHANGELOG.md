# [5.0.0] (2026-01-24)

## Release Highlights

- **Major Architecture Change**: Image generation is now completely isolated from the bot's Python process
- Three-tier image generation system: subprocess isolation, managed local API, or external API
- Significantly improved stability and resource management for image generation
- Custom fonts now work across all generation methods via base64 encoding

## Breaking Changes

- Removed `internal_api_port` setting (replaced by managed API system)
- Image generation now runs in isolated subprocesses by default

## New Features

- **Subprocess Isolation**: Profile/levelup images are now generated in separate Python processes, preventing memory leaks and GIL contention from affecting the bot
- **Managed Local API**: New `[p]lvlowner managedapi [port]` command to run a local uvicorn API server managed by the cog
  - Automatically starts/stops with the cog
  - Orphan process detection and cleanup on cog load
  - Health checks ensure API is ready before use
  - Configurable worker count with `[p]lvlowner apiworkers`
- **External API Support**: Continue using `[p]lvlowner api` for external/remote API deployments
- **Automatic Fallback**: If API is unavailable, gracefully falls back to subprocess generation
- **Semaphore-Limited Concurrency**: Subprocess generation limited to CPU core count to prevent resource exhaustion
- **Custom Font Support**: `font_b64` field in API requests allows custom fonts to work with external APIs

## Technical Improvements

- Process tree killing using `psutil` for reliable cleanup on all platforms
- PID file tracking for orphan detection across bot restarts/crashes
- Configurable uvicorn worker count (defaults to CPU cores / 2)
- API logs written to Red's logs directory (`levelup_api.log`)
- Health endpoint (`/health`) for readiness checks

## Settings Changes

- Added `managed_api` (bool) - Enable managed local API
- Added `managed_api_port` (int) - Port for managed API (default: 6789)
- Added `managed_api_workers` (int) - Worker count (0 = auto)
- Removed `internal_api_port` - Replaced by managed API system

---

# [4.1.1](https://github.com/vertyco/vrt-cogs/commit/7b66eb14a2a885ca391c0ee783b738d11b270717) (2024-07-24)

## Release Highlights

- Allow listening to other bots
- Allow list commands
- Improved ignored channels
- Various bugfixes and docstring improvements

## New Features

- Added `[p]lvlset allowlist` commands
- Added `[p]lvlowner ignorebots` to let bots have profiles too

# [4.0.0](https://github.com/vertyco/vrt-cogs/commit/60c7eedb14c770304f1e29449456596eb5949426) (2024-06-18)

## Release Highlights

- Complete rewrite of the cog to be more performant, user friendly, and easier to maintain
- Moved away from Red's `Config` driver to a custom Pydantic based configuration system
- Total rework of how voice time is tracked (way more efficient)
- [Documented functions](https://github.com/vertyco/vrt-cogs/tree/main/levelup/shared) for other 3rd party cogs to use (WIP)
- Optional external [API framework](https://github.com/vertyco/vrt-cogs/blob/main/levelup/generator/README.md) for image generation offloading
- Removed `[p]lvlset admin` group and split into two separate groups: `[p]lvldata` for backups and data related commands and `[p]lvlowner` for owner only commands

## New Features

- Image profiles can now render gifs both for the background and the profile picture
- Added a new Runescape stylized profile image style
- Added framework for an external API to offload image generation
- Added "Exp Role Groups" so many users can contribute to a grouped leaderboard
- This is mostly for fun and doesn't do any role assignment or bonuses
- User level roles are now synced more intelligently, admins should rarely if ever need to sync them manually
- LevelUp images can now be rendered as gifs
- Profile configuration commands are now hybrids
- Setting colors now support a ton of names instead of just hex codes
- Backing up the cog now prettyfies the JSON output with indentation
- The new config system keeps 3 backups of itself at all times
- Setting profile backgrounds now supports Discord [Tenor](https://developers.google.com/tenor/guides/quickstart) links directly (Must set api key with `[p]set api tenor api_key <key>`)
- Added command to set server-wide profile style override
