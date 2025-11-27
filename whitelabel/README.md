# Whitelabel

Allow server owners to customize the bot's profile (avatar, banner, and bio) on a per-server basis using Discord's guild member profile feature.

## Features

- **Per-Server Profiles**: Server owners can set custom avatars, banners, and bios for the bot in their server
- **Access Control**: Optional role-based whitelist system to control which server owners can customize the bot
- **Automatic Cleanup**: Automatically reverts unauthorized profiles when access is removed
- **Custom Messages**: Configurable denial messages with placeholder support

## User Commands

### `/botprofile avatar [avatar]`
Set or reset the bot's avatar for the current server.
- **avatar** (optional): Image attachment. Leave empty to reset to global avatar.
- **Permissions**: Requires `Manage Server` permission

### `/botprofile banner [banner]`
Set or reset the bot's banner for the current server.
- **banner** (optional): Image attachment. Leave empty to reset to global banner.
- **Permissions**: Requires `Manage Server` permission

### `/botprofile bio [bio]`
Set or reset the bot's bio for the current server.
- **bio** (optional): Text up to 190 characters. Leave empty to reset to global bio.
- **Permissions**: Requires `Manage Server` permission

## Bot Owner Commands

### `[p]whitelabel view`
View the current whitelabel configuration including main server, role, and denial message.

### `[p]whitelabel mainserver`
Set the current server as the main server where access control is managed.
- Must be run in the server you want to designate as the main server

### `[p]whitelabel mainrole [role]`
Set or clear the required role for server owners to customize the bot's profile.
- **role** (optional): Role in the main server. Leave empty to disable role checking.
- Must be run in the main server

### `[p]whitelabel disallowedmsg <message>`
Set a custom message shown to server owners who lack the required role.

**Available placeholders:**
- `{owner_mention}` - Mentions the server owner
- `{owner_name}` - The server owner's name
- `{role_name}` - Name of the required role
- `{main_guild}` - Name of the main server
- `{invite}` - Invite link to the main server (if available)

### `[p]whitelabel cleanup`
Revert all unauthorized server profiles for owners who no longer have access.
- ⚠️ **Warning**: May take time and hit rate limits if the bot is in many servers

## How It Works

1. **Optional Access Control**: If configured, only server owners with a specific role in the "main server" can customize the bot's profile
2. **Per-Server Customization**: Uses Discord's guild member profile API to set server-specific profiles
3. **Automatic Monitoring**: Listens for role removals and member departures to automatically revert unauthorized profiles
4. **Rate Limit Protection**: Built-in delays during bulk operations to prevent rate limiting

## Setup Example

1. Set your main server: `[p]whitelabel mainserver`
2. Set the required role: `[p]whitelabel mainrole @Premium`
3. (Optional) Set a custom denial message with invite link
4. Server owners with the @Premium role can now use `/botprofile` commands

To disable access control, simply run `[p]whitelabel mainrole` without a role argument.


