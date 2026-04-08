import { CATEGORIES } from '../constants'

const MONTHS = [
  { label: 'All months', value: '' },
  { label: 'January',   value: '01' }, { label: 'February',  value: '02' },
  { label: 'March',     value: '03' }, { label: 'April',     value: '04' },
  { label: 'May',       value: '05' }, { label: 'June',      value: '06' },
  { label: 'July',      value: '07' }, { label: 'August',    value: '08' },
  { label: 'September', value: '09' }, { label: 'October',   value: '10' },
  { label: 'November',  value: '11' }, { label: 'December',  value: '12' },
]

const YEARS = ['', '2024', '2025', '2026']

const sel = 'text-sm border border-gray-300 rounded-md px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500'

export default function FilterBar({ filters, onChange }) {
  const { year, month, category, merchant, cardScope } = filters
  const set = patch => onChange({ ...filters, ...patch })

  return (
    <div className="flex flex-wrap gap-2 mb-4">
      <select className={sel} value={year} onChange={e => set({ year: e.target.value })}>
        <option value="">All years</option>
        {YEARS.filter(Boolean).map(y => <option key={y} value={y}>{y}</option>)}
      </select>

      <select className={sel} value={month} onChange={e => set({ month: e.target.value })}>
        {MONTHS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
      </select>

      <select className={sel} value={category} onChange={e => set({ category: e.target.value })}>
        <option value="">All categories</option>
        {CATEGORIES.map(c => (
          <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
        ))}
      </select>

      <input
        type="text"
        placeholder="Search merchant…"
        className={`${sel} w-48`}
        value={merchant}
        onChange={e => set({ merchant: e.target.value })}
      />

      <select className={sel} value={cardScope} onChange={e => set({ cardScope: e.target.value })}>
        <option value="">All cards</option>
        <option value="primary">Primary</option>
        <option value="supplementary">Supplementary</option>
      </select>
    </div>
  )
}
