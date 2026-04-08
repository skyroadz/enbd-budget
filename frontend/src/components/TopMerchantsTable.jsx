import { useApi } from '../hooks/useApi'
import { CATEGORY_COLORS } from '../constants'

export default function TopMerchantsTable({ apiSuffix }) {
  const qs = apiSuffix ? apiSuffix + '&limit=10' : '?limit=10'
  const { data, loading, error } = useApi('/api/summary/merchants' + qs)

  if (loading) return <div className="h-64 bg-gray-100 animate-pulse rounded-lg" />
  if (error) return <p className="text-red-500 text-sm">{error}</p>

  const fmt = n =>
    `AED ${Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Top Merchants</h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-gray-500 uppercase border-b border-gray-100">
            <th className="pb-2 font-medium">#</th>
            <th className="pb-2 font-medium">Merchant</th>
            <th className="pb-2 font-medium">Category</th>
            <th className="pb-2 font-medium text-right">Total Spend</th>
            <th className="pb-2 font-medium text-right">Txns</th>
          </tr>
        </thead>
        <tbody>
          {data.merchants.map((m, i) => (
            <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
              <td className="py-2 text-gray-400 text-xs">{i + 1}</td>
              <td className="py-2 font-medium text-gray-900">{m.merchant}</td>
              <td className="py-2">
                <span className="inline-flex items-center gap-1.5 text-xs">
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: CATEGORY_COLORS[m.category] ?? '#9ca3af' }}
                  />
                  {m.category.replace(/_/g, ' ')}
                </span>
              </td>
              <td className="py-2 text-right tabular-nums">{fmt(m.total_aed)}</td>
              <td className="py-2 text-right tabular-nums text-gray-500">{m.txn_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
