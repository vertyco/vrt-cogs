# GlassRelay Changelog

## 0.0.1

- The cog keeps its settings, products and credited payments in its own SQLite file.
- Server owner commands under `[p]glassrelay`: `key`, `ratio`, `message`, `logchannel`, `addproduct`, `delproduct`, `init`, `purchases` and `view`. `key` opens a form for the API key, so the key never shows in the channel. `addproduct`, `delproduct` and `init` open a menu to pick the product from.
- `[p]claim` gives buyers the credits for their GlassRelay purchases.
- `init` marks a product's past payments so `[p]claim` never pays them, and still files each completed one under its buyer at `amount paid * ratio`, so purchase history and totals cover purchases made before the cog was set up. Removing a product and adding it back, then running `init`, rebuilds everyone's history.
- The cog only works with a per-server bank. With a global bank, every command says so and points to `[p]bankset toggleglobal`.
