from assistant.common.models import GuildSettings, RolePrompt


class FakeRole:
    """Stand-in for discord.Role; sorts by position like the real thing."""

    def __init__(self, role_id: int, position: int):
        self.id = role_id
        self.position = position

    def __lt__(self, other):
        return self.position < other.position


class FakeMember:
    def __init__(self, roles):
        # discord gives roles low->high; resolution sorts reverse=True
        self.roles = roles


def make_conf(role_prompts=None, stack=True) -> GuildSettings:
    conf = GuildSettings()
    conf.role_prompts = role_prompts or {}
    conf.role_prompts_stack = stack
    return conf


def test_role_prompt_defaults():
    rp = RolePrompt(text="hi")
    assert rp.text == "hi"
    assert rp.replace is False


def test_no_member_returns_empty():
    conf = make_conf({1: RolePrompt(text="x")})
    assert conf.get_role_prompt_layers(None) == (None, [])


def test_empty_role_prompts_returns_empty():
    conf = make_conf({})
    member = FakeMember([FakeRole(1, 1)])
    assert conf.get_role_prompt_layers(member) == (None, [])


def test_whitespace_text_skipped():
    conf = make_conf({1: RolePrompt(text="   ")})
    member = FakeMember([FakeRole(1, 1)])
    assert conf.get_role_prompt_layers(member) == (None, [])


def test_stack_off_highest_append():
    conf = make_conf({1: RolePrompt(text="mod"), 2: RolePrompt(text="admin")}, stack=False)
    member = FakeMember([FakeRole(1, 1), FakeRole(2, 2)])
    assert conf.get_role_prompt_layers(member) == (None, ["admin"])


def test_stack_off_highest_replace():
    conf = make_conf({2: RolePrompt(text="admin", replace=True)}, stack=False)
    member = FakeMember([FakeRole(1, 1), FakeRole(2, 2)])
    assert conf.get_role_prompt_layers(member) == ("admin", [])


def test_stack_off_ignores_lower():
    conf = make_conf(
        {1: RolePrompt(text="mod", replace=True), 2: RolePrompt(text="admin")}, stack=False
    )
    member = FakeMember([FakeRole(1, 1), FakeRole(2, 2)])
    assert conf.get_role_prompt_layers(member) == (None, ["admin"])


def test_stack_on_two_appends_low_to_high():
    conf = make_conf({1: RolePrompt(text="mod"), 2: RolePrompt(text="admin")})
    member = FakeMember([FakeRole(1, 1), FakeRole(2, 2)])
    assert conf.get_role_prompt_layers(member) == (None, ["mod", "admin"])


def test_stack_on_replace_plus_append():
    conf = make_conf(
        {1: RolePrompt(text="mod"), 2: RolePrompt(text="admin", replace=True)}
    )
    member = FakeMember([FakeRole(1, 1), FakeRole(2, 2)])
    assert conf.get_role_prompt_layers(member) == ("admin", ["mod"])


def test_stack_on_two_replace_highest_wins():
    conf = make_conf(
        {
            1: RolePrompt(text="mod", replace=True),
            2: RolePrompt(text="admin", replace=True),
        }
    )
    member = FakeMember([FakeRole(1, 1), FakeRole(2, 2)])
    assert conf.get_role_prompt_layers(member) == ("admin", [])


def test_stack_on_replace_high_appends_low_to_high():
    conf = make_conf(
        {
            1: RolePrompt(text="low"),
            2: RolePrompt(text="mid"),
            3: RolePrompt(text="high", replace=True),
        }
    )
    member = FakeMember([FakeRole(1, 1), FakeRole(2, 2), FakeRole(3, 3)])
    assert conf.get_role_prompt_layers(member) == ("high", ["low", "mid"])


def test_stack_on_two_replace_only_highest_wins_with_append():
    conf = make_conf(
        {
            1: RolePrompt(text="low", replace=True),
            2: RolePrompt(text="mid"),
            3: RolePrompt(text="high", replace=True),
        }
    )
    member = FakeMember([FakeRole(1, 1), FakeRole(2, 2), FakeRole(3, 3)])
    # "low" (replace, lower priority) silently dropped; "mid" (append) survives
    assert conf.get_role_prompt_layers(member) == ("high", ["mid"])
