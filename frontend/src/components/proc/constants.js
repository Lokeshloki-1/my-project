// Mirrors backend/apps/procurement/models.py — keep in sync.
export const MR_STATUSES = [['draft', 'Draft'], ['approved', 'Approved']]
export const RFQ_STATUSES = [['draft', 'Draft'], ['sent', 'Sent to suppliers'], ['awarded', 'Awarded'], ['cancelled', 'Cancelled']]
export const PO_STATUSES = [['draft', 'Draft'], ['approved', 'Approved'], ['sent', 'Sent to supplier'], ['cancelled', 'Cancelled']]
export const qty = (v, unit) => `${Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`
export const today = () => new Date().toISOString().slice(0, 10)
