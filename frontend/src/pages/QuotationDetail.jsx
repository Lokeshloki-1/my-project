import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import FormField from '../components/FormField'
import useOptions from '../components/useOptions'
import DocBadge from '../components/merch/DocBadge'
import DocLines from '../components/merch/DocLines'
import History from '../components/merch/History'
import ReasonDialog from '../components/merch/ReasonDialog'
import { INCOTERM_CODES, money } from '../components/merch/constants'
import { PAYMENT_TERMS, fmtDate, labelOf, opts } from '../components/buyers/constants'

const today = () => new Date().toISOString().slice(0, 10)

const FIELDS = [
  { name: 'quote_date', label: 'Quotation date', type: 'date', required: true },
  { name: 'valid_until', label: 'Valid until', type: 'date' },
  { name: 'currency', label: 'Currency' },
  { name: 'incoterm', label: 'Incoterm', type: 'select', options: INCOTERM_CODES.map((c) => ({ value: c, label: c })) },
  { name: 'delivery_port', label: 'Port' },
  { name: 'payment_terms', label: 'Payment terms', type: 'select', options: opts(PAYMENT_TERMS) },
  { name: 'delivery_date', label: 'Proposed ex-factory date', type: 'date' },
  { name: 'notes', label: 'Terms & notes (shown to buyer)', type: 'textarea', full: true },
]

const DIALOGS = {
  accept: { title: 'Buyer accepted this quotation?', text: 'Record the acceptance. You can then create the order confirmation.', label: 'Note, e.g. how the buyer confirmed', button: 'Mark accepted', tone: 'approve', field: 'note' },
  reject: { title: 'Buyer rejected this quotation?', label: 'Buyer’s reason', required: true, button: 'Mark rejected', tone: 'danger' },
  cancel: { title: 'Cancel this quotation?', text: 'It will no longer be offered to the buyer.', label: 'Reason', button: 'Cancel quotation', tone: 'danger' },
}

export default function QuotationDetail() {
  const { id } = useParams()
  const isNew = id === undefined
  const [query] = useSearchParams()
  const navigate = useNavigate()
  const [quote, setQuote] = useState(null)
  const [form, setForm] = useState(isNew ? { buyer: query.get('buyer') || '', quote_date: today(), lines: [] } : null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState(null)

  const apply = (data) => { setQuote(data); setForm({ ...data, lines: data.lines.map((l) => ({ ...l })) }) }
  const load = useCallback(() => {
    if (isNew) return
    api.get(`/quotations/${id}/`).then((r) => apply(r.data)).catch((e) => setError(errorMessage(e)))
  }, [id, isNew])
  useEffect(() => { load() }, [load])

  const buyers = useOptions('/buyers/', { status: 'approved' })
  const buyer = buyers.find((b) => String(b.id) === String(form?.buyer))
  const currency = form?.currency || buyer?.preferred_currency || 'USD'
  const sheets = useOptions(form?.buyer ? '/cost-sheets/' : null, form?.buyer ? { buyer: form.buyer, status: 'approved', currency } : null)

  // A new quotation started from a cost sheet gets that style as its first line.
  const preset = query.get('cost_sheet')
  const sheet = sheets.find((s) => String(s.id) === preset)
  if (isNew && sheet && form.lines.length === 0 && !form._presetDone) {
    setForm((f) => ({ ...f, _presetDone: true, lines: [{ cost_sheet: sheet.id, cost_no: sheet.cost_no, style_no: sheet.style_no, description: sheet.style_name, quantity: sheet.quantity || '', unit_price: sheet.fob_price, cost_fob_price: sheet.fob_price, cost_total_cost: sheet.total_cost }] }))
  }

  if (!form) return error ? <div className="error">{error}</div> : <div className="muted">Loading…</div>

  const can = (a) => isNew ? a === 'edit' : quote.allowed_actions.includes(a)
  const editable = can('edit')
  const set = (name, v) => setForm((f) => ({ ...f, [name]: v }))

  const save = async (e) => {
    e?.preventDefault()
    setBusy(true); setError('')
    const body = {
      ...form, currency, valid_until: form.valid_until || undefined, delivery_date: form.delivery_date || null,
      lines: form.lines.map((l) => ({ cost_sheet: l.cost_sheet, style_no: l.style_no, description: l.description, quantity: l.quantity, unit_price: l.unit_price })),
    }
    try {
      const { data } = isNew ? await api.post('/quotations/', body) : await api.put(`/quotations/${id}/`, body)
      if (isNew) navigate(`/quotations/${data.id}`, { replace: true })
      else apply(data)
      return data
    } catch (err) { setError(errorMessage(err)); return null } finally { setBusy(false) }
  }

  const act = async (action, body = {}) => {
    setBusy(true); setError('')
    try {
      const { data } = await api.post(`/quotations/${id}/${action}/`, body)
      setDialog(null)
      if (action === 'create-order') navigate(`/orders/${data.id}`)
      else apply(data)
    } catch (err) { setError(errorMessage(err)); setDialog(null) } finally { setBusy(false) }
  }
  const saveAndSend = async () => { if (await save()) act('send') }

  return (
    <>
      <div className="crumbs small"><Link to="/quotations">Quotations</Link> / {isNew ? 'New' : quote.quote_no}</div>
      <div className="page-head">
        <div>
          <h1 className="title-row">{isNew ? 'New quotation' : quote.quote_no} {!isNew && <DocBadge kind="qt" status={quote.status} />}</h1>
          {!isNew && <p className="muted"><Link to={`/buyers/${quote.buyer}`}>{quote.buyer_name}</Link> · {quote.buyer_country} · valid until {fmtDate(quote.valid_until)}{quote.is_expired && <span className="neg"> (expired)</span>}</p>}
        </div>
        <div className="actions">
          {can('cancel') && <button className="secondary" onClick={() => setDialog('cancel')} disabled={busy}>Cancel</button>}
          {can('reopen') && <button className="secondary" onClick={() => act('reopen')} disabled={busy}>Reopen for changes</button>}
          {can('reject') && <button className="secondary" onClick={() => setDialog('reject')} disabled={busy}>Buyer rejected</button>}
          {can('accept') && <button className="approve" onClick={() => setDialog('accept')} disabled={busy}>Buyer accepted</button>}
          {can('send') && <button onClick={saveAndSend} disabled={busy}>Save & send to buyer</button>}
          {can('create_order') && <button onClick={() => act('create-order')} disabled={busy}>Create order confirmation →</button>}
          {can('view_order') && <Link className="button" to={`/orders/${quote.order_id}`}>Open order →</Link>}
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {quote?.status === 'sent' && <div className="notice">Sent to the buyer on {fmtDate(quote.sent_at)}. Record their answer with “Buyer accepted” or “Buyer rejected”.</div>}
      {quote?.status === 'rejected' && <div className="notice warn"><b>Rejected:</b>&nbsp;{quote.reject_reason}</div>}
      {quote?.status === 'accepted' && <div className="notice ok">Accepted on {fmtDate(quote.accepted_at)}. {quote.order_id ? 'The order confirmation has been created.' : 'Create the order confirmation when the buyer’s PO arrives.'}</div>}

      <form onSubmit={save}>
        <fieldset className="plain" disabled={!editable}>
          <div className="card">
            <h2>Buyer & terms</h2>
            <div className="form-grid">
              <FormField field={{ name: 'buyer', label: 'Approved buyer', type: 'select', required: true,
                options: buyers.map((b) => ({ value: b.id, label: `${b.legal_name} (${b.country})` })) }}
                value={form.buyer} onChange={(n, v) => setForm((f) => ({ ...f, buyer: v, lines: [], currency: undefined }))} />
              {FIELDS.map((f) => (
                <FormField key={f.name} field={f.name === 'currency' ? { ...f, label: 'Currency' } : f}
                  value={f.name === 'currency' ? currency : form[f.name]} onChange={set} />
              ))}
            </div>
            {isNew && buyers.length === 0 && <p className="muted small">No approved buyers yet. Finish buyer onboarding first.</p>}
            {isNew && <p className="muted small">Left empty: valid for 30 days; incoterm and payment terms come from the buyer’s profile and credit check.</p>}
          </div>
          <div className="card">
            <h2>Styles</h2>
            <DocLines lines={form.lines} onChange={(lines) => set('lines', lines)} editable={editable} currency={currency} sheets={form.buyer ? sheets : null} />
          </div>
        </fieldset>
        {editable && (
          <div className="form-actions sticky-actions">
            {!isNew && <span className="muted small">Total {money(quote.total_amount, quote.currency)} (saved)</span>}
            <button type="submit" disabled={busy}>{busy ? 'Saving…' : isNew ? 'Create draft' : 'Save draft'}</button>
          </div>
        )}
      </form>

      {!isNew && !editable && (
        <div className="card">
          <dl className="facts">
            <div><dt>Incoterm</dt><dd>{quote.incoterm} {quote.delivery_port}</dd></div>
            <div><dt>Payment</dt><dd>{labelOf(PAYMENT_TERMS, quote.payment_terms)}</dd></div>
            <div><dt>Ex-factory</dt><dd>{fmtDate(quote.delivery_date)}</dd></div>
            <div><dt>Total</dt><dd><b>{money(quote.total_amount, quote.currency)}</b></dd></div>
          </dl>
        </div>
      )}
      {!isNew && <History items={quote.history} />}

      {dialog && (
        <ReasonDialog {...DIALOGS[dialog]} busy={busy} onClose={() => setDialog(null)}
          onConfirm={(text) => act(dialog, { [DIALOGS[dialog].field || 'reason']: text })} />
      )}
    </>
  )
}
