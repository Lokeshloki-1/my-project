// Mirrors backend/apps/production/models.py — keep in sync.
export const WO_STATUSES = [['planned', 'Planned'], ['in_progress', 'In production'], ['completed', 'Completed'], ['cancelled', 'Cancelled']]
export const STAGES = [['cutting', 'Cutting'], ['sewing', 'Sewing'], ['finishing', 'Finishing']]
export const pcs = (v) => `${Number(v || 0).toLocaleString('en-IN')}`
export const isoDay = (d) => { const x = new Date(d); x.setMinutes(x.getMinutes() - x.getTimezoneOffset()); return x.toISOString().slice(0, 10) }
