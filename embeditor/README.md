# EmbEditor

Easily edit any message sent by the bot. Adds two message context menu commands (right click a message > Apps) for admins and bot owners.

## Quick Edit

A single modal pre-filled with the parts the message already has: content, embed title, description, author, footer, thumbnail, image. Change what you want and submit. Best for fast text tweaks.

Limited to 5 inputs (Discord modal cap), so parts are included in priority order based on what exists on the message.

## Full Edit

Posts an interactive editor below the target message that starts as an exact clone of it. Nothing touches the original message until you hit **Save**.

### Embed mode

- **Content**: edit the plain message content
- **Body**: title, description, title URL, embed color
- **Author** / **Footer** / **Images**: the respective embed parts
- **Add / Edit / Remove Field**: manage embed fields with a picker
- **Add / Remove Embed**: toggle the embed on or off
- **To Container**: convert the preview to a components v2 text container

### Container mode (components v2)

- **Add Text**: markdown text blocks
- **Add Media**: media gallery from image URLs (one per line, up to 10)
- **Add Separator**: divider line with small or large spacing (or invisible spacing)
- **Add Buttons**: a row of inline URL buttons (`Label | URL` per line, up to 5)
- **Edit / Remove Item**: pick any item in the container to change or delete
- **Accent Color**: set the container's accent color
- **To Embed**: convert back to a regular content + embed message (only available while previewing; a message already saved with v2 components can never go back, Discord does not allow removing the flag)

## Permissions

- Only the bot's own messages can be edited.
- The invoker must be a bot admin or owner.
- Full Edit requires the bot to have `send messages` and `embed links` in the channel (for the preview message).

## Notes

- Saving in container mode converts the target message to components v2, which is **irreversible** for that message.
- The editor times out after 15 minutes and cleans itself up.
