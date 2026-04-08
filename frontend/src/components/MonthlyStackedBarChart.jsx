import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { useApi } from '../hooks/useApi'
import { CATEGORY_COLORS } from '../constants'

const TOP_N = 8

function fmtAED(value) {
  return `AED ${Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

function fmtLabel(name) {
  return name.replace(/_/g, ' ')
}

export default function MonthlyStackedBarChart({ apiSuffix }) {
  const { data, loading, error } = useApi('/api/summary/monthly' + apiSuffix)

  if (loading) return <div className="h-80 bg-gray-100 animate-pulse rounded-lg" />
  if (error) return <p className="text-red-500 text-sm">{error}</p>

  // Top-N categories by period total
  const topCats = Object.entries(data.category_totals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_N)
    .map(([cat]) => cat)

  // Build one object per month for Recharts
  const chartData = data.months.map(m => {
    const row = { name: `${m.year.slice(2)}-${m.month}` }
    let otherTotal = 0
    Object.entries(m.categories).forEach(([cat, val]) => {
      if (topCats.includes(cat)) row[cat] = val
      else otherTotal += val
    })
    if (otherTotal > 0) row.other = Math.round(otherTotal * 100) / 100
    return row
  })

  const hasOther = chartData.some(r => r.other)
  const allKeys = [...topCats, ...(hasOther ? ['other'] : [])]

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Monthly Spend by Category</h3>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={chartData} margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis
            tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}
            tick={{ fontSize: 11 }}
            width={40}
          />
          <Tooltip
            formatter={(value, name) => [fmtAED(value), fmtLabel(name)]}
            labelFormatter={label => `Month: ${label}`}
          />
          <Legend formatter={fmtLabel} />
          {allKeys.map(cat => (
            <Bar
              key={cat}
              dataKey={cat}
              stackId="a"
              fill={CATEGORY_COLORS[cat] ?? CATEGORY_COLORS.other}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
