import { useState } from 'react'
import { useApi } from '../hooks/useApi'

const MONTHS = [
  { value: '',   label: 'All months' },
  { value: '01', label: 'January' },  { value: '02', label: 'February' },
  { value: '03', label: 'March' },    { value: '04', label: 'April' },
  { value: '05', label: 'May' },      { value: '06', label: 'June' },
  { value: '07', label: 'July' },     { value: '08', label: 'August' },
  { value: '09', label: 'September' },{ value: '10', label: 'October' },
  { value: '11', label: 'November' }, { value: '12', label: 'December' },
]

const fmtAED = n =>
  `AED ${Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const YEARS = ['', '2024', '2025', '2026']

export default function BankTransactionsTable({ account }) {
  const today = new Date()
  const [year,  setYear]  = useState(String(today.getFullYear()))
  const [month, setMonth] = useState('')

  const qs = new URLSearchParams({ account })
  if (year)  qs.set('year', year)
  if (month) qs.set('month', month)
  qs.set('limit', '1000')

  const { data, loading, error } = useApi(`/api/bank-transactions?${qs}`)

  const txns = data?.transactions ?? []

  // Running totals for the filtered period
  const totalIn  = txns.filter(t => t.is_credit).reduce((s, t) => s + t.amount, 0)
  const totalOut = txns.filter(t => !t.is_credit).reduce((s, t) => s + t.amount, 0)
  const net = totalIn - totalOut

  return (
    <div>
      {/* Filters */}
      <div className="mb-4 flex items-center gap-3">
        <select
          value={month} onChange={e => setMonth(e.target.value)}
          className="border border-gray-200 rounded-md text-sm px-3 py-1.5 bg-white"
        >
          {MONTHS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
        <select
          value={year} onChange={e => setYear(e.target.value)}
          className="border border-gray-200 rounded-md text-sm px-3 py-1.5 bg-white"
        >
          {YEARS.map(y => <option key={y} value={y}>{y || 'All years'}</option>)}
        </select>

        {!loading && !error && txns.length > 0 && (
          <div className="ml-auto flex gap-4 text-sm">
            <span className="text-emerald-600 font-medium">↑ {fmtAED(totalIn)}</span>
            <span className="text-red-500 font-medium">↓ {fmtAED(totalOut)}</span>
            <span className={`font-semibold ${net >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
              Net {net >= 0 ? '+' : ''}{fmtAED(net)}
            </span>
          </div>
        )}
      </div>

      {loading && <div className="h-48 bg-gray-100 animate-pulse rounded-lg" />}
      {error   && <p className="text-red-500 text-sm">{error}</p>}

      {!loading && !error && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          {txns.length === 0 ? (
            <p className="p-8 text-center text-sm text-gray-400">No transactions found for this period.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 uppercase border-b border-gray-100 bg-gray-50">
                  <th className="px-5 py-3 font-medium">Date</th>
                  <th className="px-5 py-3 font-medium">Description</th>
                  <th className="px-5 py-3 font-medium text-right">Amount</th>
                  <th className="px-5 py-3 font-medium text-right">Balance</th>
                </tr>
              </thead>
              <tbody>
                {txns.map((t, i) => (
                  <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="px-5 py-2.5 text-gray-500 whitespace-nowrap text-xs">
                      {t.txn_date}
                    </td>
                    <td className="px-5 py-2.5 text-gray-800 max-w-xs">
                      <span className="line-clamp-2">{t.description}</span>
                    </td>
                    <td className={`px-5 py-2.5 text-right tabular-nums font-medium whitespace-nowrap ${
                      t.is_credit ? 'text-emerald-600' : 'text-red-500'
                    }`}>
                      {t.is_credit ? '+' : '−'}{fmtAED(t.amount)}
                    </td>
                    <td className="px-5 py-2.5 text-right tabular-nums text-gray-500 whitespace-nowrap">
                      {fmtAED(t.balance)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
