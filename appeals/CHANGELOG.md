# Changelog

## 0.5.0

- `[p]appeal deny` can now set how long this user must wait before appealing again, by starting the reason with a duration: `[p]appeal deny 12 6mo Ban evasion`. It replaces the server's re-appeal cooldown for that denial, whether longer or shorter; `0` lets them appeal again right away. Durations are written without spaces and accept years and months (`2y`, `6mo`, `2w`, `30d`, `12h`, `30m`; `m` is minutes, `mo` is months). Denials without a duration keep using the server default.
- The denial DM now tells the user when they can submit another appeal, shown as a full date and a relative time. It is left out when they have no appeals left or there is no wait.
- The re-appeal check now also runs on servers with no default re-appeal cooldown, so per-denial waits are enforced there too.

## 0.4.1

- Fixed `[p]appeal appealmessage` always replying "Invalid message ID provided": it fetched the message using the channel ID instead of the message ID.

## 0.4.0

- When the ArkTools cog is loaded, the appeal button now refuses users whose linked Ark player is currently temp banned, showing when the ban expires. Permanent bans are still appealable, and bots without ArkTools are unaffected.
- Fixed the approve command's ArkTools unban: it looked up the player with the appeal server's ID instead of the target server's, and called the unban with arguments that no longer exist, so the Ark unban never fired.

## 0.3.0

- Added a ban appeal cooldown: admins can require users to wait a set time after being banned before they can open an appeal (`[p]appeal bancooldown <duration>`). Ban time is read from the target server's audit log; if it can't be determined, the cooldown does not block.
- Added a re-appeal cooldown: when the appeal limit is greater than 1, admins can require users to wait a set time after a denial before appealing again (`[p]appeal reappealcooldown <duration>`).
- Appeal submissions now record when they were approved or denied (`decided_at`), used to enforce the re-appeal cooldown.
- Both cooldowns default to disabled, accept human durations (`7d`, `12h`, `1w`), take `0`/`off`/`disable` to turn off, are bypassed by admins, and show in `[p]appeal view`.
