// Mirrors backend/apps/development/models.py — keep in sync.
export const TP_STATUSES = [['draft', 'Draft'], ['released', 'Released'], ['superseded', 'Superseded']]
export const SAMPLE_TYPES = [
  ['proto', 'Proto'], ['fit', 'Fit'], ['size_set', 'Size set'], ['salesman', 'Salesman'],
  ['photo', 'Photo'], ['pp', 'PP (pre-production)'], ['top', 'TOP (top of production)'],
]
export const SAMPLE_STATUSES = [
  ['requested', 'Requested'], ['in_progress', 'In progress'], ['ready', 'Ready'], ['sent', 'Sent to buyer'],
  ['approved', 'Approved'], ['approved_with_comments', 'Approved with comments'], ['rejected', 'Rejected'],
]
export const BOM_CATEGORIES = [
  ['fabric', 'Fabric'], ['trim', 'Trim'], ['label', 'Label'], ['thread', 'Thread'],
  ['print', 'Print / embroidery'], ['packaging', 'Packaging'], ['other', 'Other'],
]
export const SIZE_PRESETS = {
  'Kids 2–12Y': ['2Y', '4Y', '6Y', '8Y', '10Y', '12Y'],
  'Adult XS–XXL': ['XS', 'S', 'M', 'L', 'XL', 'XXL'],
  'Baby 0–24M': ['0-3M', '3-6M', '6-12M', '12-18M', '18-24M'],
}
