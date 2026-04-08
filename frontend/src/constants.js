export const CATEGORIES = [
  'groceries', 'food_delivery', 'dining', 'coffee', 'transport',
  'taxi', 'parking_tolls', 'utilities', 'fuel', 'healthcare',
  'shopping', 'car', 'subscriptions', 'travel',
  'entertainment', 'hairdresser', 'housekeeping',
  'government', 'services', 'finance_fees',
  'savings',
  'uncategorized',
]

export const CATEGORY_COLORS = {
  groceries:       '#22c55e',  // green-500
  food_delivery:   '#f97316',  // orange-500
  dining:          '#ef4444',  // red-500
  coffee:          '#92400e',  // amber-800
  transport:       '#3b82f6',  // blue-500
  taxi:            '#6366f1',  // indigo-500
  parking_tolls:   '#8b5cf6',  // violet-500
  utilities:       '#06b6d4',  // cyan-500
  fuel:            '#eab308',  // yellow-500
  healthcare:      '#10b981',  // emerald-500
  shopping:        '#f43f5e',  // rose-500
  car:             '#64748b',  // slate-500
  subscriptions:   '#a855f7',  // purple-500
  travel:          '#14b8a6',  // teal-500
  entertainment:   '#ec4899',  // pink-500
  hairdresser:     '#f59e0b',  // amber-500
  housekeeping:    '#84cc16',  // lime-500
  government:      '#6b7280',  // gray-500
  services:        '#78716c',  // stone-500
  finance_fees:    '#dc2626',  // red-600
  savings:         '#0f766e',  // teal-700
  uncategorized:   '#d1d5db',  // gray-300
  other:           '#9ca3af',  // gray-400
}

// Distinct colors for merchant lines in the spend-over-time chart
export const MERCHANT_LINE_COLORS = [
  '#2563eb', '#7c3aed', '#db2777', '#059669',
  '#d97706', '#dc2626', '#0891b2', '#65a30d',
]

export const PERIOD_OPTIONS = [
  { label: 'Last 3 months',  value: 3  },
  { label: 'Last 6 months',  value: 6  },
  { label: 'Last 12 months', value: 12 },
  { label: 'All time',       value: null },
]
