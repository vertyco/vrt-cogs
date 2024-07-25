# [4.1.1](https://github.com/vertyco/vrt-cogs/commit/7b66eb14a2a885ca391c0ee783b738d11b270717) (2024-07-24)

## Release Highlights

- Allow listening to other bots
- Allow list commands
- Improved ignored channels
- Various bugfixes and docstrinc improvements

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
