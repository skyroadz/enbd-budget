import { useState, useMemo } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { useApi } from '../hooks/useApi'

const fmtAED = v => `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
const fmtK   = v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)

const SERIES = [
  { key: 'chequing_in',  label: 'Chequing In',      color: '#3b82f6' },
  { key: 'chequing_out', label: 'Chequing Out',      color: '#ef4444' },
  { key: 'savings_in',   label: 'Savings Transfers', color: '#0f766e' },
  { key: 'savings_bal',  label: 'Savings Balance',   color: '#10b981' },
]

export default function BankLineChart({ apiSuffix }) {
  const qs = apiSuffix || ''
  const { data: totals, loading: l1 } = useApi('/api/bank-monthly-totals' + qs)
  const { data: history, loading: l2 } = useApi('/api/bank-history' + qs)

  const [active, setActive] = useState(SERIES.map(s => s.key))

  const chartData = useMemo(() => {
    if (!totals?.rows || !history?.months) return []

    // Build a map: ym → { chequing_in, chequing_out, savings_in }
    const map = {}
    for (const r of totals.rows) {
      const ym = `${r.year}-${r.month}`
      if (!map[ym]) map[ym] = { ym: `${r.year.slice(2)}-${r.month}` }
      if (r.account === 'chequing') {
        map[ym].chequing_in  = r.total_in  ?? null
        map[ym].chequing_out = r.total_out ?? null
      } else if (r.account === 'savings') {
        map[ym].savings_in = r.total_in ?? null
      }
    }

    // Merge savings_balance from bank-history
    for (const m of history.months) {
      const ym = `${m.year}-${m.month}`
      if (!map[ym]) map[ym] = { ym: `${m.year.slice(2)}-${m.month}` }
      if (m.savings_balance != null) map[ym].savings_bal = m.savings_balance
    }

    return Object.values(map).sort((a, b) => a.ym.localeCompare(b.ym))
  }, [totals, history])

  function toggle(key) {
    setActive(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    )
  }

  if (l1 || l2) return <div className="h-72 bg-gray-100 animate-pulse rounded-lg" />
  if (!chartData.length) return null

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Transaction History Over Time</h3>

      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="ym" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} width={44} />
          <Tooltip
            formatter={(v, name) => [
              v != null ? fmtAED(v) : '—',
              SERIES.find(s => s.key === name)?.label ?? name,
            ]}
          />
          <Legend formatter={name => SERIES.find(s => s.key === name)?.label ?? name} />
          {SERIES.filter(s => active.includes(s.key)).map(s => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.key}
              stroke={s.color}
              strokeWidth={2}
              dot={{ r: 3, fill: s.color }}
              activeDot={{ r: 5 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>

      <div className="mt-4 flex flex-wrap gap-2">
        {SERIES.map(s => {
          const on = active.includes(s.key)
          return (
            <button
              key={s.key}
              onClick={() => toggle(s.key)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                on
                  ? 'text-white border-transparent'
                  : 'bg-white text-gray-500 border-gray-300 hover:border-gray-400'
              }`}
              style={on ? { backgroundColor: s.color, borderColor: s.color } : {}}
            >
              {s.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
