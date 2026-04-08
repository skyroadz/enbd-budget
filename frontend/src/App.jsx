import { useState } from 'react'
import PeriodSelector from './components/PeriodSelector'
import SummaryCards from './components/SummaryCards'
import MonthlyStackedBarChart from './components/MonthlyStackedBarChart'
import CategoryDonutChart from './components/CategoryDonutChart'
import TopMerchantsTable from './components/TopMerchantsTable'
import SpendLineChart from './components/SpendLineChart'
import TransactionsPage from './components/TransactionsPage'
import BudgetPage from './components/BudgetPage'
import AccountsPage from './components/AccountsPage'
import LoansPage from './components/LoansPage'
import AdminPage from './components/AdminPage'
import { PERIOD_OPTIONS } from './constants'

const TABS = ['dashboard', 'transactions', 'budget', 'accounts', 'loans', 'ml']
const TAB_LABELS = { ml: 'ML' }

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard')
  const [period, setPeriod]       = useState(PERIOD_OPTIONS[2]) // default: 12 months

  const apiSuffix = period.value ? `?months_back=${period.value}` : ''

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-900">💳 Budget Dashboard</h1>
          <nav className="flex gap-2 items-center">
            {TABS.map(tab => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 rounded-md text-sm font-medium capitalize transition-colors ${
                  activeTab === tab
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                {TAB_LABELS[tab] ?? tab}
              </button>
            ))}
            <a
              href="/cdn-cgi/access/logout"
              className="px-4 py-2 rounded-md text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
            >
              Logout
            </a>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {activeTab === 'dashboard' ? (
          <>
            {/* Period selector */}
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-800">Spending Overview</h2>
              <PeriodSelector value={period} onChange={setPeriod} />
            </div>

            {/* Summary cards */}
            <SummaryCards apiSuffix={apiSuffix} />

            {/* Charts row */}
            <div className="mt-6 grid grid-cols-1 xl:grid-cols-3 gap-6">
              <div className="xl:col-span-2">
                <MonthlyStackedBarChart apiSuffix={apiSuffix} />
              </div>
              <div>
                <CategoryDonutChart apiSuffix={apiSuffix} />
              </div>
            </div>

            {/* Spend over time line chart */}
            <div className="mt-6">
              <SpendLineChart apiSuffix={apiSuffix} />
            </div>

            {/* Top merchants */}
            <div className="mt-6">
              <TopMerchantsTable apiSuffix={apiSuffix} />
            </div>
          </>
        ) : activeTab === 'transactions' ? (
          <TransactionsPage />
        ) : activeTab === 'budget' ? (
          <BudgetPage />
        ) : activeTab === 'accounts' ? (
          <AccountsPage />
        ) : activeTab === 'loans' ? (
          <LoansPage />
        ) : (
          <AdminPage />
        )}
      </main>
    </div>
  )
}
