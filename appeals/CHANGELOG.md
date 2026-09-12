# Changelog

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
