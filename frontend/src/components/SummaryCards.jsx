import { useApi } from '../hooks/useApi'

function Card({ label, value, sub }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  )
}

function SkeletonCard() {
  return <div className="bg-gray-100 rounded-lg border border-gray-200 p-5 h-24 animate-pulse" />
}

export default function SummaryCards({ apiSuffix }) {
  const { data, loading, error } = useApi('/api/summary/monthly' + apiSuffix)

  if (loading) return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <SkeletonCard /><SkeletonCard /><SkeletonCard />
    </div>
  )
  if (error) return <p className="text-red-500 text-sm">Failed to load summary: {error}</p>

  const fmt = n => `AED ${Number(n).toLocaleString('en-US', { maximumFractionDigits: 0 })}`

  const topCatEntry = Object.entries(data.category_totals).sort((a, b) => b[1] - a[1])[0]
  const topCat = topCatEntry
    ? `${topCatEntry[0].replace(/_/g, ' ')} · ${fmt(topCatEntry[1])}`
    : '—'

  const txnCount = data.months.reduce((sum, m) => sum + Object.values(m.categories).length, 0)

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <Card label="Total Spend" value={fmt(data.grand_total)} sub={`across ${data.months.length} months`} />
      <Card label="Top Category" value={topCat} />
      <Card label="Transactions" value={txnCount.toLocaleString()} sub="category-month groups" />
    </div>
  )
}
