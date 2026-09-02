// Killswitch for fighter creation. Generating a fighter costs real GPU and
// image-model spend, so creation can be turned off without a redeploy by
// setting CREATION_ENABLED=0 on the API service. Jobs the worker already holds
// run to completion; only new submissions are refused. Creation is on unless
// explicitly disabled, so a missing or garbled value never closes the lab by
// accident.
const OFF_VALUES = new Set(["0", "false", "off", "no", "disabled"]);

export const CREATION_DISABLED_MESSAGE =
  "Fighter creation is paused. Every fighter already on the roster is still free to play.";

export function creationEnabled(env = process.env) {
  const configured = String(env.CREATION_ENABLED ?? "").trim().toLowerCase();
  return !OFF_VALUES.has(configured);
}
