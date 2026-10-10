"""Every command of the original is here, under the same names"""

from redbot.core.commands.requires import PrivilegeLevel

from casino.main import Casino


def test_every_original_command_is_here():
    cog = Casino(bot=None)
    names = {command.qualified_name for command in cog.walk_commands()}
    casino = {"stats", "info", "memberships", "version", "releasecredits", "resetuser", "resetinstance"}
    casino |= {"assignmem", "revokemem", "memdesigner", "wipe"}
    casinoset = {"name", "toggle", "payoutlimit", "payouttoggle", "min", "max", "multiplier", "cooldown"}
    casinoset |= {"access", "gametoggle", "mode"}
    assert {f"casino {name}" for name in casino} | {f"casinoset {name}" for name in casinoset} <= names
    assert [command.name for command in cog.get_app_commands()] == ["casino"]


def checked_by(command, word: str) -> bool:
    return any(word in check.__qualname__ for check in command.checks)


def test_admin_commands_need_the_manager_check_and_wipe_and_mode_the_owner():
    cog = Casino(bot=None)
    found = {command.qualified_name: command for command in cog.walk_commands()}
    for name in ("releasecredits", "resetuser", "resetinstance", "assignmem", "revokemem", "memdesigner"):
        assert checked_by(found[f"casino {name}"], "manager"), name
    assert checked_by(found["casinoset"], "manager")
    assert found["casino wipe"].requires.privilege_level == PrivilegeLevel.BOT_OWNER
    assert found["casinoset mode"].requires.privilege_level == PrivilegeLevel.BOT_OWNER
