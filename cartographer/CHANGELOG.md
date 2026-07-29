# Cartographer Changelog

## v2.3.0

- **Fix**: Backing up a server with many message attachments could exhaust the host's memory and get the bot OOM-killed. Every attachment was downloaded, base64-encoded, and held on the model until the whole guild had been serialized — roughly 4x the attachment size resident at once, before the JSON document was built on top. The v2.2.0 per-file check (`attachment.size < guild.filesize_limit`) only rejects individual oversized files and puts no ceiling on the total, so a media-heavy server produced a multi-GB backup and a peak RSS several times larger. Restoring such a backup had the same problem in reverse, since the whole file was read into a string and parsed.
- **Change**: Backups are now written as `.zip` archives (`backup.json` plus an `attachments/` folder) instead of a single `.json` file. Attachments stream into the archive as they download and are read back out one at a time, so memory stays flat regardless of how much media a server has. Nothing is skipped — a large backup simply takes longer. Backups are also considerably smaller, since base64 inflated every file by a third and the JSON is now compressed.
- **Note**: Existing `.json` backups are still readable and restorable; `load_backup` picks the format by extension. New backups are always `.zip`.

## v2.2.0

- **New**: Message attachments are now backed up and restored. Files are stored base64 inside the backup (`FileBackup`), capped at the guild's upload size limit so oversized files can't balloon the backup or fail re-upload.
- **New**: Granular restores respect the Categories toggle. Channel restore methods take `restore_category`; with categories deselected, existing channels keep their current category instead of being restored into one.
- **New**: `[p]cartoset restorelatest` requires a `True` confirmation argument and warns that unmatched roles/channels/emojis/stickers get deleted.
- **Fix**: Restoring a deleted voice channel crashed with `TypeError: create_voice_channel() got an unexpected keyword argument 'slowmode_delay'`, aborting the restore mid-run. Slowmode is now applied via edit after creation, and `nsfw`/`slowmode_delay` restore consistently on both the create and edit paths.
- **Fix**: Deselecting Categories no longer strips existing channels out of their categories. The edit path passed `category=None`, which actively moved every updated channel to the top level.
- **Fix**: Role restore fuzzy matching adopts an existing role's ID and then applies the backup's permissions/position, instead of returning early with the live role's permissions untouched. Managed roles are skipped as match candidates.
- **Fix**: Member role restore filters unremovable roles (booster, integration, above bot) from the removal batch. One bad role previously failed the whole `remove_roles` call, leaving stale roles in place.
- **Fix**: Forum tag emoji restore. Unicode emojis restore on both the update and create paths (previously dropped or crashed), the name fallback compares emoji names instead of the tag name, and tags with a missing custom emoji are kept without the emoji instead of silently dropped. Tag comparison is order-insensitive so reordered tags no longer force a needless forum edit.
- **Fix**: Forums restored twice on servers that already had community enabled. The second pass now only handles forums skipped while community was still off.
- **Fix**: `restorelatest` on a guild with an empty backup folder raised `IndexError` instead of saying there are no backups.
- **Fix**: Deleted-guild config cleanup in the auto-backup loop now persists (`save` flag was never set on that branch).
- **Misc**: Message serialization unified into `MessageBackup.serialize` (webhook name uses display name, content truncated at 2000). Shared webhook message-restore helper for text and voice channels. Emoji and sticker downloads run concurrently during backup. Backup file reads moved off the event loop. Silent exception paths now log the error.
