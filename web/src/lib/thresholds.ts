// Ratios need a sample before they mean anything: a handful of days annualizes into a
// confident-looking number that is pure noise. The marts null them below this at source, so
// the API serves null and every consumer agrees. Kept here so the UI states the same figure
// rather than a second copy that can drift from `min_days_for_ratios` in dbt_project.yml.
export const MIN_DAYS_FOR_RATIOS = 20;

// |t| at which an estimate is treated as telling apart from zero (roughly two sigma).
// A day count alone never establishes that: a window can clear MIN_DAYS_FOR_RATIOS and still
// carry a standard error larger than the estimate itself, which is the difference between a
// return the book earned and one the window cannot rule out.
export const RESOLVES_AT_T = 2;
