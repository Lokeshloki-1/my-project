// Mirrors backend/apps/finance/models.py — keep in sync.
export const INV_STATUSES = [['open', 'Open'], ['partially_paid', 'Partly paid'], ['paid', 'Paid'], ['cancelled', 'Cancelled']]
export const inr = (v) => `₹${Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
