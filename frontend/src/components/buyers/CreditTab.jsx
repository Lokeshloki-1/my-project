import { useEffect, useState } from 'react'
import api, { errorMessage } from '../../api/client'
import FormField from '../FormField'
import { PAYMENT_TERMS, RISKS, fmtAmount, fmtDateTime, labelOf, opts } from './constants'

const FIELDS = [
  { name: 'requested_limit', label: 'Credit limit requested', type: 'number' },
  { name: 'approved_limit', label: 'Credit limit approved', type: 'number' },
  { name: 'currency', label: 'Currency', required: true },
  { name: 'payment_terms', label: 'Payment terms', type: 'select', options: opts(PAYMENT_TERMS), required: true },
  { name: 'risk_rating', label: 'Risk rating', type: 'select', options: opts(RISKS), required: true },
  { name: 'ecgc_cover', label: 'ECGC export credit cover in place', type: 'checkbox' },
  { name: 'bank_reference', label: 'Bank reference', type: 'textarea', full: true },
  { name: 'trade_references', label: 'Trade references', type: 'textarea', full: true },
  { name: 'remarks', label: 'Remarks', type: 'textarea', full: true },
]

export default function CreditTab({ buyer, canRecord, onRecorded }) {
  const [checks, setChecks] = useState(null)
  const [form, setForm] = useState({ currency: buyer.preferred_currency || 'USD', payment_terms: 'lc_sight', risk_rating: 'low', ecgc_cover: false })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/credit-checks/', { params: { buyer: buyer.id, page_size: 100 } })
      .then((res) => setChecks(res.data.results))
      .catch((e) => setError(errorMessage(e)))
  }, [buyer.id, buyer.status])

  const submit = async (result) => {
    setSaving(true); setError('')
    try {
      await api.post('/credit-checks/', {
        ...form, buyer: buyer.id, result,
        requested_limit: form.requested_limit || 0,
        approved_limit: result === 'fail' ? 0 : form.approved_limit || 0,
      })
      onRecorded()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      {canRecord && (
        <div className="credit-form">
          <h2>Record credit verification</h2>
          <p className="muted small">Check bank and trade references, set the limit and terms, then pass or fail. Passing sends the buyer to a manager for approval.</p>
          <form onSubmit={(e) => { e.preventDefault(); submit('pass') }}>
            <div className="form-grid">
              {FIELDS.map((f) => (
                <FormField key={f.name} field={f} value={form[f.name]} onChange={(name, v) => setForm((p) => ({ ...p, [name]: v }))} />
              ))}
            </div>
            {error && <div className="error">{error}</div>}
            <div className="form-actions">
              <button type="button" className="danger" disabled={saving} onClick={() => form.remarks ? submit('fail') : setError('Add remarks explaining why the credit check failed.')}>Fail credit check</button>
              <button type="submit" className="approve" disabled={saving}>Pass credit check</button>
            </div>
          </form>
        </div>
      )}

      <h2>Credit history</h2>
      {!canRecord && error && <div className="error">{error}</div>}
      {checks === null ? <div className="muted">Loading…</div> : checks.length === 0 ? (
        <div className="empty-state">
          {buyer.status === 'pending_credit' ? 'Waiting for accounts to record a credit check.' : 'No credit checks yet. Submit the buyer once profile, contacts and requirements are complete.'}
        </div>
      ) : (
        <div className="table-wrap">
          <table className="compact">
            <thead><tr><th>Date</th><th>Result</th><th className="num">Approved limit</th><th>Terms</th><th>Risk</th><th>ECGC</th><th>By</th><th>Remarks</th></tr></thead>
            <tbody>
              {checks.map((c) => (
                <tr key={c.id}>
                  <td>{fmtDateTime(c.checked_at)}</td>
                  <td><span className={`badge badge-credit-${c.result}`}>{c.result}</span></td>
                  <td className="num">{fmtAmount(c.approved_limit, c.currency)}</td>
                  <td>{labelOf(PAYMENT_TERMS, c.payment_terms)}</td>
                  <td><span className={`badge badge-risk-${c.risk_rating}`}>{c.risk_rating}</span></td>
                  <td>{c.ecgc_cover ? 'Yes' : 'No'}</td>
                  <td>{c.checked_by_name}</td>
                  <td className="wrap">{c.remarks || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
