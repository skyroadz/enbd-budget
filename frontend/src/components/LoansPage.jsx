import { useApi } from '../hooks/useApi'

const fmt = n =>
  `AED ${Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

function StatCard({ label, value, sub, color }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-1">
      <span className="text-xs text-gray-500 uppercase font-medium tracking-wide">{label}</span>
      <span className={`text-lg font-semibold tabular-nums ${color ?? 'text-gray-900'}`}>
        {fmt(value)}
      </span>
      {sub && <span className="text-xs text-gray-400">{sub}</span>}
    </div>
  )
}

function ProgressBar({ paid, total, label }) {
  const pct = total > 0 ? Math.min((paid / total) * 100, 100) : 0
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>{label}</span>
        <span>{pct.toFixed(1)}%</span>
      </div>
      <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-emerald-500 rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function LoanCard({ loan }) {
  const {
    account_no, statement_date, contract_signing_date, maturity_date,
    finance_amount, total_profit_amount,
    outstanding_principal, remaining_profit, total_outstanding,
    next_payment_amount, next_payment_date, remaining_installments,
    paid_principal, paid_profit, total_paid,
  } = loan

  const totalLoan = (finance_amount || 0) + (total_profit_amount || 0)

  function fmtDate(d) {
    if (!d) return '—'
    const [y, m, day] = d.split('-')
    return new Date(y, m - 1, day).toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' })
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-gray-900">ADIB Personal Finance</h3>
          <p className="text-xs text-gray-400 mt-0.5">Account {account_no} · Statement {fmtDate(statement_date)}</p>
        </div>
        <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
          Active · {remaining_installments} payments left
        </span>
      </div>

      <div className="p-6 space-y-6">
        {/* Summary cards */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <StatCard
            label="Outstanding Balance"
            value={total_outstanding}
            sub="Principal + remaining profit"
            color="text-red-600"
          />
          <StatCard
            label="Principal Paid"
            value={paid_principal}
            sub={`of ${fmt(finance_amount)} financed`}
            color="text-emerald-600"
          />
          <StatCard
            label="Interest Paid"
            value={paid_profit}
            sub={`of ${fmt(total_profit_amount)} total profit`}
            color="text-teal-600"
          />
          <StatCard
            label="Total Paid"
            value={total_paid}
            sub={`of ${fmt(totalLoan)} total cost`}
          />
        </div>

        {/* Progress bars */}
        <div className="space-y-3">
          <ProgressBar paid={paid_principal} total={finance_amount} label="Principal repaid" />
          <ProgressBar paid={paid_profit}    total={total_profit_amount} label="Profit paid" />
          <ProgressBar paid={total_paid}     total={totalLoan} label="Overall loan repaid" />
        </div>

        {/* Remaining split */}
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-gray-50 rounded-lg p-4">
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Remaining Principal</p>
            <p className="text-lg font-semibold tabular-nums text-gray-900">{fmt(outstanding_principal)}</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-4">
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Remaining Profit</p>
            <p className="text-lg font-semibold tabular-nums text-gray-900">{fmt(remaining_profit)}</p>
          </div>
        </div>

        {/* Loan details */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-x-6 gap-y-3 pt-2 border-t border-gray-100 text-sm">
          <div>
            <p className="text-xs text-gray-400 mb-0.5">Next Payment</p>
            <p className="font-medium text-gray-800">{fmt(next_payment_amount)}</p>
            <p className="text-xs text-gray-400">{fmtDate(next_payment_date)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-0.5">Maturity Date</p>
            <p className="font-medium text-gray-800">{fmtDate(maturity_date)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-0.5">Contract Signed</p>
            <p className="font-medium text-gray-800">{fmtDate(contract_signing_date)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-0.5">Original Finance</p>
            <p className="font-medium text-gray-800">{fmt(finance_amount)}</p>
            <p className="text-xs text-gray-400">{fmt(total_profit_amount)} profit</p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function LoansPage() {
  const { data, loading, error } = useApi('/api/loans')

  if (loading) return <div className="h-64 bg-gray-100 animate-pulse rounded-xl" />
  if (error)   return <p className="text-red-500 text-sm">{error}</p>
  if (!data?.loans?.length) return (
    <div className="text-center py-16 text-gray-400 text-sm">
      No loan statements found. Add PDFs to <code>data/loans/</code> and refresh.
    </div>
  )

  return (
    <div className="space-y-6">
      {data.loans.map(loan => (
        <LoanCard key={loan.id} loan={loan} />
      ))}
    </div>
  )
}
