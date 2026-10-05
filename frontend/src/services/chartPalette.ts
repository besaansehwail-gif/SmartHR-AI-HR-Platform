/**
 * Chart colours.
 *
 * The dashboard endpoints hand back a `color` for each series so the API can
 * be rendered without the client inventing anything - but those values came
 * from the old purple-led template palette. Colour is presentation, not data,
 * so the frontend now picks it: same series, same order, same numbers, just
 * an Amber Sand ramp instead of a purple one.
 *
 * The ramp leads with the brand oranges and then moves through hues that stay
 * distinguishable side by side (and in greyscale, roughly by lightness), so a
 * department breakdown with eight slices is still readable.
 */
export const CHART_PALETTE = [
  '#C45A2A', // brand 600 - dark orange
  '#F7A96B', // brand 400 - primary orange
  '#82381A', // brand 800
  '#E4813C', // brand 500
  '#0F766E', // teal 700
  '#B45309', // amber 700
  '#4B6478', // slate blue
  '#7C6A58', // warm taupe
  '#A16207', // yellow 700
  '#5B7553', // olive
] as const;

/** Colour for the nth series, cycling once the ramp runs out. */
export const chartColor = (index: number): string =>
  CHART_PALETTE[((index % CHART_PALETTE.length) + CHART_PALETTE.length) % CHART_PALETTE.length];

/**
 * Semantic colours for charts that plot a *state* rather than a category -
 * attendance status, leave status, pipeline health. These keep their usual
 * meaning; the brief allows status colours to stay semantic.
 */
export const STATUS_COLORS = {
  positive: '#059669',
  warning: '#D97706',
  negative: '#DC2626',
  neutral: '#A8A29E',
  brand: '#C45A2A',
} as const;
