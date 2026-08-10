# SwearJar

Fine members Red economy credits when their messages contain admin-defined swear words. Fines accumulate into a per-server jar total, with a per-member lifetime paid tracker and a leaderboard.

There is no built-in word list: the jar is empty and disabled until an admin turns it on and adds words.

## How matching works

Matching is fuzzy and normalization-based, not a literal substring search:

- Case-insensitive, and common leetspeak/confusable characters are folded to letters (`$` -> `s`, `@` -> `a`, `!` -> `i`, plus digits `0`, `1`, `3`, `4`, `5`, `7`, `9`). Digit substitution only applies inside a token that already contains a letter, so a bare number like `455` is never read as a word. `!` only stands in for `i` when another letter or digit follows it in the same token, so `sh!t` is caught while ordinary emphasis like `damn!` still matches the plain word.
- Words can be digits only. `[p]swearjarset addword 67` matches the literal number, and boundary rules still apply, so it catches `that is so 67` but not `1967` or `670`.
- Punctuation between the letters of a single word is tolerated, so a configured word like `ass` also catches `a.s.s` and `@$$`. This tolerance never crosses whitespace, so `a s s` (spaced out across a message) is not caught.
- An apostrophe is never treated as a separator, so a word like `hell` does not false-positive on contractions such as `he'll`, `she'll`, or `we'll`. Straight `'` and curly `’` apostrophes are interchangeable everywhere, in both the message and the configured word, so `y'all` and `y’all` match each other regardless of which form either side used (handy since iOS/macOS auto-curl typed apostrophes). If you deliberately configure a word that contains an interior apostrophe (e.g. `y'all`), it's kept as a literal required character in the match. A leading or trailing apostrophe (e.g. `fuckin'`) is stripped instead, so the word still matches normally.
- Multi-word entries (e.g. `son of a bitch`) tolerate any separator, including none, between the words, so they also catch the squashed form (`sonofabitch`).
- Each word counts at most once per message, no matter how many times it appears.
- Per word, choose **boundary** matching (default: whole words only) or **substring** matching (matches anywhere, even inside other words).

## Setup

1. `[p]swearjarset toggle` to enable the jar for the server.
2. `[p]swearjarset addword <word> [boundary] [fine]` for each word you want to fine. Leave both empty to get whole-word matching at the server default fine, pass `false` to match the word as a substring instead, and add a number to give that word its own price.
3. Optional: `[p]swearjarset fine <amount>` to change the server-wide default fine used by words that don't have their own.
4. Optional: `[p]swearjarset ignorechannel #channel` / `[p]swearjarset ignorerole @role` to exempt channels or roles.
5. Optional: `[p]swearjarset respond` to have the bot post a short in-channel message whenever someone gets fined (default off).

If a member's balance is lower than the fine, they are drained to zero rather than going into debt, and only the amount actually taken is added to the jar total and their lifetime paid counter.

## Commands

### User commands (public) `[p]swearjar`

| Command | Description |
|---|---|
| `[p]swearjar` | Show the server's swear jar total |
| `[p]swearjar leaderboard` (alias `lb`) | Top swear jar payers in this server, paged with buttons |

### Admin group `[p]swearjarset` (alias `sjset`)

Requires admin or the Manage Server permission, guild only:

| Subcommand | Description |
|---|---|
| `toggle` | Enable or disable the swear jar |
| `addword <word> [boundary] [fine]` | Add or update a swear word. `boundary` comes first so you can set it without naming a fine (`addword damn false`). Wrap multi-word entries in quotes, e.g. `[p]swearjarset addword "son of a bitch" true 25` |
| `delword <word>` | Remove a swear word |
| `words` | List the configured words with the fine and match type for each. Sent as a file if the list is too long for one message |
| `fine <amount>` | Set the default fine for words without their own fine |
| `respond` | Toggle the in-channel message posted when someone is fined |
| `ignorechannel <channel>` | Add or remove a channel from the ignore list |
| `ignorerole <role>` | Add or remove a role from the ignore list |
| `view` | View current settings: enabled state, word count, default fine, respond toggle, jar total, and ignored channels/roles |
| `reset [confirm]` | Reset the jar total and every member's paid stats. Requires `[p]swearjarset reset true` to confirm |

## Notes

- Bot accounts and DMs are always ignored.
- This cog respects Red's per-server cog disable list; disabling the cog in a server stops fining immediately.
- `[p]swearjarset view` reports how many words are configured rather than listing them; use `[p]swearjarset words` for the full list.
