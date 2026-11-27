// Mirrors backend/apps/merchandising/models.py — keep in sync.
export const COST_CATEGORIES = [
  ['fabric', 'Fabric'], ['trims', 'Trims'], ['accessories', 'Accessories'], ['print_embroidery', 'Print / embroidery'],
  ['washing', 'Washing / dyeing'], ['cmt', 'CMT (cut, make, trim)'], ['testing', 'Testing'], ['packing', 'Packing'],
  ['freight', 'Freight / logistics'], ['other', 'Other'],
]
export const COST_STATUSES = [['draft', 'Draft'], ['approved', 'Approved']]
export const QUOTE_STATUSES = [['draft', 'Draft'], ['sent', 'Sent to buyer'], ['accepted', 'Accepted'], ['rejected', 'Rejected'], ['cancelled', 'Cancelled']]
export const ORDER_STATUSES = [['draft', 'Draft'], ['confirmed', 'Confirmed'], ['cancelled', 'Cancelled']]
export const INCOTERM_CODES = ['EXW', 'FOB', 'CIF', 'DDP']

const n = (v) => Number(v) || 0

// Same formulas as CostSheet.recalculate() on the server, for a live preview while editing.
export function costSummary(sheet) {
  const lines = (sheet.lines || []).map((l) => n(l.consumption) * n(l.rate) * (1 + n(l.wastage_pct) / 100))
  const direct = lines.reduce((a, b) => a + b, 0)
  const overhead = direct * n(sheet.overhead_pct) / 100
  const total = direct + overhead
  const margin = total * n(sheet.margin_pct) / 100
  const net = total + margin
  const commissionPct = Math.min(n(sheet.commission_pct), 49.99)
  const fob = net / (1 - commissionPct / 100)
  return { lines, direct, overhead, total, margin, commission: fob - net, fob }
}

export const num = (v, digits = 2) => Number(v || 0).toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
export const money = (v, currency, digits = 2) => `${currency || ''} ${num(v, digits)}`.trim()
export const docBadge = (prefix, status, pairs) => ({ className: `badge badge-${prefix}-${status}`, label: pairs.find(([v]) => v === status)?.[1] ?? status })
