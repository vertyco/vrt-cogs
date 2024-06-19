# 3rd Party Integration Help

This directory contains metaclassed functions that are shared between the LevelUp cog and other cogs that wish to use them. These functions are designed to be as modular as possible, allowing for easy integration into other cogs.

## Example Usage

Say we want to add xp to a user and check if they've leveled up.

```python
cog = self.bot.get_cog("LevelUp")
member: discord.Member = ctx.author
new_xp = await cog.add_xp(member, 1000)
await cog.check_levelups(member)
```

## Functions

The functions themselves are documented in the function doscstrings, but here is a brief overview of what each function does.

### [profile.py](https://github.com/vertyco/vrt-cogs/blob/main/levelup/shared/profile.py)

- add_xp - Adds XP to a user's profile
- remove_xp - Removes XP from a user's profile
- set_xp - Sets a user's XP to a specific amount
- get_profile_background - Gets the background image for a user's profile
- get_banner - Gets the banner image for a user's profile
- get_user_profile - Gets a user's profile
- get_user_profile_cached - Gets a user's profile from the cache

### [weeklyreset.py](https://github.com/vertyco/vrt-cogs/blob/main/levelup/shared/weeklyreset.py)

- reset_weekly - Resets the weekly XP for all users and sends the reset message to the set channel

### [levelups.py](https://github.com/vertyco/vrt-cogs/blob/main/levelup/shared/levelups.py)

- check_levelups - Check if a user has leveled up and award roles if needed
- ensure_roles - Ensure that a user has the correct roles for their level and/or prestige

## Events

LevelUp dispatches a few events that other cogs can listen for.

### member_levelup

Add this listener to your cog to listen for when a user levels up.

```python
@commands.Cog.listener()
async def on_member_levelup(
    self,
    guild: discord.Guild,
    member: discord.Member,
    message: str | None,
    channel: TextChannel | VoiceChannel | Thread | ForumChannel,
    nev_level: int,
):
    print(f"{member} leveled up to level {new_level}!")
    # Do something when a user levels up
```
