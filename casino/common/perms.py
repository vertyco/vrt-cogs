"""Who may change the casino: server admins in server mode, and the bot owner everywhere"""


async def can_manage(bot, who, global_mode: bool) -> bool:
    """Server admins are the hub's rule: Manage Server permission or Red's admin role. In global mode, only the owner"""
    if await bot.is_owner(who):
        return True
    if global_mode or getattr(who, "guild", None) is None:
        return False
    perms = getattr(who, "guild_permissions", None)
    if perms is not None and perms.manage_guild:
        return True
    return await bot.is_admin(who)
