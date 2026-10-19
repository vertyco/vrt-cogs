// Drawing and sound events. The rules only ever add to run.events, and never when it is null: the bot's check runs
// with it null, so events cost the check nothing.

export function emit(run, kind, data) {
  if (run.events !== null) {
    run.events.push({ kind, ...data });
  }
}
