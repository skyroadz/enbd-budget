import {
  ComposedChart, Bar, Line,
  XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { useApi } from '../hooks/useApi'

const fmtAED  = v => `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
const fmtK    = v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)

const SERIES = [
  { key: 'income',          label: 'Income',           color: '#3b82f6', type: 'bar'  },
  { key: 'savings_actual',  label: 'Saved this month', color: '#0f766e', type: 'bar'  },
  { key: 'savings_balance', label: 'Savings balance',  color: '#10b981', type: 'line' },
]

export default function BankHistoryChart({ apiSuffix }) {
  const qs = apiSuffix ? apiSuffix.replace('?', '?') : ''
  const { data, loading, error } = useApi('/api/bank-history' + (qs || ''))

  if (loading) return <div className="h-80 bg-gray-100 animate-pulse rounded-lg" />
  if (error)   return <p className="text-red-500 text-sm">{error}</p>
  if (!data?.months?.length) return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 flex items-center justify-center h-40">
      <p className="text-sm text-gray-400">No bank statement data yet — add PDFs to data/chequing/ and data/savings/</p>
    </div>
  )

  const chartData = data.months.map(m => ({
    ym: `${m.year.slice(2)}-${m.month}`,
    income:          m.income          ?? null,
    savings_actual:  m.savings_actual  ?? null,
    savings_balance: m.savings_balance ?? null,
  }))

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Income &amp; Savings Over Time</h3>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={chartData} margin={{ top: 4, right: 48, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="ym" tick={{ fontSize: 11 }} />

          {/* Left axis — monthly flows (income, saved) */}
          <YAxis
            yAxisId="flow"
            orientation="left"
            tickFormatter={fmtK}
            tick={{ fontSize: 11 }}
            width={44}
          />

          {/* Right axis — cumulative balance */}
          <YAxis
            yAxisId="balance"
            orientation="right"
            tickFormatter={fmtK}
            tick={{ fontSize: 11 }}
            width={52}
          />

          <Tooltip
            formatter={(value, name) => [
              value != null ? fmtAED(value) : '—',
              SERIES.find(s => s.key === name)?.label ?? name,
            ]}
          />
          <Legend
            formatter={name => SERIES.find(s => s.key === name)?.label ?? name}
          />

          <Bar
            yAxisId="flow"
            dataKey="income"
            name="income"
            fill="#3b82f6"
            radius={[3, 3, 0, 0]}
            maxBarSize={40}
          />
          <Bar
            yAxisId="flow"
            dataKey="savings_actual"
            name="savings_actual"
            fill="#0f766e"
            radius={[3, 3, 0, 0]}
            maxBarSize={40}
          />
          <Line
            yAxisId="balance"
            type="monotone"
            dataKey="savings_balance"
            name="savings_balance"
            stroke="#10b981"
            strokeWidth={2.5}
            dot={{ r: 4, fill: '#10b981' }}
            activeDot={{ r: 5 }}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>

      <p className="mt-3 text-xs text-gray-400">
        Bars use left axis (monthly flows) · Balance line uses right axis (account total)
      </p>
    </div>
  )
}
