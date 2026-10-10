"""Every command of the original is here: [p]casino's under [p]vegas, [p]casinoset's under [p]vegasset"""

from redbot.core.commands.requires import PrivilegeLevel

from vegas.main import Vegas


def test_every_original_command_is_here():
    cog = Vegas(bot=None)
    names = {command.qualified_name for command in cog.walk_commands()}
    vegas = {"stats", "info", "memberships", "version", "releasecredits", "resetuser", "resetinstance"}
    vegas |= {"assignmem", "revokemem", "memdesigner", "wipe"}
    vegasset = {"name", "toggle", "payoutlimit", "payouttoggle", "min", "max", "multiplier", "cooldown"}
    vegasset |= {"access", "gametoggle", "mode"}
    assert {f"vegas {name}" for name in vegas} | {f"vegasset {name}" for name in vegasset} <= names
    assert [command.name for command in cog.get_app_commands()] == ["vegas"]


def checked_by(command, word: str) -> bool:
    return any(word in check.__qualname__ for check in command.checks)


def test_admin_commands_need_the_manager_check_and_wipe_and_mode_the_owner():
    cog = Vegas(bot=None)
    found = {command.qualified_name: command for command in cog.walk_commands()}
    for name in ("releasecredits", "resetuser", "resetinstance", "assignmem", "revokemem", "memdesigner"):
        assert checked_by(found[f"vegas {name}"], "manager"), name
    assert checked_by(found["vegasset"], "manager")
    assert found["vegas wipe"].requires.privilege_level == PrivilegeLevel.BOT_OWNER
    assert found["vegasset mode"].requires.privilege_level == PrivilegeLevel.BOT_OWNER
