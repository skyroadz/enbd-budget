import { useState, useEffect, useMemo, useRef } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { useApi } from '../hooks/useApi'
import { CATEGORIES, CATEGORY_COLORS, MERCHANT_LINE_COLORS } from '../constants'

function fmtAED(v) {
  return `AED ${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

// --- Category multi-select pill UI ---
function CategoryPills({ selected, onToggle }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {CATEGORIES.filter(c => c !== 'uncategorized').map(cat => {
        const active = selected.includes(cat)
        return (
          <button
            key={cat}
            onClick={() => onToggle(cat)}
            className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
              active
                ? 'text-white border-transparent'
                : 'bg-white text-gray-600 border-gray-300 hover:border-gray-400'
            }`}
            style={active ? { backgroundColor: CATEGORY_COLORS[cat], borderColor: CATEGORY_COLORS[cat] } : {}}
          >
            {cat.replace(/_/g, ' ')}
          </button>
        )
      })}
    </div>
  )
}

// --- Merchant autocomplete search ---
function MerchantSearch({ selected, onAdd, onRemove }) {
  const [input, setInput]           = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen]             = useState(false)
  const ref                         = useRef(null)

  // Debounced fetch for autocomplete
  useEffect(() => {
    if (!input.trim()) { setSuggestions([]); return }
    const t = setTimeout(() => {
      fetch(`/api/merchants?q=${encodeURIComponent(input)}`)
        .then(r => r.json())
        .then(j => setSuggestions((j.merchants || []).filter(m => !selected.includes(m))))
        .catch(() => setSuggestions([]))
    }, 250)
    return () => clearTimeout(t)
  }, [input, selected])

  function pick(merchant) {
    onAdd(merchant)
    setInput('')
    setSuggestions([])
    setOpen(false)
  }

  return (
    <div className="space-y-2">
      {/* Selected merchant tags */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((m, i) => (
            <span
              key={m}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium text-white"
              style={{ backgroundColor: MERCHANT_LINE_COLORS[i % MERCHANT_LINE_COLORS.length] }}
            >
              {m}
              <button
                onClick={() => onRemove(m)}
                className="ml-0.5 hover:opacity-70 leading-none"
                aria-label={`Remove ${m}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Search input */}
      <div className="relative w-64" ref={ref}>
        <input
          type="text"
          value={input}
          onChange={e => { setInput(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder="Search merchant…"
          className="w-full text-sm border border-gray-300 rounded-md px-3 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {open && suggestions.length > 0 && (
          <ul className="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-52 overflow-auto">
            {suggestions.map(m => (
              <li
                key={m}
                onMouseDown={() => pick(m)}
                className="px-3 py-2 text-sm cursor-pointer hover:bg-blue-50 hover:text-blue-700"
              >
                {m}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// --- Main chart component ---
export default function SpendLineChart({ apiSuffix }) {
  const { data: summaryData, loading, error } = useApi('/api/summary/monthly' + apiSuffix)

  const [selectedCats,      setSelectedCats]      = useState([])
  const [selectedMerchants, setSelectedMerchants] = useState([])
  const [merchantData,      setMerchantData]      = useState({}) // { merchant: [{ym, total_aed}] }

  // Clear merchant monthly cache when period changes
  useEffect(() => { setMerchantData({}) }, [apiSuffix])

  // Fetch per-merchant monthly data for each selected merchant
  useEffect(() => {
    selectedMerchants.forEach(merchant => {
      if (merchantData[merchant]) return // already loaded for this period
      const qs = apiSuffix
        ? `${apiSuffix}&merchant=${encodeURIComponent(merchant)}`
        : `?merchant=${encodeURIComponent(merchant)}`
      fetch(`/api/summary/merchant-monthly${qs}`)
        .then(r => r.json())
        .then(j => setMerchantData(prev => ({ ...prev, [merchant]: j.months })))
        .catch(() => {})
    })
  }, [selectedMerchants, apiSuffix]) // eslint-disable-line react-hooks/exhaustive-deps

  function toggleCat(cat) {
    setSelectedCats(prev =>
      prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
    )
  }

  function addMerchant(m) {
    if (!selectedMerchants.includes(m)) setSelectedMerchants(prev => [...prev, m])
  }

  function removeMerchant(m) {
    setSelectedMerchants(prev => prev.filter(x => x !== m))
    setMerchantData(prev => { const n = { ...prev }; delete n[m]; return n })
  }

  // Build chart data: one object per month, each selected item as a key
  const chartData = useMemo(() => {
    if (!summaryData) return []

    const showTotal = selectedCats.length === 0 && selectedMerchants.length === 0

    return summaryData.months.map(m => {
      const row = { ym: `${m.year.slice(2)}-${m.month}` }

      if (showTotal) {
        row.total = m.total
      } else {
        selectedCats.forEach(cat => {
          row[cat] = m.categories[cat] || 0
        })
        selectedMerchants.forEach(merchant => {
          const hit = (merchantData[merchant] || []).find(r => r.ym === `${m.year}-${m.month}`)
          row[merchant] = hit?.total_aed || 0
        })
      }
      return row
    })
  }, [summaryData, selectedCats, selectedMerchants, merchantData])

  // Line definitions
  const lines = useMemo(() => {
    if (selectedCats.length === 0 && selectedMerchants.length === 0) {
      return [{ key: 'total', label: 'Total', color: '#3b82f6', dash: false }]
    }
    return [
      ...selectedCats.map(cat => ({
        key: cat,
        label: cat.replace(/_/g, ' '),
        color: CATEGORY_COLORS[cat],
        dash: false,
      })),
      ...selectedMerchants.map((m, i) => ({
        key: m,
        label: m,
        color: MERCHANT_LINE_COLORS[i % MERCHANT_LINE_COLORS.length],
        dash: true, // dashed lines to visually distinguish merchants from categories
      })),
    ]
  }, [selectedCats, selectedMerchants])

  if (loading) return <div className="h-80 bg-gray-100 animate-pulse rounded-lg" />
  if (error)   return <p className="text-red-500 text-sm">{error}</p>

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Spend Over Time</h3>

      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="ym" tick={{ fontSize: 11 }} />
          <YAxis
            tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}
            tick={{ fontSize: 11 }}
            width={40}
          />
          <Tooltip formatter={(value, name) => [fmtAED(value), name.replace(/_/g, ' ')]} />
          <Legend formatter={name => name.replace(/_/g, ' ')} />
          {lines.map(l => (
            <Line
              key={l.key}
              type="monotone"
              dataKey={l.key}
              name={l.label}
              stroke={l.color}
              strokeWidth={2}
              strokeDasharray={l.dash ? '5 3' : undefined}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>

      {/* Filters */}
      <div className="mt-5 pt-4 border-t border-gray-100 space-y-4">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
            Filter by category
          </p>
          <CategoryPills selected={selectedCats} onToggle={toggleCat} />
        </div>
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
            Filter by merchant
          </p>
          <MerchantSearch
            selected={selectedMerchants}
            onAdd={addMerchant}
            onRemove={removeMerchant}
          />
        </div>
      </div>
    </div>
  )
}
