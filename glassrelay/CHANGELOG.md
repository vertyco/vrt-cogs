# GlassRelay Changelog

## 0.0.3

- When Cloudflare, in front of GlassRelay, blocks the bot's server with a robot check, the cog says the bot is being blocked instead of blaming the key, and logs a warning. Buyers running `[p]claim` are told GlassRelay is blocking the bot.

## 0.0.2

- When `[p]glassrelay key` turns a key away and the menu then times out, the menu keeps saying why the key failed instead of only saying it timed out.

## 0.0.1

- The cog keeps its settings, products and credited payments in its own SQLite file.
- Server owner commands under `[p]glassrelay`: `key`, `ratio`, `message`, `logchannel`, `addproduct`, `delproduct`, `init`, `purchases` and `view`. `key` opens a form for the API key, so the key never shows in the channel. `addproduct`, `delproduct` and `init` open a menu to pick the product from.
- `[p]claim` gives buyers the credits for their GlassRelay purchases.
- `init` marks a product's past payments so `[p]claim` never pays them, and still files each completed one under its buyer at `amount paid * ratio`, so purchase history and totals cover purchases made before the cog was set up. Removing a product and adding it back, then running `init`, rebuilds everyone's history.
- The cog only works with a per-server bank. With a global bank, every command says so and points to `[p]bankset toggleglobal`.
