import { useCallback, useEffect, useState } from 'react'
import api, { errorMessage } from '../api/client'
import { money } from '../utils/format'

const POLL_MS = 4000

// Shows a Razorpay UPI QR for an invoice and waits for the customer to pay it.
export default function UpiQrPanel({ invoiceId, onPaid, onClose }) {
  const [qr, setQr] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [imgFailed, setImgFailed] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  const create = useCallback(async () => {
    setBusy(true)
    setError('')
    setImgFailed(false)
    try {
      const { data } = await api.post(`/invoices/${invoiceId}/upi-qr/`)
      setQr(data)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }, [invoiceId])

  useEffect(() => { create() }, [create])

  // While the QR is waiting, ask the server (which asks Razorpay) every few seconds.
  useEffect(() => {
    if (qr?.status !== 'active') return undefined
    const poll = setInterval(async () => {
      try {
        const { data } = await api.get(`/invoices/${invoiceId}/upi-qr/`)
        setQr(data)
        if (data.status === 'paid') onPaid()
      } catch { /* keep waiting; a network blip should not close the QR */ }
    }, POLL_MS)
    const tick = setInterval(() => setNow(Date.now()), 1000)
    return () => { clearInterval(poll); clearInterval(tick) }
  }, [qr?.status, invoiceId, onPaid])

  const secondsLeft = qr ? Math.max(0, Math.floor((new Date(qr.close_by).getTime() - now) / 1000)) : 0
  const mmss = `${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, '0')}`

  return (
    <div className="upi-panel">
      {busy && !qr && <p className="muted">Creating QR code…</p>}
      {error && <div className="error">{error}</div>}
      {qr && (
        <>
          {qr.status === 'active' && (
            <div className="upi-body">
              {imgFailed ? (
                <a className="upi-link" href={qr.image_url} target="_blank" rel="noreferrer">Open the QR code</a>
              ) : (
                <img className="upi-img" src={qr.image_url} alt="UPI QR code to scan and pay" onError={() => setImgFailed(true)} />
              )}
              <div>
                <div className="upi-amount">{money(qr.amount)}</div>
                <p>Ask the customer to scan with <strong>PhonePe, Google Pay, Paytm, BHIM</strong> or any UPI app.</p>
                <p className="muted small"><span className="pulse" /> Waiting for payment… QR expires in {mmss}</p>
                <p className="muted small">The payment is recorded automatically when Razorpay confirms it.</p>
              </div>
            </div>
          )}
          {qr.status === 'paid' && <div className="upi-ok">✓ Payment of {money(qr.amount)} received and recorded.</div>}
          {qr.status === 'closed' && <p className="muted">This QR code has expired or was replaced. Make a new one if the customer still wants to pay.</p>}
          {qr.status === 'needs_review' && (
            <div className="error">Money was received but could not be applied automatically: {qr.review_note} Please check it in the Razorpay Dashboard.</div>
          )}
        </>
      )}
      <div className="modal-foot">
        <span />
        <div>
          <button type="button" className="secondary" onClick={onClose}>{qr?.status === 'paid' ? 'Done' : 'Close'}</button>
          {qr && qr.status !== 'active' && qr.status !== 'paid' && <button type="button" disabled={busy} onClick={create}>New QR code</button>}
        </div>
      </div>
    </div>
  )
}
