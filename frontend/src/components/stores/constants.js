// Mirrors backend/apps/stores/models.py — keep in sync.
export const GRN_STATUSES = [['draft', 'Draft'], ['received', 'Awaiting inspection'], ['inspected', 'Inspected']]
export const RESULTS = [['pending', 'Not inspected'], ['passed', 'Passed'], ['partial', 'Partly rejected'], ['failed', 'Rejected']]
export const ALLOC_STATUSES = [['active', 'Allocated'], ['issued', 'Issued'], ['released', 'Released']]
export const MOVEMENT_TYPES = [['receipt', 'Receipt (GRN)'], ['issue', 'Issue to production'], ['adjustment', 'Adjustment']]
