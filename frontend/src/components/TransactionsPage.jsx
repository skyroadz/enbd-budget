import { useState, useMemo } from 'react'
import { useApi } from '../hooks/useApi'
import FilterBar from './FilterBar'
import { CATEGORY_COLORS, CATEGORIES } from '../constants'

const PAGE_SIZE = 50
const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

const SORT_FNS = {
  txn_date:   (a, b) => a.txn_date.localeCompare(b.txn_date),
  merchant:   (a, b) => (a.merchant ?? '').localeCompare(b.merchant ?? ''),
  category:   (a, b) => (a.category ?? '').localeCompare(b.category ?? ''),
  amount_aed: (a, b) => a.amount_aed - b.amount_aed,
}

function SortIcon({ field, sortKey, sortAsc }) {
  if (field !== sortKey) return <span className="text-gray-300 ml-1">↕</span>
  return <span className="ml-1">{sortAsc ? '↑' : '↓'}</span>
}

export default function TransactionsPage() {
  const { data, loading, error } = useApi('/transactions?limit=5000')

  const [filters, setFilters] = useState({
    year: '', month: '', category: '', merchant: '', cardScope: '',
  })
  const [sortKey, setSortKey] = useState('txn_date')
  const [sortAsc, setSortAsc] = useState(false)
  const [page, setPage]       = useState(1)
  // Local category overrides: id → { category, locked } (optimistic updates without full refetch)
  const [categoryEdits, setCategoryEdits] = useState({})
  const [editingCatId, setEditingCatId]   = useState(null)
  const [overrideMsg, setOverrideMsg]     = useState(null) // { type: 'ok'|'err', text: string }

  const rows = useMemo(() => {
    if (!data?.items) return []
    let r = data.items

    if (filters.year)      r = r.filter(t => t.txn_date.startsWith(filters.year))
    if (filters.month)     r = r.filter(t => t.txn_date.slice(5, 7) === filters.month)
    if (filters.category)  r = r.filter(t => t.category === filters.category)
    if (filters.cardScope) r = r.filter(t => t.card_scope === filters.cardScope)
    if (filters.merchant) {
      const q = filters.merchant.toLowerCase()
      r = r.filter(t => (t.merchant ?? '').toLowerCase().includes(q))
    }

    const cmp = SORT_FNS[sortKey] ?? SORT_FNS.txn_date
    return [...r].sort((a, b) => sortAsc ? cmp(a, b) : cmp(b, a))
  }, [data, filters, sortKey, sortAsc])

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const pageRows   = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  function handleSort(key) {
    if (key === sortKey) setSortAsc(v => !v)
    else { setSortKey(key); setSortAsc(true) }
    setPage(1)
  }

  function handleFilter(f) {
    setFilters(f)
    setPage(1)
  }

  const saveCategoryOverride = (txnId, newCategory, txnDate) => {
    setEditingCatId(null)
    if (!newCategory) return
    fetch(`/transactions/${encodeURIComponent(txnId)}/category`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category: newCategory }),
    }).then(res => {
      if (res.ok) {
        setCategoryEdits(prev => ({ ...prev, [txnId]: { category: newCategory, locked: true } }))
        const [y, m] = (txnDate || '').split('-')
        const monthLabel = MONTHS_SHORT[parseInt(m, 10) - 1] ?? m
        setOverrideMsg({ type: 'ok', text: `Saved. Check budget for ${monthLabel} ${y} to see the change.` })
        setTimeout(() => setOverrideMsg(null), 6000)
      } else {
        res.json().catch(() => ({})).then(body => {
          setOverrideMsg({ type: 'err', text: `Save failed: ${body?.detail ?? res.status}` })
          setTimeout(() => setOverrideMsg(null), 8000)
        })
      }
    }).catch(() => {
      setOverrideMsg({ type: 'err', text: 'Save failed: network error' })
      setTimeout(() => setOverrideMsg(null), 8000)
    })
  }

  const clearCategoryOverride = (txnId) => {
    fetch(`/transactions/${encodeURIComponent(txnId)}/category-override`, { method: 'DELETE' })
      .then(res => res.json())
      .then(json => {
        setCategoryEdits(prev => ({ ...prev, [txnId]: { category: json.category, locked: false } }))
        setOverrideMsg({ type: 'ok', text: 'Reset to auto-categorized.' })
        setTimeout(() => setOverrideMsg(null), 4000)
      })
  }

  const fmt = n => {
    const abs = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    return n < 0 ? `−AED ${abs}` : `AED ${abs}`
  }

  const cols = [
    { key: 'txn_date',   label: 'Date'     },
    { key: 'merchant',   label: 'Merchant' },
    { key: 'category',   label: 'Category' },
    { key: 'amount_aed', label: 'Amount'   },
  ]

  if (loading) return <div className="h-96 bg-gray-100 animate-pulse rounded-lg" />
  if (error)   return <p className="text-red-500">Failed to load transactions: {error}</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">Transactions</h2>
        <p className="text-sm text-gray-500">
          {rows.length.toLocaleString()} matching · {data.items.length.toLocaleString()} total
        </p>
      </div>

      <FilterBar filters={filters} onChange={handleFilter} />

      {overrideMsg && (
        <div className={`mb-3 px-4 py-2 rounded-md text-sm flex items-center justify-between ${
          overrideMsg.type === 'ok'
            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
            : 'bg-red-50 text-red-700 border border-red-200'
        }`}>
          <span>{overrideMsg.text}</span>
          <button onClick={() => setOverrideMsg(null)} className="ml-4 opacity-50 hover:opacity-100">✕</button>
        </div>
      )}

      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {cols.map(({ key, label }) => (
                  <th
                    key={key}
                    onClick={() => handleSort(key)}
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100 select-none whitespace-nowrap"
                  >
                    {label}
                    <SortIcon field={key} sortKey={sortKey} sortAsc={sortAsc} />
                  </th>
                ))}
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Card</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {pageRows.map((t, i) => {
                const edit       = categoryEdits[t.id]
                const category   = edit?.category ?? t.category ?? ''
                const isLocked   = edit ? edit.locked : Boolean(t.category_locked)
                const isEditing  = editingCatId === t.id
                return (
                  <tr key={i} className="hover:bg-gray-50 group">
                    <td className="px-4 py-2.5 text-gray-500 tabular-nums whitespace-nowrap">{t.txn_date}</td>
                    <td className="px-4 py-2.5 font-medium text-gray-900 max-w-xs truncate">
                      {t.merchant || t.description_raw}
                    </td>
                    <td className="px-4 py-2.5 whitespace-nowrap">
                      {isEditing ? (
                        <select
                          autoFocus
                          defaultValue={category}
                          onChange={e => saveCategoryOverride(t.id, e.target.value, t.txn_date)}
                          onBlur={() => setEditingCatId(null)}
                          className="text-xs border border-blue-400 rounded px-1 py-0.5 bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                        >
                          {CATEGORIES.map(c => (
                            <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
                          ))}
                        </select>
                      ) : (
                        <button
                          onClick={() => setEditingCatId(t.id)}
                          className="inline-flex items-center gap-1.5 text-xs hover:text-blue-600 group/cat"
                          title="Click to change category"
                        >
                          <span
                            className="w-2 h-2 rounded-full flex-shrink-0"
                            style={{ backgroundColor: CATEGORY_COLORS[category] ?? '#9ca3af' }}
                          />
                          {category.replace(/_/g, ' ')}
                          {isLocked && (
                            <span className="text-amber-400 text-xs" title="Manually overridden">✎</span>
                          )}
                          <span className="opacity-0 group-hover/cat:opacity-100 text-gray-300 text-xs transition-opacity">✎</span>
                        </button>
                      )}
                      {isLocked && !isEditing && (
                        <button
                          onClick={() => clearCategoryOverride(t.id)}
                          className="ml-1 text-gray-300 hover:text-red-400 text-xs"
                          title="Reset to auto-categorized"
                        >↺</button>
                      )}
                    </td>
                    <td className={`px-4 py-2.5 tabular-nums text-right whitespace-nowrap ${
                      t.amount_aed < 0 ? 'text-green-600 font-medium' : 'text-gray-900'
                    }`}>
                      {fmt(t.amount_aed)}
                    </td>
                    <td className="px-4 py-2.5 text-gray-400 text-xs capitalize whitespace-nowrap">
                      {t.card_scope}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="text-sm px-3 py-1 rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="text-sm text-gray-600">
              Page {page} of {totalPages} · rows {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, rows.length)}
            </span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="text-sm px-3 py-1 rounded border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
