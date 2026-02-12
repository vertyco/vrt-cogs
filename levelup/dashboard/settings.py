import logging
import typing as t
from pathlib import Path

import discord
import jinja2
from pydantic import ValidationError
from redbot.core.i18n import Translator

from ..common.models import GuildSettings

if t.TYPE_CHECKING:
    from ..abc import MixinMeta

_ = Translator("LevelUp", __file__)
log = logging.getLogger("red.levelup.dashboard.settings")

root = Path(__file__).parent
static = root / "static"
templates = root / "templates"


# ── Serializers: model data → form defaults ──


def list_to_text(values: t.Iterable[t.Any]) -> str:
    return "\n".join(str(i) for i in values)


def ids_to_str_list(values: t.Iterable[int]) -> t.List[str]:
    """Convert a list of int IDs to a list of string IDs for SelectMultipleField."""
    return [str(v) for v in values]


# ── Deserializers: form submission → model data ──


def int_list_from_text(raw: str) -> t.List[int]:
    tokens = [tok.strip() for tok in raw.replace(",", "\n").splitlines() if tok.strip()]
    return [int(token) for token in tokens]


def str_list_to_int_list(values: t.List[str]) -> t.List[int]:
    """Convert SelectMultipleField string IDs back to int list."""
    return [int(v) for v in values if v]


def parse_prestige_fields(form_data: dict) -> t.Dict[int, t.Dict[str, t.Any]]:
    """Parse structured prestige tier fields from form submission."""
    parsed: t.Dict[int, t.Dict[str, t.Any]] = {}
    idx = 0
    while True:
        level_key = f"prestige_{idx}_level"
        role_key = f"prestige_{idx}_role"
        emoji_key = f"prestige_{idx}_emoji"
        emoji_url_key = f"prestige_{idx}_emoji_url"
        if level_key not in form_data:
            break
        level_val = form_data.get(level_key, "").strip()
        role_val = form_data.get(role_key, "").strip()
        emoji_val = form_data.get(emoji_key, "").strip()
        emoji_url_val = form_data.get(emoji_url_key, "").strip()
        if level_val and role_val:
            parsed[int(level_val)] = {
                "role": int(role_val),
                "emoji_string": emoji_val or "⭐",
                "emoji_url": emoji_url_val or None,
            }
        idx += 1
    return parsed


def parse_levelrole_fields(form_data: dict) -> t.Dict[int, int]:
    """Parse structured level role fields from form submission."""
    parsed: t.Dict[int, int] = {}
    idx = 0
    while True:
        level_key = f"levelrole_{idx}_level"
        role_key = f"levelrole_{idx}_role"
        if level_key not in form_data:
            break
        level_val = form_data.get(level_key, "").strip()
        role_val = form_data.get(role_key, "").strip()
        if level_val and role_val:
            parsed[int(level_val)] = int(role_val)
        idx += 1
    return parsed


def parse_bonus_fields(form_data: dict, prefix: str, key_cast: t.Callable) -> t.Dict[t.Any, t.List[int]]:
    """Parse structured bonus fields (role/channel bonus rows) from form submission."""
    parsed: t.Dict[t.Any, t.List[int]] = {}
    idx = 0
    while True:
        id_key = f"{prefix}_{idx}_id"
        min_key = f"{prefix}_{idx}_min"
        max_key = f"{prefix}_{idx}_max"
        if id_key not in form_data:
            break
        id_val = form_data.get(id_key, "").strip()
        min_val = form_data.get(min_key, "").strip()
        max_val = form_data.get(max_key, "").strip()
        if id_val and min_val and max_val:
            parsed[key_cast(id_val)] = [int(min_val), int(max_val)]
        idx += 1
    return parsed


def parse_cmd_requirement_fields(form_data: dict) -> t.Dict[str, int]:
    """Parse structured command requirement fields from form submission."""
    parsed: t.Dict[str, int] = {}
    idx = 0
    while True:
        cmd_key = f"cmdreq_{idx}_command"
        lvl_key = f"cmdreq_{idx}_level"
        if cmd_key not in form_data:
            break
        cmd_val = form_data.get(cmd_key, "").strip()
        lvl_val = form_data.get(lvl_key, "").strip()
        if cmd_val and lvl_val:
            parsed[cmd_val] = int(lvl_val)
        idx += 1
    return parsed


def parse_cmd_cooldown_fields(form_data: dict) -> t.Dict[str, t.Dict[int, int]]:
    """Parse structured command cooldown fields from form submission.

    Rows are flattened (command, level, cooldown) and grouped back by command name.
    """
    parsed: t.Dict[str, t.Dict[int, int]] = {}
    idx = 0
    while True:
        cmd_key = f"cmdcd_{idx}_command"
        lvl_key = f"cmdcd_{idx}_level"
        cd_key = f"cmdcd_{idx}_cooldown"
        if cmd_key not in form_data:
            break
        cmd_val = form_data.get(cmd_key, "").strip()
        lvl_val = form_data.get(lvl_key, "").strip()
        cd_val = form_data.get(cd_key, "").strip()
        if cmd_val and lvl_val and cd_val:
            parsed.setdefault(cmd_val, {})[int(lvl_val)] = int(cd_val)
        idx += 1
    return parsed


# ── Form rendering helpers ──


def kw(placeholder: str = "", tooltip: str = "", rows: int = 0, **extra: t.Any) -> dict:
    d: dict = {"class": "form-control", "title": tooltip, "placeholder": placeholder}
    if rows:
        d["rows"] = str(rows)
    d.update(extra)
    return d


def bool_kw(tooltip: str = "") -> dict:
    return {"class": "form-check-input", "title": tooltip}


def select_kw(tooltip: str = "") -> dict:
    return {"class": "form-select", "title": tooltip}


# ── Pre-render prestige tiers as HTML rows ──


def render_prestige_rows(conf: GuildSettings, role_choices: t.List[t.Tuple[str, str]]) -> str:
    """Build HTML for the prestige tiers dynamic table."""
    role_options = "".join(f'<option value="{rid}">{rname}</option>' for rid, rname in role_choices)

    rows: t.List[str] = []
    for idx, (level, pdata) in enumerate(sorted(conf.prestigedata.items())):
        selected_options = "".join(
            f'<option value="{rid}"{" selected" if str(rid) == str(pdata.role) else ""}>{rname}</option>'
            for rid, rname in role_choices
        )
        rows.append(
            f'<tr class="lu-dynamic-row">'
            f'<td><input type="number" name="prestige_{idx}_level" value="{level}" '
            f'class="form-control form-control-sm" min="1" placeholder="Level"></td>'
            f'<td><select name="prestige_{idx}_role" class="form-control form-control-sm">'
            f"{selected_options}</select></td>"
            f'<td><input type="text" name="prestige_{idx}_emoji" value="{pdata.emoji_string}" '
            f'class="form-control form-control-sm" placeholder="⭐"></td>'
            f'<td><input type="text" name="prestige_{idx}_emoji_url" value="{pdata.emoji_url or ""}" '
            f'class="form-control form-control-sm" placeholder="https://..."></td>'
            f'<td><button type="button" class="btn btn-sm btn-outline-danger lu-remove-row" '
            f'title="Remove"><i class="ni ni-fat-remove"></i></button></td>'
            f"</tr>"
        )

    # Template row HTML stored in a <script> tag to avoid Choices.js auto-init
    template_row = (
        '<tr class="lu-dynamic-row">'
        '<td><input type="number" name="prestige_NEW_level" '
        'class="form-control form-control-sm" min="1" placeholder="Level"></td>'
        f'<td><select name="prestige_NEW_role" class="form-control form-control-sm">'
        f"{role_options}</select></td>"
        '<td><input type="text" name="prestige_NEW_emoji" '
        'class="form-control form-control-sm" placeholder="⭐"></td>'
        '<td><input type="text" name="prestige_NEW_emoji_url" '
        'class="form-control form-control-sm" placeholder="https://..."></td>'
        '<td><button type="button" class="btn btn-sm btn-outline-danger lu-remove-row" '
        'title="Remove"><i class="ni ni-fat-remove"></i></button></td>'
        "</tr>"
    )

    return (
        '<table class="table table-sm lu-dynamic-table" data-prefix="prestige">'
        "<thead><tr>"
        '<th style="width:15%">Level</th>'
        '<th style="width:30%">Role</th>'
        '<th style="width:20%">Emoji</th>'
        '<th style="width:25%">Emoji URL</th>'
        '<th style="width:10%"></th>'
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        '<tfoot><tr><td colspan="5">'
        '<button type="button" class="btn btn-sm btn-outline-primary lu-add-row">'
        '<i class="ni ni-fat-add me-1"></i>Add Tier</button>'
        "</td></tr></tfoot>"
        "</table>"
        f'<script type="text/html" class="lu-row-template" data-table="prestige">{template_row}</script>'
    )


def render_levelrole_rows(conf: GuildSettings, role_choices: t.List[t.Tuple[str, str]]) -> str:
    """Build HTML for the level-role mapping dynamic table."""
    role_options = "".join(f'<option value="{rid}">{rname}</option>' for rid, rname in role_choices)

    rows: t.List[str] = []
    for idx, (level, role_id) in enumerate(sorted(conf.levelroles.items())):
        selected_options = "".join(
            f'<option value="{rid}"{" selected" if str(rid) == str(role_id) else ""}>{rname}</option>'
            for rid, rname in role_choices
        )
        rows.append(
            f'<tr class="lu-dynamic-row">'
            f'<td><input type="number" name="levelrole_{idx}_level" value="{level}" '
            f'class="form-control form-control-sm" min="1" placeholder="Level"></td>'
            f'<td><select name="levelrole_{idx}_role" class="form-control form-control-sm">'
            f"{selected_options}</select></td>"
            f'<td><button type="button" class="btn btn-sm btn-outline-danger lu-remove-row" '
            f'title="Remove"><i class="ni ni-fat-remove"></i></button></td>'
            f"</tr>"
        )

    template_row = (
        '<tr class="lu-dynamic-row">'
        '<td><input type="number" name="levelrole_NEW_level" '
        'class="form-control form-control-sm" min="1" placeholder="Level"></td>'
        f'<td><select name="levelrole_NEW_role" class="form-control form-control-sm">'
        f"{role_options}</select></td>"
        '<td><button type="button" class="btn btn-sm btn-outline-danger lu-remove-row" '
        'title="Remove"><i class="ni ni-fat-remove"></i></button></td>'
        "</tr>"
    )

    return (
        '<table class="table table-sm lu-dynamic-table" data-prefix="levelrole">'
        "<thead><tr>"
        '<th style="width:30%">Level</th>'
        '<th style="width:55%">Role</th>'
        '<th style="width:15%"></th>'
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        '<tfoot><tr><td colspan="3">'
        '<button type="button" class="btn btn-sm btn-outline-primary lu-add-row">'
        '<i class="ni ni-fat-add me-1"></i>Add Role Mapping</button>'
        "</td></tr></tfoot>"
        "</table>"
        f'<script type="text/html" class="lu-row-template" data-table="levelrole">{template_row}</script>'
    )


def render_bonus_rows(
    data: t.Dict[t.Any, t.List[int]],
    prefix: str,
    id_label: str,
    id_placeholder: str,
    choices: t.Optional[t.List[t.Tuple[str, str]]] = None,
) -> str:
    """Build HTML for bonus mapping dynamic tables (role/channel/presence/app bonuses)."""
    rows: t.List[str] = []
    for idx, (key, pair) in enumerate(data.items()):
        if choices:
            selected_options = "".join(
                f'<option value="{cid}"{" selected" if str(cid) == str(key) else ""}>{cname}</option>'
                for cid, cname in choices
            )
            id_cell = (
                f'<select name="{prefix}_{idx}_id" class="form-control form-control-sm">{selected_options}</select>'
            )
        else:
            id_cell = (
                f'<input type="text" name="{prefix}_{idx}_id" value="{key}" '
                f'class="form-control form-control-sm" placeholder="{id_placeholder}">'
            )
        rows.append(
            f'<tr class="lu-dynamic-row">'
            f"<td>{id_cell}</td>"
            f'<td><input type="number" name="{prefix}_{idx}_min" value="{pair[0]}" '
            f'class="form-control form-control-sm" placeholder="Min"></td>'
            f'<td><input type="number" name="{prefix}_{idx}_max" value="{pair[1]}" '
            f'class="form-control form-control-sm" placeholder="Max"></td>'
            f'<td><button type="button" class="btn btn-sm btn-outline-danger lu-remove-row" '
            f'title="Remove"><i class="ni ni-fat-remove"></i></button></td>'
            f"</tr>"
        )

    # Template row
    if choices:
        options_html = "".join(f'<option value="{cid}">{cname}</option>' for cid, cname in choices)
        id_template = f'<select name="{prefix}_NEW_id" class="form-control form-control-sm">{options_html}</select>'
    else:
        id_template = (
            f'<input type="text" name="{prefix}_NEW_id" '
            f'class="form-control form-control-sm" placeholder="{id_placeholder}">'
        )
    template_row = (
        f'<tr class="lu-dynamic-row">'
        f"<td>{id_template}</td>"
        f'<td><input type="number" name="{prefix}_NEW_min" '
        f'class="form-control form-control-sm" placeholder="Min"></td>'
        f'<td><input type="number" name="{prefix}_NEW_max" '
        f'class="form-control form-control-sm" placeholder="Max"></td>'
        f'<td><button type="button" class="btn btn-sm btn-outline-danger lu-remove-row" '
        f'title="Remove"><i class="ni ni-fat-remove"></i></button></td>'
        f"</tr>"
    )

    return (
        f'<table class="table table-sm lu-dynamic-table" data-prefix="{prefix}">'
        f"<thead><tr>"
        f'<th style="width:40%">{id_label}</th>'
        f'<th style="width:22%">Min XP</th>'
        f'<th style="width:22%">Max XP</th>'
        f'<th style="width:16%"></th>'
        f"</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        f'<tfoot><tr><td colspan="4">'
        f'<button type="button" class="btn btn-sm btn-outline-primary lu-add-row">'
        f'<i class="ni ni-fat-add me-1"></i>Add Bonus</button>'
        f"</td></tr></tfoot>"
        f"</table>"
        f'<script type="text/html" class="lu-row-template" data-table="{prefix}">{template_row}</script>'
    )


def render_cmd_requirements_rows(conf: GuildSettings) -> str:
    """Build HTML for the command requirements dynamic table."""
    rows: t.List[str] = []
    for idx, (command, level) in enumerate(sorted(conf.cmd_requirements.items())):
        rows.append(
            f'<tr class="lu-dynamic-row">'
            f'<td><input type="text" name="cmdreq_{idx}_command" value="{command}" '
            f'class="form-control form-control-sm" placeholder="commandname"></td>'
            f'<td><input type="number" name="cmdreq_{idx}_level" value="{level}" '
            f'class="form-control form-control-sm" min="1" placeholder="10"></td>'
            f'<td><button type="button" class="btn btn-sm btn-outline-danger lu-remove-row" '
            f'title="Remove"><i class="ni ni-fat-remove"></i></button></td>'
            f"</tr>"
        )

    template_row = (
        '<tr class="lu-dynamic-row">'
        '<td><input type="text" name="cmdreq_NEW_command" '
        'class="form-control form-control-sm" placeholder="commandname"></td>'
        '<td><input type="number" name="cmdreq_NEW_level" '
        'class="form-control form-control-sm" min="1" placeholder="10"></td>'
        '<td><button type="button" class="btn btn-sm btn-outline-danger lu-remove-row" '
        'title="Remove"><i class="ni ni-fat-remove"></i></button></td>'
        "</tr>"
    )

    return (
        '<table class="table table-sm lu-dynamic-table" data-prefix="cmdreq">'
        "<thead><tr>"
        '<th style="width:50%">Command</th>'
        '<th style="width:35%">Required Level</th>'
        '<th style="width:15%"></th>'
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        '<tfoot><tr><td colspan="3">'
        '<button type="button" class="btn btn-sm btn-outline-primary lu-add-row">'
        '<i class="ni ni-fat-add me-1"></i>Add Requirement</button>'
        "</td></tr></tfoot>"
        "</table>"
        f'<script type="text/html" class="lu-row-template" data-table="cmdreq">{template_row}</script>'
    )


def render_cmd_cooldowns_rows(conf: GuildSettings) -> str:
    """Build HTML for the command cooldowns dynamic table.

    Flattens Dict[str, Dict[int, int]] into individual rows: command | level | cooldown.
    """
    rows: t.List[str] = []
    idx = 0
    for command, levels in sorted(conf.cmd_cooldowns.items()):
        for level, cooldown in sorted(levels.items()):
            rows.append(
                f'<tr class="lu-dynamic-row">'
                f'<td><input type="text" name="cmdcd_{idx}_command" value="{command}" '
                f'class="form-control form-control-sm" placeholder="commandname"></td>'
                f'<td><input type="number" name="cmdcd_{idx}_level" value="{level}" '
                f'class="form-control form-control-sm" min="0" placeholder="5"></td>'
                f'<td><input type="number" name="cmdcd_{idx}_cooldown" value="{cooldown}" '
                f'class="form-control form-control-sm" min="0" placeholder="30"></td>'
                f'<td><button type="button" class="btn btn-sm btn-outline-danger lu-remove-row" '
                f'title="Remove"><i class="ni ni-fat-remove"></i></button></td>'
                f"</tr>"
            )
            idx += 1

    template_row = (
        '<tr class="lu-dynamic-row">'
        '<td><input type="text" name="cmdcd_NEW_command" '
        'class="form-control form-control-sm" placeholder="commandname"></td>'
        '<td><input type="number" name="cmdcd_NEW_level" '
        'class="form-control form-control-sm" min="0" placeholder="5"></td>'
        '<td><input type="number" name="cmdcd_NEW_cooldown" '
        'class="form-control form-control-sm" min="0" placeholder="30"></td>'
        '<td><button type="button" class="btn btn-sm btn-outline-danger lu-remove-row" '
        'title="Remove"><i class="ni ni-fat-remove"></i></button></td>'
        "</tr>"
    )

    return (
        '<table class="table table-sm lu-dynamic-table" data-prefix="cmdcd">'
        "<thead><tr>"
        '<th style="width:35%">Command</th>'
        '<th style="width:22%">Level</th>'
        '<th style="width:28%">Cooldown (sec)</th>'
        '<th style="width:15%"></th>'
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        '<tfoot><tr><td colspan="4">'
        '<button type="button" class="btn btn-sm btn-outline-primary lu-add-row">'
        '<i class="ni ni-fat-add me-1"></i>Add Cooldown</button>'
        "</td></tr></tfoot>"
        "</table>"
        f'<script type="text/html" class="lu-row-template" data-table="cmdcd">{template_row}</script>'
    )


# ── Main settings page handler ──


async def handle_settings_page(
    cog: "MixinMeta",
    user: discord.User,
    guild: discord.Guild,
    **kwargs: t.Any,
) -> t.Dict[str, t.Any]:
    import wtforms

    log.info(f"Getting settings for {guild.name} by {user.name}")
    member = guild.get_member(user.id)
    if not member:
        log.warning(f"Member {user.name} not found in guild {guild.name}")
        return {
            "status": 1,
            "error_title": _("Member not found"),
            "error_message": _("You are not a member of this guild."),
        }
    if not await cog.bot.is_admin(member):
        log.warning(f"Member {user.name} is not an admin in guild {guild.name}")
        return {
            "status": 1,
            "error_title": _("Insufficient permissions"),
            "error_message": _("You need to be an admin to access this page."),
        }

    conf = cog.db.get_conf(guild)

    # Get channel/role choices from the dashboard helpers
    channel_choices = kwargs["get_sorted_channels"](guild, filter_func=None)
    role_choices = kwargs["get_sorted_roles"](guild, filter_func=None)

    style_choices = [
        ("", _("None (use user preference)")),
        ("default", _("Default")),
        ("minimal", _("Minimal")),
        ("gaming", _("Gaming")),
        ("runescape", _("Runescape")),
    ]
    day_choices = [
        ("0", _("Monday")),
        ("1", _("Tuesday")),
        ("2", _("Wednesday")),
        ("3", _("Thursday")),
        ("4", _("Friday")),
        ("5", _("Saturday")),
        ("6", _("Sunday")),
    ]
    hour_choices = [(str(h), f"{h:02d}:00") for h in range(24)]

    class SettingsForm(kwargs["Form"]):
        def __init__(self) -> None:
            super().__init__(prefix="levelup_settings_form_")

        # ── General ──
        enabled = wtforms.BooleanField(
            _("Enable Leveling"),
            default=conf.enabled,
            render_kw=bool_kw(_("Master toggle for the entire leveling system in this guild.")),
        )
        use_embeds = wtforms.BooleanField(
            _("Use Embeds for Profiles"),
            default=conf.use_embeds,
            render_kw=bool_kw(_("Show profiles as embeds instead of generated images.")),
        )
        showbal = wtforms.BooleanField(
            _("Show Economy Balance"),
            default=conf.showbal,
            render_kw=bool_kw(_("Display the user's Red economy balance on their profile card.")),
        )
        autoremove = wtforms.BooleanField(
            _("Auto-Remove Previous Level Role"),
            default=conf.autoremove,
            render_kw=bool_kw(_("Remove the previous level role when a new one is earned.")),
        )
        style_override = wtforms.SelectField(
            _("Guild Style Override"),
            choices=style_choices,
            default=conf.style_override or "",
            render_kw=select_kw(_("Force a specific profile style for all members.")),
        )
        default_background = wtforms.StringField(
            _("Default Background"),
            default=conf.default_background,
            render_kw=kw(
                placeholder="default",
                tooltip=_("Default profile background for all members. Use 'default', a filename, or a URL."),
            ),
        )
        show_profile_welcome = wtforms.BooleanField(
            _("Show Profile Welcome"),
            default=conf.show_profile_welcome,
            render_kw=bool_kw(_("Show tutorial/welcome message on first profile command.")),
        )

        # ── Algorithm & XP ──
        algo_base = wtforms.IntegerField(
            _("Algorithm Base"),
            default=conf.algorithm.base,
            render_kw=kw(
                placeholder="100", tooltip=_("Base value for the leveling formula. Higher = slower leveling.")
            ),
        )
        algo_exp = wtforms.FloatField(
            _("Algorithm Exponent"),
            default=conf.algorithm.exp,
            render_kw=kw(placeholder="2.0", tooltip=_("Exponent for the leveling curve. Higher = more exponential.")),
        )
        xp_min = wtforms.IntegerField(
            _("Message XP Min"),
            default=conf.xp[0],
            render_kw=kw(placeholder="3", tooltip=_("Minimum XP awarded per qualifying message.")),
        )
        xp_max = wtforms.IntegerField(
            _("Message XP Max"),
            default=conf.xp[1],
            render_kw=kw(placeholder="6", tooltip=_("Maximum XP awarded per qualifying message.")),
        )
        command_xp = wtforms.BooleanField(
            _("Give XP for Commands"),
            default=conf.command_xp,
            render_kw=bool_kw(_("Award XP when members use bot commands.")),
        )
        cooldown = wtforms.IntegerField(
            _("Message Cooldown"),
            default=conf.cooldown,
            render_kw=kw(placeholder="60", tooltip=_("Seconds between XP-eligible messages per user.")),
        )
        min_length = wtforms.IntegerField(
            _("Min Message Length"),
            default=conf.min_length,
            render_kw=kw(
                placeholder="0", tooltip=_("Minimum character count for a message to earn XP. 0 = no minimum.")
            ),
        )

        # ── Anti-Spam ──
        antispam_enabled = wtforms.BooleanField(
            _("Enable Anti-Spam"),
            default=conf.antispam.enabled,
            render_kw=bool_kw(_("Detect and reject repetitive/similar messages from earning XP.")),
        )
        antispam_similarity_threshold = wtforms.IntegerField(
            _("Similarity Threshold"),
            default=conf.antispam.similarity_threshold,
            render_kw=kw(
                placeholder="85", tooltip=_("0-100. How similar messages can be before flagged. Higher = stricter.")
            ),
        )
        antispam_history_size = wtforms.IntegerField(
            _("History Size"),
            default=conf.antispam.history_size,
            render_kw=kw(placeholder="5", tooltip=_("Number of recent messages to compare against for similarity.")),
        )
        antispam_min_unique_ratio = wtforms.FloatField(
            _("Min Unique Word Ratio"),
            default=conf.antispam.min_unique_ratio,
            render_kw=kw(placeholder="0.4", tooltip=_("0.0-1.0. Minimum ratio of unique words in a message.")),
        )

        # ── Voice ──
        voicexp = wtforms.IntegerField(
            _("Voice XP per Minute"),
            default=conf.voicexp,
            render_kw=kw(placeholder="2", tooltip=_("XP awarded per minute spent in a voice channel.")),
        )
        ignore_muted = wtforms.BooleanField(
            _("Ignore Self-Muted"),
            default=conf.ignore_muted,
            render_kw=bool_kw(_("Don't award voice XP to self-muted members.")),
        )
        ignore_solo = wtforms.BooleanField(
            _("Ignore Solo"),
            default=conf.ignore_solo,
            render_kw=bool_kw(_("Don't award voice XP when alone in a channel (bots excluded).")),
        )
        ignore_deafened = wtforms.BooleanField(
            _("Ignore Self-Deafened"),
            default=conf.ignore_deafened,
            render_kw=bool_kw(_("Don't award voice XP to self-deafened members.")),
        )
        ignore_invisible = wtforms.BooleanField(
            _("Ignore Invisible"),
            default=conf.ignore_invisible,
            render_kw=bool_kw(_("Don't award voice XP to members with invisible status.")),
        )
        streambonus_min = wtforms.IntegerField(
            _("Stream Bonus Min"),
            default=conf.streambonus[0] if len(conf.streambonus) >= 2 else 0,
            render_kw=kw(placeholder="0", tooltip=_("Extra minimum voice XP bonus per minute while streaming.")),
        )
        streambonus_max = wtforms.IntegerField(
            _("Stream Bonus Max"),
            default=conf.streambonus[1] if len(conf.streambonus) >= 2 else 0,
            render_kw=kw(placeholder="0", tooltip=_("Extra maximum voice XP bonus per minute while streaming.")),
        )

        # ── Filters (multi-select dropdowns) ──
        allowedchannels = wtforms.SelectMultipleField(
            _("Allowed Channels"),
            choices=[],
            default=ids_to_str_list(conf.allowedchannels),
            render_kw=select_kw(_("Only these channels will earn XP. Leave empty to allow all.")),
        )
        allowedroles = wtforms.SelectMultipleField(
            _("Allowed Roles"),
            choices=[],
            default=ids_to_str_list(conf.allowedroles),
            render_kw=select_kw(_("Only members with these roles will earn XP. Leave empty to allow all.")),
        )
        ignoredchannels = wtforms.SelectMultipleField(
            _("Ignored Channels"),
            choices=[],
            default=ids_to_str_list(conf.ignoredchannels),
            render_kw=select_kw(_("These channels will never earn XP.")),
        )
        ignoredroles = wtforms.SelectMultipleField(
            _("Ignored Roles"),
            choices=[],
            default=ids_to_str_list(conf.ignoredroles),
            render_kw=select_kw(_("Members with these roles will not earn XP.")),
        )
        ignoredusers = wtforms.TextAreaField(
            _("Ignored Users"),
            default=list_to_text(conf.ignoredusers),
            render_kw=kw(
                placeholder="One user ID per line\n123456789012345678\n987654321098765432",
                tooltip=_("User IDs that will never earn XP. One per line."),
                rows=3,
            ),
        )
        ignore_notification_channels = wtforms.SelectMultipleField(
            _("Muted Notification Channels"),
            choices=[],
            default=ids_to_str_list(conf.ignore_notification_channels),
            render_kw=select_kw(_("Level-up announcements will not be sent in these channels.")),
        )
        cmd_bypass_roles = wtforms.SelectMultipleField(
            _("Command Bypass Roles"),
            choices=[],
            default=ids_to_str_list(conf.cmd_bypass_roles),
            render_kw=select_kw(_("These roles bypass command level requirements and cooldowns.")),
        )
        cmd_bypass_member = wtforms.SelectMultipleField(
            _("Command Bypass Members"),
            choices=[],
            default=ids_to_str_list(conf.cmd_bypass_member),
            render_kw=select_kw(_("Members that bypass command level requirements and cooldowns.")),
        )

        # ── Alerts ──
        notify = wtforms.BooleanField(
            _("Announce in Current Channel"),
            default=conf.notify,
            render_kw=bool_kw(_("Send level-up messages in the channel where the user earned XP.")),
        )
        notifylog = wtforms.SelectField(
            _("Log Channel"),
            choices=[],
            default=str(conf.notifylog) if conf.notifylog else "",
            render_kw=select_kw(_("Channel for level-up log messages.")),
        )
        notifydm = wtforms.BooleanField(
            _("DM on Level Up"),
            default=conf.notifydm,
            render_kw=bool_kw(_("Send a DM to the member when they level up.")),
        )
        notifymention = wtforms.BooleanField(
            _("Mention User"),
            default=conf.notifymention,
            render_kw=bool_kw(_("@mention the user in level-up announcements.")),
        )
        role_awarded_dm = wtforms.TextAreaField(
            _("Role Awarded DM"),
            default=conf.role_awarded_dm,
            render_kw=kw(
                placeholder="{role} has been awarded!",
                tooltip=_("Custom DM message when a level role is awarded. Supports {role}, {level}, {user}."),
                rows=2,
            ),
        )
        levelup_dm = wtforms.TextAreaField(
            _("Level Up DM"),
            default=conf.levelup_dm,
            render_kw=kw(
                placeholder="You reached level {level}!",
                tooltip=_("Custom DM message on level up. Supports {level}, {user}."),
                rows=2,
            ),
        )
        role_awarded_msg = wtforms.TextAreaField(
            _("Role Awarded Message"),
            default=conf.role_awarded_msg or "",
            render_kw=kw(
                placeholder="{user} earned {role}!",
                tooltip=_("Custom guild message when a level role is awarded. Supports {role}, {level}, {user}."),
                rows=2,
            ),
        )
        levelup_msg = wtforms.TextAreaField(
            _("Level Up Message"),
            default=conf.levelup_msg or "",
            render_kw=kw(
                placeholder="{user} reached level {level}!",
                tooltip=_("Custom guild message on level up. Supports {level}, {user}."),
                rows=2,
            ),
        )

        # ── Stars ──
        starcooldown = wtforms.IntegerField(
            _("Star Cooldown"),
            default=conf.starcooldown,
            render_kw=kw(placeholder="3600", tooltip=_("Seconds between giving stars to the same person.")),
        )
        starmention = wtforms.BooleanField(
            _("Star Mention"),
            default=conf.starmention,
            render_kw=bool_kw(_("Send a message when someone gives a star.")),
        )
        starmentionautodelete = wtforms.IntegerField(
            _("Star Auto-Delete"),
            default=conf.starmentionautodelete,
            render_kw=kw(placeholder="0", tooltip=_("Auto-delete star mention messages after N seconds. 0 = don't.")),
        )

        # ── Prestige ──
        prestigelevel = wtforms.IntegerField(
            _("Required Level"),
            default=conf.prestigelevel,
            render_kw=kw(placeholder="0", tooltip=_("Level required to prestige. 0 = prestige disabled.")),
        )
        stackprestigeroles = wtforms.BooleanField(
            _("Stack Prestige Roles"),
            default=conf.stackprestigeroles,
            render_kw=bool_kw(_("Keep all earned prestige roles instead of only the latest.")),
        )
        keep_level_roles = wtforms.BooleanField(
            _("Keep Level Roles on Prestige"),
            default=conf.keep_level_roles,
            render_kw=bool_kw(_("Don't remove level roles when a member prestiges.")),
        )

        # ── Weekly ──
        weekly_on = wtforms.BooleanField(
            _("Enable Weekly Stats"),
            default=conf.weeklysettings.on,
            render_kw=bool_kw(_("Track a weekly leaderboard alongside the all-time one.")),
        )
        weekly_autoreset = wtforms.BooleanField(
            _("Auto Reset"),
            default=conf.weeklysettings.autoreset,
            render_kw=bool_kw(_("Automatically reset the weekly leaderboard on the scheduled day.")),
        )
        weekly_reset_hour = wtforms.SelectField(
            _("Reset Hour"),
            choices=hour_choices,
            default=str(conf.weeklysettings.reset_hour),
            render_kw=select_kw(_("Hour of day (server time) for the weekly reset.")),
        )
        weekly_reset_day = wtforms.SelectField(
            _("Reset Day"),
            choices=day_choices,
            default=str(conf.weeklysettings.reset_day),
            render_kw=select_kw(_("Day of the week for the weekly reset.")),
        )
        weekly_count = wtforms.IntegerField(
            _("Winner Count"),
            default=conf.weeklysettings.count,
            render_kw=kw(placeholder="3", tooltip=_("Number of top members announced as weekly winners.")),
        )
        weekly_channel = wtforms.SelectField(
            _("Announcement Channel"),
            choices=[],
            default=str(conf.weeklysettings.channel) if conf.weeklysettings.channel else "",
            render_kw=select_kw(_("Channel to post weekly winner announcements.")),
        )
        weekly_role = wtforms.SelectField(
            _("Winner Role"),
            choices=[],
            default=str(conf.weeklysettings.role) if conf.weeklysettings.role else "",
            render_kw=select_kw(_("Role awarded to the weekly winner(s).")),
        )
        weekly_role_all = wtforms.BooleanField(
            _("Role for All Winners"),
            default=conf.weeklysettings.role_all,
            render_kw=bool_kw(_("Give the winner role to all top members, not just 1st place.")),
        )
        weekly_remove = wtforms.BooleanField(
            _("Remove Previous Roles"),
            default=conf.weeklysettings.remove,
            render_kw=bool_kw(_("Remove winner role(s) from last week's winners on reset.")),
        )
        weekly_bonus = wtforms.IntegerField(
            _("Bonus XP"),
            default=conf.weeklysettings.bonus,
            render_kw=kw(placeholder="0", tooltip=_("Bonus XP awarded to each weekly winner.")),
        )
        weekly_ping_winners = wtforms.BooleanField(
            _("Ping Winners"),
            default=conf.weeklysettings.ping_winners,
            render_kw=bool_kw(_("@mention winners in the weekly announcement.")),
        )
        weekly_excluded_roles = wtforms.SelectMultipleField(
            _("Excluded Roles"),
            choices=[],
            default=ids_to_str_list(conf.weeklysettings.excluded_roles),
            render_kw=select_kw(_("Roles excluded from winning the weekly leaderboard role.")),
        )
        weekly_bonus_roles = wtforms.SelectMultipleField(
            _("Bonus Roles"),
            choices=[],
            default=ids_to_str_list(conf.weeklysettings.bonus_roles),
            render_kw=select_kw(_("Additional roles awarded alongside the main winner role.")),
        )

        # ── Emojis ──
        emoji_level = wtforms.StringField(
            _("Level"), default=str(conf.emojis.level), render_kw=kw(placeholder="🏅", tooltip=_("Emoji for levels."))
        )
        emoji_trophy = wtforms.StringField(
            _("Trophy"),
            default=str(conf.emojis.trophy),
            render_kw=kw(placeholder="🏆", tooltip=_("Emoji for prestige.")),
        )
        emoji_star = wtforms.StringField(
            _("Star"), default=str(conf.emojis.star), render_kw=kw(placeholder="⭐", tooltip=_("Emoji for stars."))
        )
        emoji_chat = wtforms.StringField(
            _("Chat"), default=str(conf.emojis.chat), render_kw=kw(placeholder="💬", tooltip=_("Emoji for messages."))
        )
        emoji_mic = wtforms.StringField(
            _("Mic"), default=str(conf.emojis.mic), render_kw=kw(placeholder="🎙️", tooltip=_("Emoji for voice time."))
        )
        emoji_bulb = wtforms.StringField(
            _("Bulb"), default=str(conf.emojis.bulb), render_kw=kw(placeholder="💡", tooltip=_("Emoji for tips."))
        )
        emoji_money = wtforms.StringField(
            _("Money"), default=str(conf.emojis.money), render_kw=kw(placeholder="💰", tooltip=_("Emoji for balance."))
        )

        # ── Role Groups & Mappings ──
        role_groups = wtforms.SelectMultipleField(
            _("Role Groups"),
            choices=[],
            default=ids_to_str_list(conf.role_groups.keys()),
            render_kw=select_kw(_("Roles that accumulate XP as a group from all members with the role.")),
        )

        submit = wtforms.SubmitField(_("Save Settings"))

    form = SettingsForm()

    # Assign choices to multi-select and single-select fields AFTER instantiation
    none_channel = [("", _("— None —"))]
    none_role = [("", _("— None —"))]

    form.allowedchannels.choices = channel_choices
    form.allowedroles.choices = role_choices
    form.ignoredchannels.choices = channel_choices
    form.ignoredroles.choices = role_choices
    form.ignore_notification_channels.choices = channel_choices
    form.cmd_bypass_roles.choices = role_choices
    member_choices = sorted(
        [(str(m.id), m.display_name) for m in guild.members if not m.bot],
        key=lambda x: x[1].lower(),
    )
    form.cmd_bypass_member.choices = member_choices

    form.notifylog.choices = none_channel + channel_choices
    form.weekly_channel.choices = none_channel + channel_choices
    form.weekly_role.choices = none_role + role_choices
    form.weekly_excluded_roles.choices = role_choices
    form.weekly_bonus_roles.choices = role_choices
    form.role_groups.choices = role_choices

    # Pre-render structured HTML for dynamic tables
    prestige_html = render_prestige_rows(conf, role_choices)
    levelrole_html = render_levelrole_rows(conf, role_choices)
    rolebonus_msg_html = render_bonus_rows(conf.rolebonus.msg, "rolebonus_msg", _("Role"), "", choices=role_choices)
    rolebonus_voice_html = render_bonus_rows(
        conf.rolebonus.voice, "rolebonus_voice", _("Role"), "", choices=role_choices
    )
    channelbonus_msg_html = render_bonus_rows(
        conf.channelbonus.msg, "channelbonus_msg", _("Channel"), "", choices=channel_choices
    )
    channelbonus_voice_html = render_bonus_rows(
        conf.channelbonus.voice, "channelbonus_voice", _("Channel"), "", choices=channel_choices
    )
    status_choices = [
        ("online", _("Online")),
        ("dnd", _("Do Not Disturb")),
        ("idle", _("Idle")),
        ("offline", _("Offline")),
    ]
    presencebonus_msg_html = render_bonus_rows(
        conf.presencebonus.msg, "presencebonus_msg", _("Status"), "online", choices=status_choices
    )
    presencebonus_voice_html = render_bonus_rows(
        conf.presencebonus.voice, "presencebonus_voice", _("Status"), "online", choices=status_choices
    )
    appbonus_msg_html = render_bonus_rows(conf.appbonus.msg, "appbonus_msg", _("App Name"), "Spotify")
    appbonus_voice_html = render_bonus_rows(conf.appbonus.voice, "appbonus_voice", _("App Name"), "Spotify")
    cmd_requirements_html = render_cmd_requirements_rows(conf)
    cmd_cooldowns_html = render_cmd_cooldowns_rows(conf)

    # ── Handle POST ──
    if form.validate_on_submit() and await form.validate_dpy_converters():
        try:
            payload = conf.dump(exclued_defaults=False)

            # General
            payload["enabled"] = bool(form.enabled.data)
            payload["use_embeds"] = bool(form.use_embeds.data)
            payload["showbal"] = bool(form.showbal.data)
            payload["autoremove"] = bool(form.autoremove.data)
            style_val = (form.style_override.data or "").strip()
            payload["style_override"] = style_val if style_val else None
            payload["default_background"] = (form.default_background.data or "default").strip() or "default"
            payload["show_profile_welcome"] = bool(form.show_profile_welcome.data)

            # Algorithm & XP
            payload["algorithm"]["base"] = int(form.algo_base.data)
            payload["algorithm"]["exp"] = float(form.algo_exp.data)
            xp_min = int(form.xp_min.data)
            xp_max = int(form.xp_max.data)
            if xp_min > xp_max:
                raise ValueError("Message XP Min cannot be greater than Message XP Max")
            payload["xp"] = [xp_min, xp_max]
            payload["command_xp"] = bool(form.command_xp.data)
            payload["cooldown"] = int(form.cooldown.data)
            payload["min_length"] = int(form.min_length.data)

            # Anti-Spam
            payload["antispam"]["enabled"] = bool(form.antispam_enabled.data)
            payload["antispam"]["similarity_threshold"] = int(form.antispam_similarity_threshold.data)
            payload["antispam"]["history_size"] = int(form.antispam_history_size.data)
            payload["antispam"]["min_unique_ratio"] = float(form.antispam_min_unique_ratio.data)

            # Voice
            payload["voicexp"] = int(form.voicexp.data)
            payload["ignore_muted"] = bool(form.ignore_muted.data)
            payload["ignore_solo"] = bool(form.ignore_solo.data)
            payload["ignore_deafened"] = bool(form.ignore_deafened.data)
            payload["ignore_invisible"] = bool(form.ignore_invisible.data)
            stream_min = int(form.streambonus_min.data)
            stream_max = int(form.streambonus_max.data)
            if stream_min == 0 and stream_max == 0:
                payload["streambonus"] = []
            else:
                if stream_min > stream_max:
                    raise ValueError("Stream Bonus Min cannot be greater than Stream Bonus Max")
                payload["streambonus"] = [stream_min, stream_max]

            # Filters (multi-select returns list of string IDs)
            payload["allowedchannels"] = str_list_to_int_list(form.allowedchannels.data or [])
            payload["allowedroles"] = str_list_to_int_list(form.allowedroles.data or [])
            payload["ignoredchannels"] = str_list_to_int_list(form.ignoredchannels.data or [])
            payload["ignoredroles"] = str_list_to_int_list(form.ignoredroles.data or [])
            payload["ignoredusers"] = int_list_from_text(form.ignoredusers.data or "")
            payload["ignore_notification_channels"] = str_list_to_int_list(form.ignore_notification_channels.data or [])
            payload["cmd_bypass_roles"] = str_list_to_int_list(form.cmd_bypass_roles.data or [])
            payload["cmd_bypass_member"] = str_list_to_int_list(form.cmd_bypass_member.data or [])

            # Alerts
            payload["notify"] = bool(form.notify.data)
            notifylog_val = form.notifylog.data or ""
            payload["notifylog"] = int(notifylog_val) if notifylog_val else 0
            payload["notifydm"] = bool(form.notifydm.data)
            payload["notifymention"] = bool(form.notifymention.data)
            payload["role_awarded_dm"] = form.role_awarded_dm.data or ""
            payload["levelup_dm"] = form.levelup_dm.data or ""
            payload["role_awarded_msg"] = form.role_awarded_msg.data or ""
            payload["levelup_msg"] = form.levelup_msg.data or ""

            # Stars
            payload["starcooldown"] = int(form.starcooldown.data)
            payload["starmention"] = bool(form.starmention.data)
            payload["starmentionautodelete"] = int(form.starmentionautodelete.data)

            # Prestige
            payload["prestigelevel"] = int(form.prestigelevel.data)
            payload["stackprestigeroles"] = bool(form.stackprestigeroles.data)
            payload["keep_level_roles"] = bool(form.keep_level_roles.data)

            # Parse structured prestige/levelrole/bonus fields from raw form data
            raw_form = kwargs["data"]["form"]
            payload["prestigedata"] = parse_prestige_fields(raw_form)
            payload["levelroles"] = parse_levelrole_fields(raw_form)

            # Role groups: preserve existing XP for roles still selected, add 0 for new
            selected_role_ids = str_list_to_int_list(form.role_groups.data or [])
            existing_groups = conf.role_groups
            payload["role_groups"] = {rid: existing_groups.get(rid, 0) for rid in selected_role_ids}

            # Weekly
            payload["weeklysettings"]["on"] = bool(form.weekly_on.data)
            payload["weeklysettings"]["autoreset"] = bool(form.weekly_autoreset.data)
            payload["weeklysettings"]["reset_hour"] = int(form.weekly_reset_hour.data)
            payload["weeklysettings"]["reset_day"] = int(form.weekly_reset_day.data)
            payload["weeklysettings"]["count"] = int(form.weekly_count.data)
            weekly_ch = form.weekly_channel.data or ""
            payload["weeklysettings"]["channel"] = int(weekly_ch) if weekly_ch else 0
            weekly_rl = form.weekly_role.data or ""
            payload["weeklysettings"]["role"] = int(weekly_rl) if weekly_rl else 0
            payload["weeklysettings"]["role_all"] = bool(form.weekly_role_all.data)
            payload["weeklysettings"]["remove"] = bool(form.weekly_remove.data)
            payload["weeklysettings"]["bonus"] = int(form.weekly_bonus.data)
            payload["weeklysettings"]["ping_winners"] = bool(form.weekly_ping_winners.data)
            payload["weeklysettings"]["excluded_roles"] = str_list_to_int_list(form.weekly_excluded_roles.data or [])
            payload["weeklysettings"]["bonus_roles"] = str_list_to_int_list(form.weekly_bonus_roles.data or [])

            # Emojis
            payload["emojis"]["level"] = (form.emoji_level.data or "").strip()
            payload["emojis"]["trophy"] = (form.emoji_trophy.data or "").strip()
            payload["emojis"]["star"] = (form.emoji_star.data or "").strip()
            payload["emojis"]["chat"] = (form.emoji_chat.data or "").strip()
            payload["emojis"]["mic"] = (form.emoji_mic.data or "").strip()
            payload["emojis"]["bulb"] = (form.emoji_bulb.data or "").strip()
            payload["emojis"]["money"] = (form.emoji_money.data or "").strip()

            # Mappings (from structured dynamic rows)
            payload["rolebonus"]["msg"] = parse_bonus_fields(raw_form, "rolebonus_msg", int)
            payload["rolebonus"]["voice"] = parse_bonus_fields(raw_form, "rolebonus_voice", int)
            payload["channelbonus"]["msg"] = parse_bonus_fields(raw_form, "channelbonus_msg", int)
            payload["channelbonus"]["voice"] = parse_bonus_fields(raw_form, "channelbonus_voice", int)
            payload["presencebonus"]["msg"] = parse_bonus_fields(raw_form, "presencebonus_msg", str)
            payload["presencebonus"]["voice"] = parse_bonus_fields(raw_form, "presencebonus_voice", str)
            payload["appbonus"]["msg"] = parse_bonus_fields(raw_form, "appbonus_msg", str)
            payload["appbonus"]["voice"] = parse_bonus_fields(raw_form, "appbonus_voice", str)

            # Command requirements/cooldowns (from structured dynamic rows)
            payload["cmd_requirements"] = parse_cmd_requirement_fields(raw_form)
            payload["cmd_cooldowns"] = parse_cmd_cooldown_fields(raw_form)

            validated = GuildSettings.load(payload)
        except (ValidationError, ValueError, TypeError) as e:
            log.warning(f"Settings validation failed for guild {guild.id}: {e}")
            return {
                "status": 0,
                "notifications": [{"message": _("Invalid settings input."), "category": "danger"}],
                "web_content": {
                    "source": _render_settings(
                        form,
                        prestige_html=prestige_html,
                        levelrole_html=levelrole_html,
                        rolebonus_msg_html=rolebonus_msg_html,
                        rolebonus_voice_html=rolebonus_voice_html,
                        channelbonus_msg_html=channelbonus_msg_html,
                        channelbonus_voice_html=channelbonus_voice_html,
                        presencebonus_msg_html=presencebonus_msg_html,
                        presencebonus_voice_html=presencebonus_voice_html,
                        appbonus_msg_html=appbonus_msg_html,
                        appbonus_voice_html=appbonus_voice_html,
                        cmd_requirements_html=cmd_requirements_html,
                        cmd_cooldowns_html=cmd_cooldowns_html,
                    ),
                    "expanded": True,
                },
            }

        cog.db.configs[guild.id] = validated
        cog.save(force=True)
        return {
            "status": 0,
            "notifications": [{"message": _("Settings saved"), "category": "success"}],
            "redirect_url": kwargs["request_url"],
        }

    # ── GET: render form ──
    return {
        "status": 0,
        "web_content": {
            "source": _render_settings(
                form,
                prestige_html=prestige_html,
                levelrole_html=levelrole_html,
                rolebonus_msg_html=rolebonus_msg_html,
                rolebonus_voice_html=rolebonus_voice_html,
                channelbonus_msg_html=channelbonus_msg_html,
                channelbonus_voice_html=channelbonus_voice_html,
                presencebonus_msg_html=presencebonus_msg_html,
                presencebonus_voice_html=presencebonus_voice_html,
                appbonus_msg_html=appbonus_msg_html,
                appbonus_voice_html=appbonus_voice_html,
                cmd_requirements_html=cmd_requirements_html,
                cmd_cooldowns_html=cmd_cooldowns_html,
            ),
            "expanded": True,
        },
    }


def _render_settings(form: t.Any, **extra_context: str) -> str:
    """Pre-render the settings template with the form on the bot side."""
    css_text = (static / "css" / "settings.css").read_text(encoding="utf-8")
    js_text = (static / "js" / "settings.js").read_text(encoding="utf-8")
    template_text = (templates / "settings.html").read_text(encoding="utf-8")
    env = jinja2.Environment(autoescape=True)
    env.globals["_"] = _
    tmpl = env.from_string(template_text)
    rendered = tmpl.render(settings_form=form, **extra_context)
    return f"<style>\n{css_text}\n</style>\n\n{rendered}\n\n<script>\n{js_text}\n</script>"
