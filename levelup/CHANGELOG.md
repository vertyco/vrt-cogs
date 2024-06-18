# 4.0.0 (2024-06-17)

## Release Highlights

- Complete rework of the cog to be more performant, user friendly, and easier to maintain
- Moved away from Red's `Config` driver to a custom Pydantic based configuration system
- Total rework of how voice time is tracked (way more efficient)
- Documented functions for other 3rd party cogs to use (WIP)
- Optional external API framework for image generation offloading

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
- Setting profile backgrounds now supports Discord tenor links directly
- Added command to set server-wide profile style override
