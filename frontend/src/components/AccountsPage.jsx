import { useState, useMemo } from 'react'
import { useApi } from '../hooks/useApi'
import BankHistoryChart from './BankHistoryChart'
import BankLineChart from './BankLineChart'
import BankTransactionsTable from './BankTransactionsTable'
import PeriodSelector from './PeriodSelector'
import { PERIOD_OPTIONS } from '../constants'

const fmt = n =>
  `AED ${Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const SUB_TABS = [
  { key: 'overview', label: 'Overview'  },
  { key: 'chequing', label: 'Chequing'  },
  { key: 'savings',  label: 'Savings'   },
]

function StatCard({ label, value, sub, color }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-1">
      <span className="text-xs text-gray-500 uppercase font-medium tracking-wide">{label}</span>
      {value != null ? (
        <span className={`text-lg font-semibold tabular-nums ${color ?? 'text-gray-900'}`}>
          {fmt(value)}
        </span>
      ) : (
        <span className="text-sm text-gray-400">—</span>
      )}
      {sub && <span className="text-xs text-gray-400">{sub}</span>}
    </div>
  )
}

function Overview() {
  const [period, setPeriod] = useState(PERIOD_OPTIONS[2])
  const apiSuffix = period.value ? `?months_back=${period.value}` : ''
  const { data, loading, error } = useApi('/api/bank-history' + apiSuffix)

  const stats = useMemo(() => {
    if (!data?.months?.length) return null
    const months = data.months
    const latestBalance = [...months].reverse().find(m => m.savings_balance != null)?.savings_balance
    const latestIncome  = [...months].reverse().find(m => m.income != null)?.income
    const totalSaved    = months.reduce((s, m) => s + (m.savings_actual ?? 0), 0)
    const bothMonths    = months.filter(m => m.income != null && m.savings_actual != null)
    const avgRate       = bothMonths.length
      ? bothMonths.reduce((s, m) => s + m.savings_actual / m.income * 100, 0) / bothMonths.length
      : null
    return { latestBalance, latestIncome, totalSaved, avgRate }
  }, [data])

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Accounts Overview</h2>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {loading && <div className="h-64 bg-gray-100 animate-pulse rounded-lg" />}
      {error   && <p className="text-red-500 text-sm">{error}</p>}

      {!loading && !error && (<>
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
          <StatCard label="Current Savings Balance" value={stats?.latestBalance}
            sub="Latest statement balance" color="text-emerald-600" />
          <StatCard label="Latest Monthly Income" value={stats?.latestIncome}
            sub="Most recent salary credit" />
          <StatCard label="Total Saved (period)" value={stats?.totalSaved}
            sub="Sum of transfers to savings" color="text-teal-700" />
          <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-1">
            <span className="text-xs text-gray-500 uppercase font-medium tracking-wide">Avg Savings Rate</span>
            {stats?.avgRate != null ? (
              <>
                <span className={`text-lg font-semibold tabular-nums ${
                  stats.avgRate >= 20 ? 'text-emerald-600' : stats.avgRate >= 10 ? 'text-amber-500' : 'text-red-500'
                }`}>{stats.avgRate.toFixed(1)}%</span>
                <span className="text-xs text-gray-400">of income saved per month</span>
              </>
            ) : <span className="text-sm text-gray-400">—</span>}
          </div>
        </div>

        <BankHistoryChart apiSuffix={apiSuffix} />

        <div className="mt-6">
          <BankLineChart apiSuffix={apiSuffix} />
        </div>

        {data?.months?.length > 0 && (
          <div className="mt-6 bg-white rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 uppercase border-b border-gray-100">
                  <th className="px-5 py-3 font-medium">Month</th>
                  <th className="px-5 py-3 font-medium text-right">Income</th>
                  <th className="px-5 py-3 font-medium text-right">Saved</th>
                  <th className="px-5 py-3 font-medium text-right">Savings Rate</th>
                  <th className="px-5 py-3 font-medium text-right">Account Balance</th>
                </tr>
              </thead>
              <tbody>
                {[...data.months].reverse().map(m => {
                  const rate = m.income && m.savings_actual
                    ? (m.savings_actual / m.income * 100).toFixed(1) : null
                  return (
                    <tr key={m.ym} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="px-5 py-2.5 font-medium text-gray-900">
                        {new Date(m.year, parseInt(m.month) - 1)
                          .toLocaleString('en-US', { month: 'long', year: 'numeric' })}
                      </td>
                      <td className="px-5 py-2.5 text-right tabular-nums text-gray-700">
                        {m.income != null ? fmt(m.income) : <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-5 py-2.5 text-right tabular-nums text-teal-700">
                        {m.savings_actual != null ? fmt(m.savings_actual) : <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-5 py-2.5 text-right tabular-nums">
                        {rate != null
                          ? <span className={parseFloat(rate) >= 20 ? 'text-emerald-600 font-medium' : 'text-gray-700'}>{rate}%</span>
                          : <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-5 py-2.5 text-right tabular-nums text-emerald-600 font-medium">
                        {m.savings_balance != null ? fmt(m.savings_balance) : <span className="text-gray-300 font-normal">—</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </>)}
    </>
  )
}

export default function AccountsPage() {
  const [subTab, setSubTab] = useState('overview')

  return (
    <div>
      {/* Sub-tab bar */}
      <div className="mb-6 flex gap-1 border-b border-gray-200">
        {SUB_TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setSubTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
              subTab === t.key
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {subTab === 'overview' && <Overview />}

      {subTab === 'chequing' && (
        <>
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Chequing Transactions</h2>
          <BankTransactionsTable account="chequing" />
        </>
      )}

      {subTab === 'savings' && (
        <>
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Savings Transactions</h2>
          <BankTransactionsTable account="savings" />
        </>
      )}
    </div>
  )
}
