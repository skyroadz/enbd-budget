import { useState, useEffect } from 'react'
import { CATEGORY_COLORS } from '../constants'

const fmt = n =>
  `AED ${Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const MONTHS = [
  { value: '01', label: 'January' },  { value: '02', label: 'February' },
  { value: '03', label: 'March' },    { value: '04', label: 'April' },
  { value: '05', label: 'May' },      { value: '06', label: 'June' },
  { value: '07', label: 'July' },     { value: '08', label: 'August' },
  { value: '09', label: 'September' },{ value: '10', label: 'October' },
  { value: '11', label: 'November' }, { value: '12', label: 'December' },
]

// Category hierarchy: parent label → children category names
const CATEGORY_GROUPS = [
  { key: 'entertainment', label: 'Entertainment', children: ['dining', 'food_delivery'] },
  { key: 'car',           label: 'Car',           children: ['fuel'] },
  { key: 'home',          label: 'Home',          children: ['utilities', 'rent', 'groceries', 'housekeeping'] },
]

function InlineEdit({ initialValue, onSave, onCancel }) {
  const [val, setVal] = useState(initialValue ?? '')
  return (
    <input
      autoFocus
      type="number"
      min="0"
      value={val}
      onChange={e => setVal(e.target.value)}
      onBlur={() => onSave(val)}
      onKeyDown={e => {
        if (e.key === 'Enter')  onSave(val)
        if (e.key === 'Escape') onCancel()
      }}
      className="w-32 text-right border border-blue-400 rounded px-2 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
    />
  )
}

function ConfigCard({ label, editKey, value, editingKey, setEditingKey, onSave, onDelete, placeholder, sub }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-1">
      <span className="text-xs text-gray-500 uppercase font-medium tracking-wide">{label}</span>
      {editingKey === editKey ? (
        <InlineEdit
          initialValue={value != null ? String(value) : ''}
          onSave={onSave}
          onCancel={() => setEditingKey(null)}
        />
      ) : value != null ? (
        <div className="flex items-baseline gap-2">
          <button
            onClick={() => setEditingKey(editKey)}
            className="text-lg font-semibold text-gray-900 hover:text-blue-600 hover:underline tabular-nums"
            title="Click to edit"
          >
            {fmt(value)}
          </button>
          <button
            onClick={onDelete}
            className="text-gray-300 hover:text-red-400 text-xs ml-auto"
            title="Remove"
          >✕</button>
        </div>
      ) : (
        <button
          onClick={() => setEditingKey(editKey)}
          className="text-sm text-blue-500 hover:underline text-left"
        >
          {placeholder}
        </button>
      )}
      {sub && <span className="text-xs text-gray-400">{sub}</span>}
    </div>
  )
}

export default function BudgetPage() {
  const today = new Date()
  const [year, setYear]   = useState(String(today.getFullYear()))
  const [month, setMonth] = useState(String(today.getMonth() + 1).padStart(2, '0'))
  const [data, setData]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [editingKey, setEditingKey] = useState(null)
  const [expandedGroups, setExpandedGroups] = useState(
    new Set(CATEGORY_GROUPS.map(g => g.key))
  )
  // Rent edit form state (amount + effective-from date)
  const [rentEditAmount, setRentEditAmount] = useState('')
  const [rentEditYear,   setRentEditYear]   = useState(String(today.getFullYear()))
  const [rentEditMonth,  setRentEditMonth]  = useState(String(today.getMonth() + 1).padStart(2, '0'))

  const years = []
  for (let y = 2024; y <= today.getFullYear(); y++) years.push(String(y))

  const load = () => {
    setLoading(true)
    setError(null)
    fetch(`/api/budget?year=${year}&month=${month}`)
      .then(res => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json() })
      .then(json => { setData(json); setLoading(false) })
      .catch(err => { setError(err.message); setLoading(false) })
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [year, month])

  // --- category budget (monthly target) ---
  const saveCategoryBudget = (category, val) => {
    setEditingKey(null)
    const amount = parseFloat(val)
    if (isNaN(amount) || amount <= 0) return
    fetch('/api/budget', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category, monthly_aed: amount }),
    }).then(() => load())
  }

  const deleteCategoryBudget = category => {
    fetch(`/api/budget/${encodeURIComponent(category)}`, { method: 'DELETE' }).then(() => load())
  }

  // --- manual spend (savings) ---
  const saveCategorySpent = (category, val) => {
    setEditingKey(null)
    const amount = parseFloat(val)
    if (isNaN(amount) || amount < 0) return
    fetch('/api/monthly-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year, month, key: `${category}_actual`, amount_aed: amount }),
    }).then(() => load())
  }

  const deleteCategorySpent = category => {
    fetch(`/api/monthly-config/${year}/${month}/${category}_actual`, { method: 'DELETE' })
      .then(() => load())
  }

  // --- monthly config (income, savings_balance, wife_income) ---
  const saveConfig = (key, val) => {
    setEditingKey(null)
    const amount = parseFloat(val)
    if (isNaN(amount) || amount <= 0) return
    fetch('/api/monthly-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ year, month, key, amount_aed: amount }),
    }).then(() => load())
  }

  const deleteConfig = key => {
    fetch(`/api/monthly-config/${year}/${month}/${key}`, { method: 'DELETE' }).then(() => load())
  }

  // --- annual rent (stored for a specific year+month start date) ---
  const openRentEdit = () => {
    // Pre-fill with current effective rent data if available, otherwise default to viewed month
    setRentEditAmount(data?.annual_rent_aed != null ? String(data.annual_rent_aed) : '')
    setRentEditYear(data?.annual_rent_year  || year)
    setRentEditMonth(data?.annual_rent_month || month)
    setEditingKey('annual_rent')
  }

  const saveAnnualRent = () => {
    setEditingKey(null)
    const amount = parseFloat(rentEditAmount)
    if (isNaN(amount) || amount <= 0) return
    // If the effective date changed, delete the old entry first
    const oldYear  = data?.annual_rent_year
    const oldMonth = data?.annual_rent_month
    const dateChanged = oldYear && (oldYear !== rentEditYear || oldMonth !== rentEditMonth)
    const doSave = () =>
      fetch('/api/monthly-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ year: rentEditYear, month: rentEditMonth, key: 'annual_rent', amount_aed: amount }),
      }).then(() => load())
    if (dateChanged) {
      fetch(`/api/monthly-config/${oldYear}/${oldMonth}/annual_rent`, { method: 'DELETE' })
        .then(doSave)
    } else {
      doSave()
    }
  }

  const deleteAnnualRent = () => {
    if (!data?.annual_rent_year || !data?.annual_rent_month) return
    fetch(`/api/monthly-config/${data.annual_rent_year}/${data.annual_rent_month}/annual_rent`, { method: 'DELETE' })
      .then(() => load())
  }

  const toggleGroup = key => {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // Build display rows: group header rows + standalone category rows
  const buildDisplayRows = cats => {
    const catMap = Object.fromEntries(cats.map(c => [c.category, c]))
    const groupedCats = new Set()
    const rows = []

    for (const group of CATEGORY_GROUPS) {
      const allGroupCats = [group.key, ...group.children]
      const presentCats  = allGroupCats.filter(k => catMap[k])
      if (presentCats.length === 0) continue
      allGroupCats.forEach(k => groupedCats.add(k))

      const rawBudget   = presentCats.reduce((s, k) => s + (catMap[k]?.budget_aed || 0), 0)
      const groupBudget = rawBudget > 0 ? Math.round(rawBudget * 100) / 100 : null
      const groupSpent  = Math.round(presentCats.reduce((s, k) => s + (catMap[k]?.spent_aed || 0), 0) * 100) / 100
      const groupRem    = groupBudget != null ? Math.round((groupBudget - groupSpent) * 100) / 100 : null
      const groupPct    = groupBudget ? Math.round(groupSpent / groupBudget * 1000) / 10 : null

      rows.push({
        type: 'group',
        key:  group.key,
        label: group.label,
        budget_aed:    groupBudget,
        spent_aed:     groupSpent,
        remaining_aed: groupRem,
        pct_used:      groupPct,
        // All categories in the group shown as children (parent key + children)
        children: allGroupCats.filter(k => catMap[k]),
      })
    }

    for (const cat of cats) {
      if (!groupedCats.has(cat.category)) {
        rows.push({ type: 'cat', ...cat })
      }
    }

    return rows
  }

  // Render a single category row
  const renderCatRow = (cat, isChild = false) => {
    const color       = CATEGORY_COLORS[cat.category] ?? '#9ca3af'
    const catBudgKey  = `cat:${cat.category}`
    const catSpentKey = `spent:${cat.category}`
    const editingBudget = editingKey === catBudgKey
    const editingSpent  = editingKey === catSpentKey
    const pct      = cat.pct_used ?? 0
    const barColor = cat.invert_surplus
      ? '#22c55e'  // savings: always green regardless of %
      : pct > 100 ? '#ef4444' : pct > 80 ? '#f97316' : '#22c55e'
    const barWidth = Math.min(pct, 100)

    return (
      <tr key={cat.category} className={`border-b border-gray-50 hover:bg-gray-50 ${isChild ? 'bg-gray-50/40' : ''}`}>

        <td className="px-5 py-3">
          <span className={`inline-flex items-center gap-2 ${isChild ? 'pl-5' : ''}`}>
            <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
            <span className={`font-medium ${isChild ? 'text-gray-600 text-sm' : 'text-gray-900'}`}>
              {cat.category.replace(/_/g, ' ')}
            </span>
            {cat.manual_spend && (
              <span className="text-xs text-gray-400 italic">manual</span>
            )}
          </span>
        </td>

        <td className="px-5 py-3 text-right">
          {editingBudget ? (
            <InlineEdit
              initialValue={cat.budget_aed != null ? String(cat.budget_aed) : ''}
              onSave={v => saveCategoryBudget(cat.category, v)}
              onCancel={() => setEditingKey(null)}
            />
          ) : cat.budget_aed != null ? (
            <button
              onClick={() => setEditingKey(catBudgKey)}
              className="tabular-nums text-gray-900 hover:text-blue-600 hover:underline"
              title="Click to edit"
            >
              {fmt(cat.budget_aed)}
            </button>
          ) : (
            <button
              onClick={() => setEditingKey(catBudgKey)}
              className="text-xs text-blue-500 hover:underline"
            >
              + Set budget
            </button>
          )}
        </td>

        <td className="px-5 py-3 text-right tabular-nums">
          {cat.manual_spend ? (
            editingSpent ? (
              <InlineEdit
                initialValue={cat.spent_aed > 0 ? String(cat.spent_aed) : ''}
                onSave={v => saveCategorySpent(cat.category, v)}
                onCancel={() => setEditingKey(null)}
              />
            ) : (
              <button
                onClick={() => setEditingKey(catSpentKey)}
                className="tabular-nums text-gray-700 hover:text-blue-600 hover:underline inline-flex items-center gap-1"
                title="Click to enter amount"
              >
                {cat.spent_aed > 0 ? fmt(cat.spent_aed) : <span className="text-gray-400">—</span>}
                <svg className="w-3 h-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 112.828 2.828L11.828 15.828a2 2 0 01-1.414.586H9v-2a2 2 0 01.586-1.414z" />
                </svg>
              </button>
            )
          ) : (
            <span className="text-gray-700">{fmt(cat.spent_aed)}</span>
          )}
        </td>

        <td className="px-5 py-3 text-right tabular-nums">
          {cat.remaining_aed != null ? (
            cat.invert_surplus ? (
              // For savings: negative remaining = saved extra (good), positive = short (bad)
              cat.remaining_aed <= 0 ? (
                <span className="text-emerald-600 font-medium" title="Saved above target">
                  +{fmt(Math.abs(cat.remaining_aed))}
                </span>
              ) : (
                <span className="text-red-500 font-medium" title="Below savings target">
                  -{fmt(cat.remaining_aed)}
                </span>
              )
            ) : (
              <span className={cat.remaining_aed < 0 ? 'text-red-500 font-medium' : 'text-gray-700'}>
                {cat.remaining_aed < 0 ? '-' : ''}{fmt(Math.abs(cat.remaining_aed))}
              </span>
            )
          ) : (
            <span className="text-gray-300">—</span>
          )}
        </td>

        <td className="px-5 py-3 w-52">
          {cat.budget_aed != null ? (
            <div className="flex items-center gap-2">
              <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full rounded-full transition-all" style={{ width: `${barWidth}%`, backgroundColor: barColor }} />
              </div>
              <span className="text-xs tabular-nums text-gray-500 w-10 text-right">{pct}%</span>
            </div>
          ) : (
            <span className="text-xs text-gray-300">no budget</span>
          )}
        </td>

        <td className="px-3 py-3">
          <div className="flex gap-1">
            {cat.manual_spend && cat.spent_aed > 0 && (
              <button
                onClick={() => deleteCategorySpent(cat.category)}
                className="text-gray-300 hover:text-orange-400 text-xs"
                title="Clear entered amount"
              >⟳</button>
            )}
            {cat.budget_aed != null && (
              <button
                onClick={() => deleteCategoryBudget(cat.category)}
                className="text-gray-300 hover:text-red-400"
                title="Remove budget"
              >✕</button>
            )}
          </div>
        </td>
      </tr>
    )
  }

  // Raw totals across all categories (no double-counting from grouping)
  const totalBudget    = data ? data.categories.reduce((s, c) => s + (c.budget_aed || 0), 0) : 0
  const totalSpent     = data ? data.categories.reduce((s, c) => s + (c.spent_aed  || 0), 0) : 0
  const totalRemaining = totalBudget - totalSpent

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Budget vs Spend</h2>
        <div className="flex gap-2">
          <select
            value={month}
            onChange={e => setMonth(e.target.value)}
            className="border border-gray-200 rounded-md text-sm px-3 py-1.5 bg-white"
          >
            {MONTHS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
          <select
            value={year}
            onChange={e => setYear(e.target.value)}
            className="border border-gray-200 rounded-md text-sm px-3 py-1.5 bg-white"
          >
            {years.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
      </div>

      {loading && <div className="h-64 bg-gray-100 animate-pulse rounded-lg" />}
      {error   && <p className="text-red-500 text-sm">{error}</p>}

      {!loading && !error && data && (<>

        {/* ── Summary strip ── */}
        <div className="grid grid-cols-2 xl:grid-cols-3 gap-4 mb-6">

          <ConfigCard
            label="My Income"
            editKey="income"
            value={data.income_aed}
            editingKey={editingKey}
            setEditingKey={setEditingKey}
            onSave={v => saveConfig('income', v)}
            onDelete={() => deleteConfig('income')}
            placeholder="+ Set income"
          />

          <ConfigCard
            label="Second Income"
            editKey="wife_income"
            value={data.wife_income_aed}
            editingKey={editingKey}
            setEditingKey={setEditingKey}
            onSave={v => saveConfig('wife_income', v)}
            onDelete={() => deleteConfig('wife_income')}
            placeholder="+ Set income"
          />

          {/* Net */}
          <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-1">
            <span className="text-xs text-gray-500 uppercase font-medium tracking-wide">Net</span>
            {data.net_aed != null ? (
              <>
                <span className={`text-lg font-semibold tabular-nums ${data.net_aed >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                  {data.net_aed >= 0 ? '+' : ''}{fmt(data.net_aed)}
                </span>
                {data.total_income_aed != null && (
                  <span className="text-xs text-gray-400">
                    of {fmt(data.total_income_aed)} income
                  </span>
                )}
                <span className={`text-xs font-medium ${data.net_aed >= 0 ? 'text-emerald-500' : 'text-red-400'}`}>
                  {data.net_aed >= 0 ? 'surplus' : 'deficit'} · excl. savings
                </span>
              </>
            ) : (
              <span className="text-sm text-gray-400">Set income to see net</span>
            )}
          </div>

          {/* Total Spend */}
          <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-1">
            <span className="text-xs text-gray-500 uppercase font-medium tracking-wide">Total Expenses</span>
            <span className="text-lg font-semibold text-gray-900 tabular-nums">
              {fmt(data.total_expenses_aed ?? data.total_spent_aed)}
            </span>
            {data.total_income_aed != null && (
              <span className="text-xs text-gray-400">
                {Math.round((data.total_expenses_aed ?? data.total_spent_aed) / data.total_income_aed * 100)}% of income · excl. savings
              </span>
            )}
          </div>

          {/* Annual Rent */}
          <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-2">
            <span className="text-xs text-gray-500 uppercase font-medium tracking-wide">Annual Rent</span>
            {editingKey === 'annual_rent' ? (
              <div className="flex flex-col gap-2">
                <input
                  autoFocus
                  type="number"
                  min="0"
                  placeholder="Annual amount"
                  value={rentEditAmount}
                  onChange={e => setRentEditAmount(e.target.value)}
                  className="w-full text-right border border-blue-400 rounded px-2 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <div className="flex flex-col gap-0.5">
                  <span className="text-xs text-gray-400">Effective from</span>
                  <div className="flex gap-1">
                    <select
                      value={rentEditMonth}
                      onChange={e => setRentEditMonth(e.target.value)}
                      className="flex-1 border border-gray-200 rounded text-xs px-1 py-1 bg-white"
                    >
                      {MONTHS.map(mo => <option key={mo.value} value={mo.value}>{mo.label}</option>)}
                    </select>
                    <select
                      value={rentEditYear}
                      onChange={e => setRentEditYear(e.target.value)}
                      className="border border-gray-200 rounded text-xs px-1 py-1 bg-white"
                    >
                      {years.map(y => <option key={y} value={y}>{y}</option>)}
                    </select>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={saveAnnualRent}
                    className="text-xs bg-blue-600 text-white rounded px-2 py-1 hover:bg-blue-700"
                  >Save</button>
                  <button
                    onClick={() => setEditingKey(null)}
                    className="text-xs text-gray-500 hover:text-gray-700"
                  >Cancel</button>
                </div>
              </div>
            ) : data.annual_rent_aed != null ? (
              <>
                <div className="flex items-baseline gap-2">
                  <button
                    onClick={openRentEdit}
                    className="text-lg font-semibold text-gray-900 hover:text-blue-600 hover:underline tabular-nums"
                    title="Click to edit"
                  >
                    {fmt(data.annual_rent_aed)}
                  </button>
                  <button
                    onClick={deleteAnnualRent}
                    className="text-gray-300 hover:text-red-400 text-xs ml-auto"
                    title="Remove"
                  >✕</button>
                </div>
                <span className="text-xs text-gray-400">
                  Monthly provision: {fmt(data.rent_provision_aed)}
                </span>
                <span className="text-xs text-gray-400">
                  Since {MONTHS.find(mo => mo.value === data.annual_rent_month)?.label} {data.annual_rent_year}
                </span>
              </>
            ) : (
              <button
                onClick={openRentEdit}
                className="text-sm text-blue-500 hover:underline text-left"
              >
                + Set annual rent
              </button>
            )}
          </div>

          <ConfigCard
            label="Savings Balance"
            editKey="savings_balance"
            value={data.savings_balance_aed}
            editingKey={editingKey}
            setEditingKey={setEditingKey}
            onSave={v => saveConfig('savings_balance', v)}
            onDelete={() => deleteConfig('savings_balance')}
            placeholder="+ Set balance"
            sub="Current account balance"
          />
        </div>

        {/* ── Category table ── */}
        {(() => {
          const displayRows = buildDisplayRows(data.categories)
          return (
            <div className="bg-white rounded-lg border border-gray-200">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 uppercase border-b border-gray-100">
                    <th className="px-5 py-3 font-medium">Category</th>
                    <th className="px-5 py-3 font-medium text-right">Monthly Budget</th>
                    <th className="px-5 py-3 font-medium text-right">Spent</th>
                    <th className="px-5 py-3 font-medium text-right">Remaining</th>
                    <th className="px-5 py-3 font-medium w-52">Usage</th>
                    <th className="px-3 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {displayRows.map(row => {
                    if (row.type === 'group') {
                      const isExpanded = expandedGroups.has(row.key)
                      const pct      = row.pct_used ?? 0
                      const barColor = pct > 100 ? '#ef4444' : pct > 80 ? '#f97316' : '#22c55e'
                      const barWidth = Math.min(pct, 100)
                      return (
                        <>
                          <tr key={`grp-${row.key}`} className="border-b border-gray-200 bg-gray-50 hover:bg-gray-100/80">
                            <td className="px-5 py-3">
                              <button
                                onClick={() => toggleGroup(row.key)}
                                className="inline-flex items-center gap-2 font-semibold text-gray-800"
                              >
                                <span className="text-gray-400 text-xs w-3">{isExpanded ? '▾' : '▸'}</span>
                                {row.label}
                              </button>
                            </td>
                            <td className="px-5 py-3 text-right tabular-nums font-semibold text-gray-800">
                              {row.budget_aed != null
                                ? fmt(row.budget_aed)
                                : <span className="text-gray-300 font-normal">—</span>}
                            </td>
                            <td className="px-5 py-3 text-right tabular-nums font-semibold text-gray-800">
                              {fmt(row.spent_aed)}
                            </td>
                            <td className="px-5 py-3 text-right tabular-nums">
                              {row.remaining_aed != null ? (
                                <span className={`font-semibold ${row.remaining_aed < 0 ? 'text-red-500' : 'text-gray-800'}`}>
                                  {row.remaining_aed < 0 ? '-' : ''}{fmt(Math.abs(row.remaining_aed))}
                                </span>
                              ) : <span className="text-gray-300">—</span>}
                            </td>
                            <td className="px-5 py-3 w-52">
                              {row.budget_aed != null ? (
                                <div className="flex items-center gap-2">
                                  <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                                    <div className="h-full rounded-full transition-all" style={{ width: `${barWidth}%`, backgroundColor: barColor }} />
                                  </div>
                                  <span className="text-xs tabular-nums text-gray-500 w-10 text-right">{pct}%</span>
                                </div>
                              ) : <span className="text-xs text-gray-300">no budget</span>}
                            </td>
                            <td className="px-3 py-3" />
                          </tr>
                          {isExpanded && row.children.map(childKey => {
                            const cat = data.categories.find(c => c.category === childKey)
                            return cat ? renderCatRow(cat, true) : null
                          })}
                        </>
                      )
                    }
                    return renderCatRow(row)
                  })}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-gray-200 bg-gray-50">
                    <td className="px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Totals</td>
                    <td className="px-5 py-3 text-right tabular-nums font-semibold text-gray-900">
                      {totalBudget > 0
                        ? fmt(totalBudget)
                        : <span className="text-gray-300 font-normal">—</span>}
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums font-semibold text-gray-900">
                      {fmt(totalSpent)}
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums">
                      {totalBudget > 0 ? (
                        <span className={`font-semibold ${totalRemaining < 0 ? 'text-red-500' : 'text-emerald-600'}`}>
                          {totalRemaining < 0 ? '-' : ''}{fmt(Math.abs(totalRemaining))}
                        </span>
                      ) : <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-5 py-3 w-52" />
                    <td className="px-3 py-3" />
                  </tr>
                </tfoot>
              </table>
            </div>
          )
        })()}

      </>)}
    </div>
  )
}
