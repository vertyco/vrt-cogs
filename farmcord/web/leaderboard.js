// The leaderboard: the top farms everywhere, by level and then XP, and where the player's own farm stands. It fills a
// box on the farmhouse board.

// Asks the bot each time it is shown. It only reads, so a second ask while one is on its way goes too, and only the
// list still on screen is filled
export async function showLeaderboard(ctx, box) {
  const { make } = ctx.hud;
  const list = make("ol", "leaders");
  const you = make("p", "you", "Loading...");
  you.id = "leaders-you";
  box.replaceChildren(make("p", "dim", "Every FarmCord farm, by level and then XP."), list, you);
  const reply = await ctx.act("leaderboard", {}, { key: null, sound: null });
  if (!list.isConnected) {
    return;
  }
  if (!reply) {
    you.textContent = "";
    return;
  }
  const me = ctx.state().player.id;
  list.replaceChildren(...reply.top.map((row, i) => leaderRow(ctx, row, i + 1, row.id === me)));
  you.textContent = reply.rank === null ? "" : `Your farm is #${ctx.hud.number(reply.rank)}`;
}

function leaderRow(ctx, row, place, mine) {
  const { make, number } = ctx.hud;
  const item = make("li", mine ? "mine" : "");
  const numbers = `Level ${number(row.level)} · ${number(row.xp)} XP`;
  item.append(make("span", "place", `#${place}`), make("span", "name", row.name), make("span", "numbers", numbers));
  return item;
}
