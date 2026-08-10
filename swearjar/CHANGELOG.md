# SwearJar Changelog

## 0.4.0

- The leaderboard now pages with buttons instead of reactions. It was using redbot's reaction-driven `menus.menu`, which needs the reactions intent, needs Manage Messages to clear reactions, and is awkward on mobile. It now uses the repo's standard button-based `DynamicMenu` view, which also brings first/last page jumps and a search box.

## 0.3.0

- `[p]swearjarset words` now lists the words in the channel instead of DMing them. It is an admin-only command showing words the admin configured themselves, so the DM bought nothing and broke the command outright for anyone with DMs closed. Long lists come back as a text file.

## 0.2.0

- Fixed: a word followed by an exclamation mark was never matched. `!` was folded to `i` everywhere, so `damn!` normalized to `damni` and the whole-word boundary could not close on it. `!` now only stands in for `i` when another letter or digit follows it in the same token, so `sh!t` is still caught while `damn!`, `fuck!` and `hell!` match again.
- Words can now be digits only, so `[p]swearjarset addword 67` works. Boundary rules still apply: it catches `that is so 67` but not `1967` or `670`. Entries with neither letters nor digits (`!!!`, `$$$`) are still rejected.
- `addword` takes `boundary` before `fine`, so a word can be set to substring matching without also naming a price: `[p]swearjarset addword damn false`. To give a word its own fine, pass both: `[p]swearjarset addword damn true 25`.

## 0.1.0

Initial release.

- Fines members Red bank credits when their messages contain admin-defined swear words. The word list starts empty and the cog stays inert until an admin enables it and adds at least one word.
- Per-word fines with a server-wide default for words that do not carry their own. A member who cannot cover the fine pays what they have; balances never go negative and no debt is tracked.
- The amount actually taken is recorded in a per-server jar total and in the member's lifetime paid counter, so the two can never disagree with what left the bank.
- Fuzzy matching that survives casing, leetspeak (`d4mn`, `@$$`, `sh!7`) and punctuation between letters (`a.s.s`), with a per-word toggle between whole-word and substring matching.
- Matching avoids the obvious false positives: a bare number like `455` is never read as a word, single-word entries do not match across a space, and apostrophes are literals rather than separators so a configured `hell` leaves `he'll` alone. Straight and curly apostrophes are interchangeable.
- Multi-word entries work spaced or joined, so `son of a bitch` also catches `sonofabitch`.
- Exemptions: ignored channel list (which also covers threads under an ignored channel), ignored role list, and bots and DMs are always skipped. Honors Red's per-server cog disable.
- Admin config under `[p]swearjarset` (alias `sjset`): toggle, addword, delword, words, fine, respond, ignorechannel, ignorerole, view, reset. The word list is sent by DM so profanity is never printed in-channel.
- `[p]swearjar` shows the server's jar total, `[p]swearjar leaderboard` (alias `lb`) shows a paginated ranking of top payers.
- In-channel response when someone is fined is off by default.
