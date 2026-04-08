import { PERIOD_OPTIONS } from '../constants'

export default function PeriodSelector({ value, onChange }) {
  return (
    <select
      className="text-sm border border-gray-300 rounded-md px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
      value={String(value.value ?? '')}
      onChange={e => {
        const found = PERIOD_OPTIONS.find(o => String(o.value ?? '') === e.target.value)
        if (found) onChange(found)
      }}
    >
      {PERIOD_OPTIONS.map(opt => (
        <option key={String(opt.value ?? 'all')} value={opt.value ?? ''}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}
