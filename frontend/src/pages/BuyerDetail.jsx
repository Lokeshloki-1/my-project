import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import api, { errorMessage } from '../api/client'
import Modal from '../components/Modal'
import BuyerStatusBadge from '../components/buyers/BuyerStatusBadge'
import ContactsTab from '../components/buyers/ContactsTab'
import CreditTab from '../components/buyers/CreditTab'
import ProfileTab from '../components/buyers/ProfileTab'
import RequirementsTab from '../components/buyers/RequirementsTab'
import Stepper from '../components/buyers/Stepper'
import TimelineTab from '../components/buyers/TimelineTab'
import { BUYER_TYPES, PAYMENT_TERMS, fmtAmount, firstOpenTab, fmtDateTime, labelOf } from '../components/buyers/constants'

const TABS = [
  ['profile', 'Profile'], ['contacts', 'Contacts'], ['requirements', 'Requirements'],
  ['credit', 'Credit'], ['timeline', 'Timeline'],
]

export default function BuyerDetail() {
  const { id } = useParams()
  const [buyer, setBuyer] = useState(null)
  const [tab, setTab] = useState(null)
  const [error, setError] = useState('')
  const [banner, setBanner] = useState('')
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState(null) // 'approve' | 'reject' | 'reopen'

  const load = useCallback(() => {
    return api.get(`/buyers/${id}/`)
      .then((res) => {
        setBuyer(res.data)
        setError('')
        // First load: open the tab of the first unfinished step. Later reloads keep the user's tab.
        setTab((current) => current ?? firstOpenTab(res.data))
      })
      .catch((e) => setError(errorMessage(e)))
  }, [id])

  useEffect(() => { load() }, [load])


  const act = async (action, body = {}) => {
    setBusy(true); setBanner('')
    try {
      const { data } = await api.post(`/buyers/${id}/${action}/`, body)
      setBuyer(data)
      setDialog(null)
      setTab(firstOpenTab(data))
    } catch (e) {
      const missing = e.response?.data?.missing
      setBanner(missing ? `Complete these first: ${missing.join(' · ')}` : errorMessage(e))
      setDialog(null)
    } finally {
      setBusy(false)
    }
  }

  if (error) return <div className="error">{error}</div>
  if (!buyer || !tab) return <div className="muted">Loading…</div>

  const can = (a) => buyer.allowed_actions.includes(a)
  const editable = can('edit')
  const refresh = () => load()

  return (
    <>
      <div className="crumbs small"><Link to="/buyers/pipeline">Buyer pipeline</Link> / {buyer.buyer_code}</div>
      <div className="page-head buyer-head">
        <div>
          <h1>{buyer.legal_name} <BuyerStatusBadge status={buyer.status} /></h1>
          <p className="muted">
            {buyer.buyer_code} · {labelOf(BUYER_TYPES, buyer.buyer_type)} · {[buyer.city, buyer.country].filter(Boolean).join(', ')}
            {buyer.enquiry_no && <> · from enquiry {buyer.enquiry_no}</>}
          </p>
        </div>
        <div className="actions">
          {can('submit') && (
            <button onClick={() => act('submit')} disabled={busy}>
              {buyer.status === 'credit_failed' ? 'Resubmit for credit check' : 'Submit for credit check'}
            </button>
          )}
          {can('record_credit_check') && <button onClick={() => setTab('credit')}>Record credit check</button>}
          {can('reject') && <button className="secondary" onClick={() => setDialog('reject')} disabled={busy}>Reject</button>}
          {can('approve') && <button className="approve" onClick={() => setDialog('approve')} disabled={busy}>Approve buyer</button>}
          {can('reopen') && <button className="secondary" onClick={() => setDialog('reopen')} disabled={busy}>Reopen</button>}
        </div>
      </div>

      {banner && <div className="error">{banner}</div>}
      <StatusNotice buyer={buyer} />

      <Stepper steps={buyer.onboarding} onSelect={setTab} />

      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'tab active' : 'tab'} onClick={() => setTab(key)}>
            {label}
            {key === 'contacts' && <span className="tab-count">{buyer.contacts.length}</span>}
          </button>
        ))}
      </div>

      <div className="card tab-panel">
        {tab === 'profile' && <ProfileTab buyer={buyer} editable={editable} onSaved={setBuyer} />}
        {tab === 'contacts' && <ContactsTab buyer={buyer} editable={editable} onChanged={refresh} />}
        {tab === 'requirements' && <RequirementsTab buyer={buyer} editable={editable} onChanged={refresh} />}
        {tab === 'credit' && <CreditTab buyer={buyer} canRecord={can('record_credit_check')} onRecorded={refresh} />}
        {tab === 'timeline' && <TimelineTab buyer={buyer} />}
      </div>

      {dialog && <ActionDialog kind={dialog} buyer={buyer} busy={busy} onClose={() => setDialog(null)} onConfirm={(reason) => act(dialog, { reason })} />}
    </>
  )
}

function StatusNotice({ buyer }) {
  const credit = buyer.latest_credit_check
  switch (buyer.status) {
    case 'pending_credit':
      return <div className="notice">Submitted. Accounts must record a credit check before a manager can approve. Profile is locked meanwhile.</div>
    case 'credit_failed':
      return <div className="notice warn">Credit check failed{credit?.remarks ? `: ${credit.remarks}` : ''}. Update the details and resubmit.</div>
    case 'pending_approval':
      return <div className="notice">Credit passed — limit {fmtAmount(credit?.approved_limit, credit?.currency)} on {labelOf(PAYMENT_TERMS, credit?.payment_terms)}. Waiting for manager approval.</div>
    case 'approved':
      return (
        <div className="notice ok">
          <span>Approved by {buyer.approved_by_name} on {fmtDateTime(buyer.approved_at)}. This buyer is now a customer and can receive quotations and orders.</span>
          <span className="actions">
            <Link to={`/tech-packs?buyer=${buyer.id}`}>Tech packs</Link>
            <Link to={`/costing?buyer=${buyer.id}`}>Cost sheets</Link>
            <Link to={`/quotations/new?buyer=${buyer.id}`}>New quotation →</Link>
          </span>
        </div>
      )
    case 'rejected':
      return <div className="notice warn"><b>Rejected:</b>&nbsp;{buyer.rejection_reason}</div>
    default:
      return null
  }
}

function ActionDialog({ kind, buyer, busy, onClose, onConfirm }) {
  const [reason, setReason] = useState('')
  const copy = {
    approve: { title: `Approve ${buyer.legal_name}?`, text: 'A customer record will be created so the team can send quotations and take orders.', button: 'Approve buyer', label: 'Note (optional)' },
    reject: { title: `Reject ${buyer.legal_name}?`, text: 'The buyer stops onboarding. A manager can reopen it later.', button: 'Reject buyer', label: 'Reason *' },
    reopen: { title: `Reopen ${buyer.legal_name}?`, text: 'The buyer goes back to Registered so the details can be corrected.', button: 'Reopen', label: 'Note (optional)' },
  }[kind]
  const needsReason = kind === 'reject'
  return (
    <Modal title={copy.title} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onConfirm(reason.trim()) }}>
        <p className="muted">{copy.text}</p>
        <label className="field" style={{ marginTop: 12 }}>
          <span>{copy.label}</span>
          <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} required={needsReason} autoFocus />
        </label>
        <div className="modal-foot">
          <span />
          <div>
            <button type="button" className="secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className={kind === 'reject' ? 'danger' : kind === 'approve' ? 'approve' : ''} disabled={busy || (needsReason && !reason.trim())}>
              {busy ? 'Working…' : copy.button}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  )
}
