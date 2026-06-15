import types as _types

import discord

from assistant.common import command_ui


def test_parse_instantiated_names_catches_assigned_and_inline_and_dotted():
    source = (
        "async def cmd(self, ctx):\n"
        "    view = EmbeddingMenu(ctx, conf)\n"
        "    other = views.TaskMenu(ctx).start()\n"
        "    await TaskMenu(ctx, query).start()\n"
    )
    names = command_ui.parse_instantiated_names(source)
    assert "EmbeddingMenu" in names
    assert "views.TaskMenu" in names
    assert "TaskMenu" in names


class _FakeView(discord.ui.View):
    pass


class _FakeModal(discord.ui.Modal, title="Fake"):
    pass


def test_resolve_name_and_is_ui_class():
    import types

    mod = types.ModuleType("fake_mod")
    mod.FakeView = _FakeView
    namespace = {"FakeView": _FakeView, "mod": mod, "NotUI": int}

    assert command_ui.resolve_name("FakeView", namespace) is _FakeView
    assert command_ui.resolve_name("mod.FakeView", namespace) is _FakeView
    assert command_ui.resolve_name("missing", namespace) is None
    assert command_ui.resolve_name("mod.missing", namespace) is None

    assert command_ui.is_ui_class(_FakeView) is True
    assert command_ui.is_ui_class(_FakeModal) is True
    assert command_ui.is_ui_class(int) is False
    assert command_ui.is_ui_class("FakeView") is False


class _BaseMenu(discord.ui.View):
    @discord.ui.button(label="Close")
    async def close(self, interaction, button):
        pass


class _ChildMenu(_BaseMenu):
    @discord.ui.button(label="Add")
    async def add(self, interaction, button):
        pass


def test_class_source_with_bases_includes_inherited_buttons():
    out = command_ui.class_source_with_bases(_ChildMenu)
    assert 'label="Add"' in out
    assert 'label="Close"' in out
    assert "class View" not in out


def test_resolve_label_constants_resolves_emoji_and_label_identifiers():
    import types

    consts = types.SimpleNamespace(PLUS="➕", TRASH="\U0001f5d1")
    namespace = {"C": consts, "CLOSE_EMOJI": "❌"}
    source = (
        "@discord.ui.button(emoji=C.PLUS)\n"
        "@discord.ui.button(emoji=C.TRASH, label='Delete')\n"
        "@discord.ui.button(emoji=CLOSE_EMOJI)\n"
        "@discord.ui.button(label='Literal')\n"
    )
    legend = command_ui.resolve_label_constants(source, namespace)
    assert legend["C.PLUS"] == "➕"
    assert legend["C.TRASH"] == "\U0001f5d1"
    assert legend["CLOSE_EMOJI"] == "❌"
    assert "Literal" not in legend


# ---------------------------------------------------------------------------
# Module-level helpers for Task 5 (inspect.getsource requires file-level defs)
# ---------------------------------------------------------------------------

_PLUS_EMOJI = "➕"


class _InnerModal(discord.ui.Modal, title="Inner Modal"):
    pass


class _MenuView(discord.ui.View):
    @discord.ui.button(emoji=_PLUS_EMOJI)
    async def add(self, interaction, button):
        await interaction.response.send_modal(_InnerModal())


# _BigView: source text must exceed per_class_chars=4000 so truncation fires.
# The long docstring below is a literal string in source (~5 000 chars).
_BIG_FILLER = (
    "    # padding line 001\n    # padding line 002\n    # padding line 003\n"
    "    # padding line 004\n    # padding line 005\n    # padding line 006\n"
    "    # padding line 007\n    # padding line 008\n    # padding line 009\n"
    "    # padding line 010\n    # padding line 011\n    # padding line 012\n"
    "    # padding line 013\n    # padding line 014\n    # padding line 015\n"
    "    # padding line 016\n    # padding line 017\n    # padding line 018\n"
    "    # padding line 019\n    # padding line 020\n    # padding line 021\n"
    "    # padding line 022\n    # padding line 023\n    # padding line 024\n"
    "    # padding line 025\n    # padding line 026\n    # padding line 027\n"
    "    # padding line 028\n    # padding line 029\n    # padding line 030\n"
    "    # padding line 031\n    # padding line 032\n    # padding line 033\n"
    "    # padding line 034\n    # padding line 035\n    # padding line 036\n"
    "    # padding line 037\n    # padding line 038\n    # padding line 039\n"
    "    # padding line 040\n    # padding line 041\n    # padding line 042\n"
    "    # padding line 043\n    # padding line 044\n    # padding line 045\n"
    "    # padding line 046\n    # padding line 047\n    # padding line 048\n"
    "    # padding line 049\n    # padding line 050\n    # padding line 051\n"
    "    # padding line 052\n    # padding line 053\n    # padding line 054\n"
    "    # padding line 055\n    # padding line 056\n    # padding line 057\n"
    "    # padding line 058\n    # padding line 059\n    # padding line 060\n"
    "    # padding line 061\n    # padding line 062\n    # padding line 063\n"
    "    # padding line 064\n    # padding line 065\n    # padding line 066\n"
    "    # padding line 067\n    # padding line 068\n    # padding line 069\n"
    "    # padding line 070\n    # padding line 071\n    # padding line 072\n"
    "    # padding line 073\n    # padding line 074\n    # padding line 075\n"
    "    # padding line 076\n    # padding line 077\n    # padding line 078\n"
    "    # padding line 079\n    # padding line 080\n    # padding line 081\n"
    "    # padding line 082\n    # padding line 083\n    # padding line 084\n"
    "    # padding line 085\n    # padding line 086\n    # padding line 087\n"
    "    # padding line 088\n    # padding line 089\n    # padding line 090\n"
    "    # padding line 091\n    # padding line 092\n    # padding line 093\n"
    "    # padding line 094\n    # padding line 095\n    # padding line 096\n"
    "    # padding line 097\n    # padding line 098\n    # padding line 099\n"
    "    # padding line 100\n"
)


class _BigView(discord.ui.View):
    """
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    padding padding padding padding padding padding padding padding padding padding padding padding
    """

    pass


def _make_command(callback):
    cmd = _types.SimpleNamespace()
    cmd.qualified_name = "fakecmd"
    cmd.callback = callback
    return cmd


def test_expand_collects_view_modal_and_legend():
    # _MenuView and _InnerModal are module-level; inspect.getsource can read them.
    # _MenuView.__module__ is "assistant.test_command_ui" which is already in sys.modules,
    # so class_namespace(_MenuView) returns this module's globals and can find _InnerModal.
    glob = {
        "discord": discord,
        "_MenuView": _MenuView,
        "_InnerModal": _InnerModal,
        "_PLUS_EMOJI": _PLUS_EMOJI,
    }

    async def cb(self, ctx):
        await _MenuView().start()

    cb.__globals__.update(glob)
    cmd = _make_command(cb)

    out = command_ui.expand_command_ui_source(cmd)
    assert "class _MenuView" in out
    assert "class _InnerModal" in out
    assert "➕" in out
    assert "fakecmd" in out


def test_expand_no_view_degrades_to_plain_source():
    glob = {"discord": discord}

    async def cb(self, ctx):
        await ctx.send("hi")

    cb.__globals__.update(glob)
    cmd = _make_command(cb)
    out = command_ui.expand_command_ui_source(cmd)
    assert "No interactive UI detected" in out
    assert "ctx.send" in out


def test_expand_respects_total_budget():
    glob = {"discord": discord, "_BigView": _BigView}

    async def cb(self, ctx):
        await _BigView().start()

    cb.__globals__.update(glob)
    cmd = _make_command(cb)
    out = command_ui.expand_command_ui_source(cmd, total_chars=2000)
    assert len(out) <= 2500
    assert "truncated" in out.lower()
