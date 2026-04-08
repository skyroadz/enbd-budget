import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { useApi } from '../hooks/useApi'
import { CATEGORY_COLORS } from '../constants'

const TOP_N = 10

export default function CategoryDonutChart({ apiSuffix }) {
  const { data, loading, error } = useApi('/api/summary/monthly' + apiSuffix)

  if (loading) return <div className="h-80 bg-gray-100 animate-pulse rounded-lg" />
  if (error) return <p className="text-red-500 text-sm">{error}</p>

  const sorted = Object.entries(data.category_totals).sort((a, b) => b[1] - a[1])

  const slices = sorted.slice(0, TOP_N).map(([name, value]) => ({ name, value }))
  const otherValue = sorted.slice(TOP_N).reduce((s, [, v]) => s + v, 0)
  if (otherValue > 0) slices.push({ name: 'other', value: Math.round(otherValue * 100) / 100 })

  const fmt = n => `AED ${Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 })}`

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Category Breakdown</h3>
      <ResponsiveContainer width="100%" height={320}>
        <PieChart>
          <Pie
            data={slices}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="45%"
            innerRadius={60}
            outerRadius={100}
            paddingAngle={2}
          >
            {slices.map(entry => (
              <Cell
                key={entry.name}
                fill={CATEGORY_COLORS[entry.name] ?? CATEGORY_COLORS.other}
              />
            ))}
          </Pie>
          <Tooltip
            formatter={(value, name) => [fmt(value), name.replace(/_/g, ' ')]}
          />
          <Legend
            formatter={name => name.replace(/_/g, ' ')}
            iconSize={10}
            wrapperStyle={{ fontSize: 11 }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
