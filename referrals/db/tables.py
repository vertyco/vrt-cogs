
from piccolo.columns import (
    Array,
    BigInt,
    Boolean,
    ForeignKey,
    Integer,
    Serial,
    Timestamptz,
)
from piccolo.table import Table, sort_table_classes
from redbot.core.i18n import Translator

_ = Translator("Referrals", __file__)


class GuildSettings(Table):
    id = BigInt(primary_key=True, index=True, help_text="Guild ID")
    created_at = Timestamptz()
    enabled = Boolean(default=False)
    referral_reward = Integer(help_text="Reward sent to the person who referred someone")
    referred_reward = Integer(help_text="Reward sent to the person who was referred")
    referral_channel = Integer(help_text="Channel where referral messages are sent")
    min_account_age_minutes = Integer(help_text="Minimum account age to be eligible for rewards")
    claim_timeout_minutes = Integer(help_text="User must claim their reward within this time frame after joining")
    initialized_users = Array(BigInt(), default=[])


class Referral(Table):
    id: Serial
    guild = ForeignKey(references=GuildSettings, index=True)
    created_at = Timestamptz()

    # The person who was referred, there should only be one of these per server
    referred_id = BigInt(help_text="ID of the person who was referred")

    # There can be multiple entries with the same referrer_id
    referrer_id = BigInt(help_text="ID of the person who referred someone")


TABLES: list[Table] = sort_table_classes([GuildSettings, Referral])
