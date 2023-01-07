from redbot.core.utils.chat_formatting import box
from discord.ext.commands import (
    MemberConverter, EmojiConverter, GuildConverter, CategoryChannelConverter,
    InviteConverter, PartialEmojiConverter, PartialMessageConverter, MessageConverter, UserConverter,
    RoleConverter, TextChannelConverter, ColourConverter, ColorConverter, GuildStickerConverter,
    VoiceChannelConverter, ObjectConverter, FlagConverter, ScheduledEventConverter,
    ForumChannelConverter, StageChannelConverter, ThreadConverter
)
from discord import AppCommandOptionType
from discord import (
    Member, Emoji, Guild, CategoryChannel, Invite, PartialEmoji, PartialMessage, Message, User, Role,
    TextChannel, Color, Colour, Sticker, GuildSticker, Object, ScheduledEvent, ForumChannel, VoiceChannel,
    UserFlags, ChannelFlags, MessageFlags, PublicUserFlags, SystemChannelFlags, ApplicationFlags,
    MemberCacheFlags, StageChannel, Thread, Attachment
)

CONVERTERS = {
    Member: MemberConverter.__doc__,
    Emoji: EmojiConverter.__doc__,
    Guild: GuildConverter.__doc__,
    CategoryChannel: CategoryChannelConverter.__doc__,
    Invite: InviteConverter.__doc__,
    PartialEmoji: PartialEmojiConverter.__doc__,
    PartialMessage: PartialMessageConverter.__doc__,
    Message: MessageConverter.__doc__,
    User: UserConverter.__doc__,
    Role: RoleConverter.__doc__,
    TextChannel: TextChannelConverter.__doc__,
    VoiceChannel: VoiceChannelConverter.__doc__,
    StageChannel: StageChannelConverter.__doc__,
    Thread: ThreadConverter.__doc__,
    Color: ColorConverter.__doc__,
    Colour: ColourConverter.__doc__,
    Sticker: GuildStickerConverter.__doc__,
    GuildSticker: GuildStickerConverter.__doc__,
    Object: ObjectConverter.__doc__,
    ScheduledEvent: ScheduledEventConverter.__doc__,
    ForumChannel: ForumChannelConverter.__doc__,
    UserFlags: FlagConverter.__doc__,
    ChannelFlags: FlagConverter.__doc__,
    PublicUserFlags: FlagConverter.__doc__,
    SystemChannelFlags: FlagConverter.__doc__,
    ApplicationFlags: FlagConverter.__doc__,
    MessageFlags: FlagConverter.__doc__,
    MemberCacheFlags: FlagConverter.__doc__,
    int: box(int.__doc__),
    float: box(float.__doc__),
    bool: box(bool.__doc__),
    str: box(str.__doc__),
    AppCommandOptionType.string: box(str.__doc__),
    AppCommandOptionType.integer: box(int.__doc__),
    AppCommandOptionType.boolean: box(bool.__doc__),
    AppCommandOptionType.user: MemberConverter.__doc__,
    AppCommandOptionType.channel: TextChannelConverter.__doc__,
    AppCommandOptionType.role: RoleConverter.__doc__,
    AppCommandOptionType.attachment: Attachment.__doc__,
}

CLASSCONVERTER = {
    AppCommandOptionType.string: str,
    AppCommandOptionType.integer: int,
    AppCommandOptionType.boolean: bool,
    AppCommandOptionType.user: Member,
    AppCommandOptionType.channel: TextChannel,
    AppCommandOptionType.role: Role,
    AppCommandOptionType.attachment: Attachment,
}
