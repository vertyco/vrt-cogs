from datetime import datetime, timezone

from assistant.common.models import GuildSettings, Skill, build_skill_index


def make_skill(**overrides) -> Skill:
    defaults = {
        "description": "Use when a player reports a lost dino",
        "body": "1. Check tribe logs\n2. Never promise restoration",
    }
    defaults.update(overrides)
    return Skill(**defaults)


def test_skill_defaults():
    skill = make_skill()
    assert skill.enabled is True
    assert skill.permission_level == "user"
    assert skill.use_count == 0
    assert skill.last_used is None
    assert isinstance(skill.created, datetime)
    assert isinstance(skill.modified, datetime)


def test_skill_mark_used():
    skill = make_skill()
    skill.mark_used()
    assert skill.use_count == 1
    assert skill.last_used is not None
    assert skill.last_used.tzinfo == timezone.utc


def test_skill_touch_updates_modified():
    skill = make_skill()
    before = skill.modified
    skill.touch()
    assert skill.modified >= before


def test_guild_settings_skill_fields():
    conf = GuildSettings()
    assert conf.skills == {}
    assert conf.skills_enabled is False
    assert conf.max_skills == 50


def test_build_skill_index_filters_and_sorts():
    skills = {
        "b-skill": make_skill(description="B desc"),
        "a-skill": make_skill(description="A desc"),
        "disabled": make_skill(enabled=False),
        "mod-only": make_skill(description="Mod desc", permission_level="mod"),
    }
    index = build_skill_index(skills, allowed=["a-skill", "b-skill", "disabled"])
    assert "- a-skill: A desc" in index
    assert "- b-skill: B desc" in index
    assert index.index("a-skill") < index.index("b-skill")
    assert "disabled" not in index
    assert "mod-only" not in index  # not in allowed list


def test_build_skill_index_empty_returns_blank():
    assert build_skill_index({}, allowed=[]) == ""
    assert build_skill_index({"x": make_skill(enabled=False)}, allowed=["x"]) == ""
