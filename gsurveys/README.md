# GSurveys

Link Google Forms to your Discord server's virtual economy. When a user completes a survey, they automatically receive credits and a DM confirmation.

## How It Works

1. **Admin creates a survey** — the bot creates a Discord webhook in a designated private channel
2. **Admin adds a Google Apps Script** to their Google Form (the bot provides the script)
3. The Google Form must include a question asking for the user's **Discord User ID**
4. When someone submits the form, the Apps Script sends the response to the Discord webhook
5. The bot detects the webhook message, validates the ID, deposits credits, and DMs the user a thank-you
6. The webhook message is automatically deleted for security

No external server or open ports required — everything runs through Discord's own webhook system.
Fully multi-guild — each server manages its own surveys independently.

## Setup

### Per Survey

1. **Create a survey** (use a private channel only the bot and admins can see):
   ```
   [p]gsurveys add #survey-log 500 Customer Feedback Survey
   ```
2. **Add the Discord ID question** to your Google Form — the question title must be exactly **"Discord User ID"** (or whatever you configure with `[p]gsurveys field`)
3. **Get the Apps Script:**
   ```
   [p]gsurveys script <survey_id>
   ```
4. Follow the DM'ed instructions to add the script to your Google Form

### Helping Users Find Their ID

Users need to enter their Discord User ID (a long number) into the form. To help them:
- Tell them to run `[p]myid` in your server — it gives them a copyable ID
- The script instructions include a suggestion for adding **Google Forms response validation** that rejects non-numeric entries, so typos and usernames are blocked before they even submit
- The Apps Script itself also validates the format and silently ignores bad entries

### Anti-Abuse

- **One completion per user** — duplicate submissions for the same Discord ID are ignored
- **Webhook messages are auto-deleted** — users can't see or copy the webhook channel content
- **Use a private channel** for the webhook that only the bot and admins can access
- The Apps Script validates that the entry is a valid Discord ID format (17-20 digits)

## Commands

### User Commands
| Command | Description |
|---------|-------------|
| `[p]myid` | Get your Discord User ID for survey forms |

### Admin Commands
| Command | Description |
|---------|-------------|
| `[p]gsurveys add <channel> <reward> <name>` | Create a new survey with a webhook |
| `[p]gsurveys remove <id>` | Delete a survey and its webhook |
| `[p]gsurveys list` | List all surveys |
| `[p]gsurveys toggle <id>` | Enable/disable a survey |
| `[p]gsurveys reward <id> <amount>` | Change reward amount |
| `[p]gsurveys field <id> <name>` | Change the Discord ID question title |
| `[p]gsurveys completions <id>` | View who completed a survey |
| `[p]gsurveys reset <id>` | Wipe all completions for a survey |
| `[p]gsurveys resetuser <id> <user>` | Reset a specific user's completion |
| `[p]gsurveys script <id>` | Get the Google Apps Script (DM) |
