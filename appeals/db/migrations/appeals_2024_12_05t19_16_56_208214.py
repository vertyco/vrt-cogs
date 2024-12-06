from piccolo.apps.migrations.auto.migration_manager import MigrationManager
from piccolo.columns.base import OnDelete, OnUpdate
from piccolo.columns.column_types import (
    JSON,
    Array,
    BigInt,
    Boolean,
    ForeignKey,
    Integer,
    Text,
    Timestamptz,
)
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.columns.indexes import IndexMethod
from piccolo.table import Table


class AppealGuild(Table, tablename="appeal_guild", schema=None):
    id = BigInt(
        default=0,
        null=False,
        primary_key=True,
        unique=False,
        index=True,
        index_method=IndexMethod.btree,
        choices=None,
        db_column_name=None,
        secret=False,
    )


ID = "2024-12-05T19:16:56:208214"
VERSION = "1.13.0"
DESCRIPTION = "Initial Migrations"


async def forwards():
    manager = MigrationManager(migration_id=ID, app_name="appeals", description=DESCRIPTION)

    manager.add_table(
        class_name="AppealQuestion",
        tablename="appeal_question",
        schema=None,
        columns=None,
    )

    manager.add_table(
        class_name="AppealSubmission",
        tablename="appeal_submission",
        schema=None,
        columns=None,
    )

    manager.add_table(
        class_name="AppealGuild",
        tablename="appeal_guild",
        schema=None,
        columns=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="created_at",
        db_column_name="created_at",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="updated_on",
        db_column_name="updated_on",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="guild",
        db_column_name="guild",
        column_class_name="ForeignKey",
        column_class=ForeignKey,
        params={
            "references": AppealGuild,
            "on_delete": OnDelete.cascade,
            "on_update": OnUpdate.cascade,
            "target_column": None,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="question",
        db_column_name="question",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": "",
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="sort_order",
        db_column_name="sort_order",
        column_class_name="Integer",
        column_class=Integer,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="required",
        db_column_name="required",
        column_class_name="Boolean",
        column_class=Boolean,
        params={
            "default": True,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="default",
        db_column_name="default",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": None,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="placeholder",
        db_column_name="placeholder",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": None,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="max_length",
        db_column_name="max_length",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": None,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="min_length",
        db_column_name="min_length",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": None,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="style",
        db_column_name="style",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": "long",
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealQuestion",
        tablename="appeal_question",
        column_name="button_style",
        db_column_name="button_style",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": "primary",
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealSubmission",
        tablename="appeal_submission",
        column_name="created_at",
        db_column_name="created_at",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealSubmission",
        tablename="appeal_submission",
        column_name="guild",
        db_column_name="guild",
        column_class_name="ForeignKey",
        column_class=ForeignKey,
        params={
            "references": AppealGuild,
            "on_delete": OnDelete.cascade,
            "on_update": OnUpdate.cascade,
            "target_column": None,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealSubmission",
        tablename="appeal_submission",
        column_name="user_id",
        db_column_name="user_id",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealSubmission",
        tablename="appeal_submission",
        column_name="answers",
        db_column_name="answers",
        column_class_name="JSON",
        column_class=JSON,
        params={
            "default": "{}",
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealSubmission",
        tablename="appeal_submission",
        column_name="status",
        db_column_name="status",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": "pending",
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealSubmission",
        tablename="appeal_submission",
        column_name="message_id",
        db_column_name="message_id",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="id",
        db_column_name="id",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": True,
            "unique": False,
            "index": True,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="created_at",
        db_column_name="created_at",
        column_class_name="Timestamptz",
        column_class=Timestamptz,
        params={
            "default": TimestamptzNow(),
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="target_guild_id",
        db_column_name="target_guild_id",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="appeal_channel",
        db_column_name="appeal_channel",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="appeal_message",
        db_column_name="appeal_message",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="pending_channel",
        db_column_name="pending_channel",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="approved_channel",
        db_column_name="approved_channel",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="denied_channel",
        db_column_name="denied_channel",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="alert_roles",
        db_column_name="alert_roles",
        column_class_name="Array",
        column_class=Array,
        params={
            "base_column": BigInt(
                default=0,
                null=False,
                primary_key=False,
                unique=False,
                index=False,
                index_method=IndexMethod.btree,
                choices=None,
                db_column_name=None,
                secret=False,
            ),
            "default": list,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="alert_channel",
        db_column_name="alert_channel",
        column_class_name="BigInt",
        column_class=BigInt,
        params={
            "default": 0,
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="button_style",
        db_column_name="button_style",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": "primary",
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="button_label",
        db_column_name="button_label",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": "Submit Appeal",
            "null": False,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    manager.add_column(
        table_class_name="AppealGuild",
        tablename="appeal_guild",
        column_name="button_emoji",
        db_column_name="button_emoji",
        column_class_name="Text",
        column_class=Text,
        params={
            "default": None,
            "null": True,
            "primary_key": False,
            "unique": False,
            "index": False,
            "index_method": IndexMethod.btree,
            "choices": None,
            "db_column_name": None,
            "secret": False,
        },
        schema=None,
    )

    return manager
