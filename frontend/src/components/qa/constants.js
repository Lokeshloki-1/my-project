// Mirrors backend/apps/quality/models.py — keep in sync.
export const DEFECT_CATEGORIES = [
  ['sewing', 'Sewing'], ['fabric', 'Fabric'], ['measurement', 'Measurement'], ['finishing', 'Finishing / pressing'],
  ['print', 'Print / embroidery'], ['trims', 'Trims / labels'], ['packing', 'Packing'], ['other', 'Other'],
]
export const SEVERITIES = [['minor', 'Minor'], ['major', 'Major'], ['critical', 'Critical']]
export const FI_STATUSES = [['draft', 'Draft'], ['passed', 'Passed'], ['failed', 'Failed']]
export const RESULTS = [['green', 'Green'], ['amber', 'Amber'], ['red', 'Red']]
export const GREEN_MAX = 2.5
export const AMBER_MAX = 5
export const dhuResult = (dhu) => (dhu <= GREEN_MAX ? 'green' : dhu <= AMBER_MAX ? 'amber' : 'red')
