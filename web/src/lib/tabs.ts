export const TABS = [
  "Overview",
  "Evidence",
  "Options",
  "Positioning",
  "Fundamentals",
  "Brief",
  "Model & Book",
  "Research",
];

/** Tabs that read option chains, which only some markets have. They are hidden rather than shown
 * empty: an empty tab reads as a bug, a missing one as a deliberate limit. Positioning is not one
 * of them — it shows on every market, with what that market publishes. */
const OPTIONS_TABS = ["Options"];

export function visibleTabs(hasOptions: boolean | undefined): string[] {
  return hasOptions === false ? TABS.filter((t) => !OPTIONS_TABS.includes(t)) : TABS;
}
