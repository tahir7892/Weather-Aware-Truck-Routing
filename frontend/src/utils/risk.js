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

// Same thresholds as backend/planner/constants.py, used to color the heatmap's
// wind / rain / snow views. Borders go to the higher level; No Travel rain and
// snow are strictly "greater than", exactly as in the backend.
const CONDITION_THRESHOLDS = {
  wind: { steps: [25, 35, 45, 55], strictTop: false },
  rain: { steps: [0.1, 0.25, 0.5, 1.0], strictTop: true },
  snow: { steps: [0.5, 1.0, 2.0, 3.0], strictTop: true },
}

/** Level (0-4) of one condition's value, or -1 when the value is missing. */
export function conditionLevel(condition, value) {
  if (value === null || value === undefined) return -1
  const { steps, strictTop } = CONDITION_THRESHOLDS[condition]
  if (strictTop ? value > steps[3] : value >= steps[3]) return 4
  for (let i = 2; i >= 0; i -= 1) if (value >= steps[i]) return i + 1
  return 0
}

/** What the heatmap can show. `property` is the cell property holding a 0-4 level. */
export const HEATMAP_VIEWS = [
  {
    id: 'risk',
    label: 'Risk',
    property: 'risk',
    title: 'Overall risk for your load',
    ranges: ['Low', 'Moderate', 'High', 'Severe', 'No Travel'],
  },
  {
    id: 'wind',
    label: 'Wind',
    property: 'windLevel',
    title: 'Sustained wind, mph (before load rules)',
    ranges: ['< 25', '25–34', '35–44', '45–54', '≥ 55'],
  },
  {
    id: 'rain',
    label: 'Rain',
    property: 'rainLevel',
    title: 'Rain, in/hr',
    ranges: ['< 0.10', '0.10–0.24', '0.25–0.49', '0.50–1.00', '> 1.00'],
  },
  {
    id: 'snow',
    label: 'Snow',
    property: 'snowLevel',
    title: 'Snow, in/hr',
    ranges: ['< 0.5', '0.5–0.9', '1.0–1.9', '2.0–3.0', '> 3.0'],
  },
]

function withAlpha(hex, alpha) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

/**
 * Heatmap cell color for a 0-4 level property. Low is a faint tint and
 * "no data" is fully transparent, so the layer's opacity can stay constant
 * (which lets MapLibre fade smoothly between hours).
 */
export function heatColorExpression(property) {
  return [
    'match',
    ['get', property],
    -1,
    'rgba(0, 0, 0, 0)',
    0,
    withAlpha(RISK_LEVELS[0].color, 0.18),
    ...RISK_LEVELS.slice(1).flatMap((level) => [level.score, level.color]),
    'rgba(0, 0, 0, 0)',
  ]
}
