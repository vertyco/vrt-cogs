# Cartographer Help

Backup & Restore tools for Discord servers.<br/><br/>This cog will create a backup of all roles, channels and permission.<br/><br/>When restoring it will do its best to restore the backup as closely as possible, some roles may not be restored due to position hirearchy.

## Features

- **Full Server Backups**: Save roles, channels, emojis, stickers, bans, and server settings
- **Granular Restore Options**: Choose exactly what to restore from a backup
- **Cross-Server Restore**: Bot owners can restore backups from one server to another
- **Auto Backups**: Optionally enable automatic periodic backups
- **Member Role Restoration**: Optionally restore saved role assignments to members
- **Only Restore Missing**: Safely recover deleted items without modifying existing ones
- **Delete Unmatched**: Optionally remove items not present in the backup

## Restore Options

When restoring a backup, you can select from the following options:

| Option | Description |
|--------|-------------|
| Server Settings | Name, icon, banner, verification level, etc. |
| Roles | Role definitions and permissions |
| Emojis | Custom emojis |
| Stickers | Custom stickers |
| Categories | Category channels |
| Text Channels | Text channels |
| Voice Channels | Voice channels |
| Forum Channels | Forum channels |
| Bans | User bans |
| Restore Member Roles | Assign saved roles to members |
| Delete Unmatched | ⚠️ Remove items not in backup |
| Only Restore Missing | 🆕 Skip existing items, only recreate deleted ones |

# cartographer
 - Usage: `[p]cartographer `
 - Checks: `server_only`

Open the Backup/Restore menu

# cartographerset
 - Usage: `[p]cartographerset `
 - Checks: `server_only`

Backup & Restore Tools

## cartographerset autobackups
 - Usage: `[p]cartographerset autobackups `
 - Restricted to: `BOT_OWNER`

Enable/Disable allowing auto backups

## cartographerset restorelatest
 - Usage: `[p]cartographerset restorelatest [delete_existing=False] `

Restore the latest backup for this server<br/><br/>**Arguments**<br/>- delete_existing: if True, deletes existing channels/roles that aren't part of the backup.

## cartographerset ignore
 - Usage: `[p]cartographerset ignore <server> `
 - Restricted to: `BOT_OWNER`

Add/Remove a server from the ignore list

## cartographerset maxbackups
 - Usage: `[p]cartographerset maxbackups <max_backups> `
 - Restricted to: `BOT_OWNER`

Set the max amount of backups a server can have

## cartographerset view
 - Usage: `[p]cartographerset view `
 - Restricted to: `BOT_OWNER`

View current global settings

## cartographerset allow
 - Usage: `[p]cartographerset allow <server> `
 - Restricted to: `BOT_OWNER`

Add/Remove a server from the allow list

## cartographerset backup
 - Usage: `[p]cartographerset backup `

Create a backup of this server

