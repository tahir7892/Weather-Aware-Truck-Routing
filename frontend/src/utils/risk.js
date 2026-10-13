/*
 * Risk levels as the backend returns them, with one color each.
 * Every place that shows risk (map, cards, table, legend, heatmap) uses these,
 * and always next to the text label so meaning never depends on color alone.
 */

export const RISK_LEVELS = [
  { score: 0, label: 'Low', color: '#1f9d55' },
  { score: 1, label: 'Moderate', color: '#cf9800' },
  { score: 2, label: 'High', color: '#e2661a' },
  { score: 3, label: 'Severe', color: '#b3202b' },
  { score: 4, label: 'No Travel', color: '#5e1240' },
]

export const NO_DATA = { score: null, label: 'No data', color: '#a8a7a0' }

// Order of the backend's `miles_by_level` keys, safest first.
export const MILES_BY_LEVEL_ORDER = [...RISK_LEVELS.map((level) => level.label), NO_DATA.label]

export function riskByScore(score) {
  return RISK_LEVELS[score] ?? NO_DATA
}

export function riskByLabel(label) {
  return RISK_LEVELS.find((level) => level.label === label) ?? NO_DATA
}

/** MapLibre expression: feature property (0-4, or -1 for no data) -> color. */
export function riskColorExpression(property = 'risk') {
  return [
    'match',
    ['get', property],
    ...RISK_LEVELS.flatMap((level) => [level.score, level.color]),
    NO_DATA.color,
  ]
}
