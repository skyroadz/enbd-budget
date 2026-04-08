import { useState } from 'react'
import { useApi } from '../hooks/useApi'

function StatRow({ label, value }) {
  return (
    <div className="flex justify-between py-1.5 border-b border-gray-100 last:border-0">
      <span className="text-sm text-gray-600">{label}</span>
      <span className="text-sm font-medium text-gray-900">{value}</span>
    </div>
  )
}

function CategoryTable({ categories }) {
  if (!categories) return null
  const rows = Object.entries(categories).sort((a, b) => a[0].localeCompare(b[0]))
  return (
    <table className="w-full text-xs mt-3">
      <thead>
        <tr className="text-left text-gray-400 uppercase">
          <th className="pb-1 font-medium">Category</th>
          <th className="pb-1 font-medium text-right">Precision</th>
          <th className="pb-1 font-medium text-right">Recall</th>
          <th className="pb-1 font-medium text-right">F1</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-50">
        {rows.map(([cat, s]) => (
          <tr key={cat}>
            <td className="py-1 text-gray-700">{cat.replace(/_/g, ' ')}</td>
            <td className="py-1 text-right tabular-nums">{(s.precision * 100).toFixed(0)}%</td>
            <td className="py-1 text-right tabular-nums">{(s.recall * 100).toFixed(0)}%</td>
            <td className={`py-1 text-right tabular-nums font-medium ${s.f1 >= 0.8 ? 'text-emerald-600' : s.f1 >= 0.5 ? 'text-amber-600' : 'text-red-500'}`}>
              {(s.f1 * 100).toFixed(0)}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const CATEGORIES = [
  'car','coffee','dining','entertainment','finance_fees',
  'food_delivery','fuel','government','groceries','hairdresser','healthcare',
  'housekeeping','parking_tolls','services','shopping','subscriptions',
  'taxi','transport','travel','utilities',
]

export default function AdminPage() {
  const { data: uncatData, loading: uncatLoading, refetch: refetchUncat } = useApi('/admin/uncategorized')

  const [retrainState, setRetrainState] = useState('idle') // idle | running | done | error
  const [retrainResult, setRetrainResult] = useState(null)
  const [retrainError, setRetrainError] = useState(null)

  const [recatState, setRecatState] = useState('idle')
  const [recatResult, setRecatResult] = useState(null)
  const [unlockState, setUnlockState] = useState('idle')
  const [unlockResult, setUnlockResult] = useState(null)

  const [rowSelections, setRowSelections] = useState({})  // {merchant: category}
  const [rowSaving, setRowSaving]         = useState({})  // {merchant: bool}
  const [rowSaved, setRowSaved]           = useState({})  // {merchant: bool}

  const [auditState, setAuditState] = useState('idle')
  const [auditResult, setAuditResult] = useState(null)
  const [auditTab, setAuditTab] = useState('wrong')

  const [overrideMerchant, setOverrideMerchant] = useState('')
  const [overrideCategory, setOverrideCategory] = useState('')
  const [overrideState, setOverrideState] = useState('idle') // idle | saving | done | error
  const [overrideResult, setOverrideResult] = useState(null)

  function handleRetrain() {
    setRetrainState('running')
    setRetrainResult(null)
    setRetrainError(null)
    fetch('/admin/retrain', { method: 'POST' })
      .then(res => res.json().then(body => ({ ok: res.ok, body })))
      .then(({ ok, body }) => {
        if (ok) {
          setRetrainResult(body)
          setRetrainState('done')
        } else {
          setRetrainError(body?.detail ?? 'Unknown error')
          setRetrainState('error')
        }
      })
      .catch(err => {
        setRetrainError(err.message)
        setRetrainState('error')
      })
  }

  function handleAudit() {
    setAuditState('running')
    setAuditResult(null)
    fetch('/admin/audit-rules')
      .then(r => r.json())
      .then(body => { setAuditResult(body); setAuditState('done') })
      .catch(() => setAuditState('error'))
  }

  function handleApplyCategory(merchant, category) {
    setRowSaving(s => ({ ...s, [merchant]: true }))
    fetch('/admin/categorize-merchant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant, category }),
    })
      .then(r => r.json())
      .then(() => {
        setRowSaving(s => ({ ...s, [merchant]: false }))
        setRowSaved(s => ({ ...s, [merchant]: true }))
        refetchUncat()
      })
      .catch(() => setRowSaving(s => ({ ...s, [merchant]: false })))
  }

  async function handleUnlockAndRecategorize() {
    setUnlockState('running')
    setUnlockResult(null)
    try {
      const unlockBody = await fetch('/admin/unlock-uncategorized', { method: 'POST' }).then(r => r.json())
      setUnlockResult(unlockBody)
      const recatBody = await fetch('/admin/recategorize', { method: 'POST' }).then(r => r.json())
      setRecatResult(recatBody)
      setUnlockState('done')
      refetchUncat()
    } catch {
      setUnlockState('error')
    }
  }

  function handleOverrideMerchant() {
    if (!overrideMerchant.trim() || !overrideCategory) return
    setOverrideState('saving')
    setOverrideResult(null)
    fetch('/admin/categorize-merchant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant: overrideMerchant.trim().toUpperCase(), category: overrideCategory }),
    })
      .then(r => r.json())
      .then(body => {
        setOverrideResult(body)
        setOverrideState('done')
        setOverrideMerchant('')
        setOverrideCategory('')
        refetchUncat()
      })
      .catch(() => setOverrideState('error'))
  }

  function handleRecategorize() {
    setRecatState('running')
    setRecatResult(null)
    fetch('/admin/recategorize', { method: 'POST' })
      .then(r => r.json())
      .then(body => { setRecatResult(body); setRecatState('done') })
      .catch(() => setRecatState('error'))
  }

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-800">Admin</h2>

      {/* ML Model */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-medium text-gray-900">ML Categorisation Model</h3>
            <p className="text-sm text-gray-500 mt-0.5">
              Retrain the model using all current labeled transactions + synthetic data.
              Takes ~30 seconds. The model hot-reloads immediately — no restart needed.
            </p>
          </div>
          <button
            onClick={handleRetrain}
            disabled={retrainState === 'running'}
            className={`shrink-0 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              retrainState === 'running'
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            {retrainState === 'running' ? 'Training…' : 'Retrain Model'}
          </button>
        </div>

        {retrainState === 'running' && (
          <div className="mt-4 flex items-center gap-2 text-sm text-blue-600">
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            Training in progress…
          </div>
        )}

        {retrainState === 'error' && (
          <div className="mt-4 px-3 py-2 bg-red-50 border border-red-200 rounded text-sm text-red-700">
            {retrainError}
          </div>
        )}

        {retrainState === 'done' && retrainResult && (
          <div className="mt-4">
            <div className="grid grid-cols-4 gap-4 mb-3">
              <div className="bg-emerald-50 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-emerald-700">
                  {(retrainResult.accuracy * 100).toFixed(1)}%
                </div>
                <div className="text-xs text-emerald-600 mt-0.5">Accuracy</div>
              </div>
              <div className="bg-blue-50 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-blue-700">
                  {retrainResult.locked_merchants?.toLocaleString()}
                </div>
                <div className="text-xs text-blue-600 mt-0.5">Locked merchants</div>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-gray-700">
                  {retrainResult.db_rows?.toLocaleString()}
                </div>
                <div className="text-xs text-gray-500 mt-0.5">DB rows used</div>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-gray-700">
                  {retrainResult.combined_rows?.toLocaleString()}
                </div>
                <div className="text-xs text-gray-500 mt-0.5">Total training rows</div>
              </div>
            </div>
            <CategoryTable categories={retrainResult.categories} />
          </div>
        )}
      </div>

      {/* Recategorize */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-medium text-gray-900">Re-apply Rules</h3>
            <p className="text-sm text-gray-500 mt-0.5">
              Re-run rules.yaml + ML model over all unlocked transactions.
              Run this after retraining or after editing rules.yaml.
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={handleUnlockAndRecategorize}
              disabled={unlockState === 'running' || recatState === 'running'}
              title="Unlocks stuck rows (locked but uncategorized), then re-categorizes everything"
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                unlockState === 'running'
                  ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  : 'bg-amber-600 text-white hover:bg-amber-700'
              }`}
            >
              {unlockState === 'running' ? 'Fixing…' : 'Unlock & Re-categorize'}
            </button>
            <button
              onClick={handleRecategorize}
              disabled={recatState === 'running' || unlockState === 'running'}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                recatState === 'running'
                  ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  : 'bg-gray-800 text-white hover:bg-gray-900'
              }`}
            >
              {recatState === 'running' ? 'Running…' : 'Re-categorize All'}
            </button>
          </div>
        </div>
        {unlockState === 'done' && unlockResult && (
          <p className="mt-3 text-sm text-emerald-700">
            Unlocked {unlockResult.unlocked_rows?.toLocaleString()} stuck rows,
            updated {recatResult?.updated_rows?.toLocaleString()} transactions.
          </p>
        )}
        {unlockState === 'error' && (
          <p className="mt-3 text-sm text-red-600">Failed — check server logs.</p>
        )}
        {recatState === 'done' && recatResult && unlockState !== 'done' && (
          <p className="mt-3 text-sm text-emerald-700">
            Updated {recatResult.updated_rows?.toLocaleString()} rows.
          </p>
        )}
        {recatState === 'error' && (
          <p className="mt-3 text-sm text-red-600">Failed — check server logs.</p>
        )}
      </div>

      {/* Rules audit */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-medium text-gray-900">Rules Audit</h3>
            <p className="text-sm text-gray-500 mt-0.5">
              Compare rules.yaml against manually-corrected transactions to find wrong or missing rules.
            </p>
          </div>
          <button
            onClick={handleAudit}
            disabled={auditState === 'running'}
            className={`shrink-0 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              auditState === 'running'
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-indigo-600 text-white hover:bg-indigo-700'
            }`}
          >
            {auditState === 'running' ? 'Auditing…' : 'Run Audit'}
          </button>
        </div>

        {auditState === 'error' && (
          <p className="mt-3 text-sm text-red-600">Failed — check server logs.</p>
        )}

        {auditState === 'done' && auditResult && (
          <div className="mt-4">
            {/* Summary */}
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="bg-red-50 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-red-700">{auditResult.wrong_rule.length}</div>
                <div className="text-xs text-red-600 mt-0.5">Wrong rules</div>
              </div>
              <div className="bg-amber-50 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-amber-700">{auditResult.no_rule.length}</div>
                <div className="text-xs text-amber-600 mt-0.5">Missing rules</div>
              </div>
              <div className="bg-emerald-50 rounded-lg p-3 text-center">
                <div className="text-2xl font-bold text-emerald-700">{auditResult.correct_count}</div>
                <div className="text-xs text-emerald-600 mt-0.5">Correct</div>
              </div>
            </div>

            {/* Tab toggle */}
            <div className="flex gap-2 mb-3">
              <button
                onClick={() => setAuditTab('wrong')}
                className={`px-3 py-1 rounded text-xs font-medium ${auditTab === 'wrong' ? 'bg-red-100 text-red-700' : 'text-gray-500 hover:bg-gray-100'}`}
              >
                Wrong rules ({auditResult.wrong_rule.length})
              </button>
              <button
                onClick={() => setAuditTab('missing')}
                className={`px-3 py-1 rounded text-xs font-medium ${auditTab === 'missing' ? 'bg-amber-100 text-amber-700' : 'text-gray-500 hover:bg-gray-100'}`}
              >
                Missing rules ({auditResult.no_rule.length})
              </button>
            </div>

            {/* Table */}
            {(() => {
              const rows = auditTab === 'wrong' ? auditResult.wrong_rule : auditResult.no_rule
              if (rows.length === 0) return <p className="text-sm text-gray-400">None.</p>
              return (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-gray-400 uppercase border-b border-gray-100">
                        <th className="pb-1 font-medium">Merchant</th>
                        <th className="pb-1 font-medium text-right">Locked →</th>
                        {auditTab === 'wrong' && <th className="pb-1 font-medium text-right">Rules →</th>}
                        <th className="pb-1 font-medium text-right">Txn</th>
                        <th className="pb-1 font-medium text-right">AED</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {rows.map((r, i) => (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="py-1 font-medium text-gray-900 max-w-xs truncate">{r.merchant}</td>
                          <td className="py-1 text-right text-emerald-700 font-medium">{r.locked}</td>
                          {auditTab === 'wrong' && <td className="py-1 text-right text-red-600">{r.rule}</td>}
                          <td className="py-1 text-right tabular-nums text-gray-600">{r.txn_count}</td>
                          <td className="py-1 text-right tabular-nums text-gray-900">
                            {r.total_aed?.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            })()}
          </div>
        )}
      </div>

      {/* Override merchant */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h3 className="font-medium text-gray-900 mb-1">Override Merchant</h3>
        <p className="text-sm text-gray-500 mb-4">
          Force all transactions for a merchant to a specific category, regardless of current assignment.
        </p>
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <label className="text-xs text-gray-500 block mb-1">Merchant name (exact, uppercase)</label>
            <input
              type="text"
              value={overrideMerchant}
              onChange={e => { setOverrideMerchant(e.target.value); setOverrideState('idle') }}
              placeholder="e.g. PETZONE"
              className="w-full text-sm border border-gray-200 rounded px-3 py-1.5 text-gray-800 placeholder-gray-300"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Category</label>
            <select
              value={overrideCategory}
              onChange={e => { setOverrideCategory(e.target.value); setOverrideState('idle') }}
              className="text-sm border border-gray-200 rounded px-2 py-1.5 text-gray-700 bg-white"
            >
              <option value="">— pick —</option>
              {CATEGORIES.map(c => (
                <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>
          <button
            onClick={handleOverrideMerchant}
            disabled={!overrideMerchant.trim() || !overrideCategory || overrideState === 'saving'}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              !overrideMerchant.trim() || !overrideCategory || overrideState === 'saving'
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            {overrideState === 'saving' ? 'Saving…' : 'Apply to All'}
          </button>
        </div>
        {overrideState === 'done' && overrideResult && (
          <p className="mt-2 text-sm text-emerald-700">Updated {overrideResult.updated} transaction{overrideResult.updated !== 1 ? 's' : ''}.</p>
        )}
        {overrideState === 'error' && (
          <p className="mt-2 text-sm text-red-600">Failed — check server logs.</p>
        )}
      </div>

      {/* Uncategorized review */}
      <div className="bg-white rounded-lg border border-gray-200 p-5">
        <h3 className="font-medium text-gray-900 mb-1">Review Queue</h3>
        <p className="text-sm text-gray-500 mb-4">
          Merchants the model couldn't confidently categorise. Apply the suggestion or correct it.
        </p>
        {uncatLoading ? (
          <div className="h-32 bg-gray-100 animate-pulse rounded" />
        ) : uncatData?.uncategorized_merchants?.length === 0 ? (
          <p className="text-sm text-emerald-600">No uncategorized merchants.</p>
        ) : (
          <div className="space-y-2">
            {(uncatData?.uncategorized_merchants ?? []).map((r, i) => {
              const selected = rowSelections[r.merchant] ?? r.ml_prediction ?? ''
              const saving   = rowSaving[r.merchant]
              const saved    = rowSaved[r.merchant]
              const conf     = r.ml_prediction_confidence
              const confColor = conf == null ? 'text-gray-300'
                : conf >= 0.75 ? 'text-emerald-600'
                : conf >= 0.60 ? 'text-amber-500'
                : conf >= 0.45 ? 'text-orange-500'
                : 'text-red-500'
              return (
                <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-lg border border-gray-100 hover:bg-gray-50">
                  <div className="flex-1 min-w-0">
                    <span className="text-sm font-medium text-gray-900 truncate block">{r.merchant}</span>
                    <div className="flex items-center gap-3 mt-0.5">
                      {r.ml_prediction && (
                        <span className="text-xs text-gray-400">
                          ML: <span className="font-medium text-gray-600">{r.ml_prediction.replace(/_/g, ' ')}</span>
                        </span>
                      )}
                      <span className="text-xs text-gray-400">{r.txn_count} txn · AED {r.total_aed?.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
                    </div>
                  </div>
                  {conf != null && (
                    <span className={`text-base font-bold tabular-nums ${confColor}`}>
                      {(conf * 100).toFixed(0)}%
                    </span>
                  )}
                  <select
                    value={selected}
                    onChange={e => setRowSelections(s => ({ ...s, [r.merchant]: e.target.value }))}
                    className="text-xs border border-gray-200 rounded px-2 py-1 text-gray-700 bg-white"
                  >
                    <option value="">— pick —</option>
                    {CATEGORIES.map(c => (
                      <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>
                    ))}
                  </select>
                  <button
                    onClick={() => handleApplyCategory(r.merchant, selected)}
                    disabled={!selected || saving || saved}
                    className={`shrink-0 text-xs px-3 py-1 rounded font-medium transition-colors ${
                      saved
                        ? 'bg-emerald-100 text-emerald-700'
                        : !selected || saving
                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                        : 'bg-blue-600 text-white hover:bg-blue-700'
                    }`}
                  >
                    {saved ? '✓ Saved' : saving ? 'Saving…' : 'Apply'}
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
