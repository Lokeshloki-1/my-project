// Choice lists mirrored from backend/apps/buyers/models.py — keep them in sync.
export const opts = (pairs) => pairs.map(([value, label]) => ({ value, label }))
export const labelOf = (pairs, value) => pairs.find(([v]) => v === value)?.[1] ?? value ?? '—'

export const BUYER_STATUSES = [
  ['registered', 'Registered'],
  ['pending_credit', 'Pending credit check'],
  ['credit_failed', 'Credit failed'],
  ['pending_approval', 'Pending approval'],
  ['approved', 'Approved'],
  ['rejected', 'Rejected'],
]
export const ENQUIRY_STATUSES = [['new', 'New'], ['qualified', 'Qualified'], ['converted', 'Converted'], ['rejected', 'Rejected']]
export const SOURCES = [
  ['email', 'Email'], ['website', 'Website'], ['trade_fair', 'Trade fair'],
  ['agent', 'Buying agent'], ['referral', 'Referral'], ['other', 'Other'],
]
export const BUYER_TYPES = [
  ['brand', 'Brand'], ['retailer', 'Retailer'], ['importer', 'Importer'],
  ['wholesaler', 'Wholesaler'], ['buying_agent', 'Buying agent'],
]
export const INCOTERMS = [['EXW', 'EXW – Ex works'], ['FOB', 'FOB – Free on board'], ['CIF', 'CIF – Cost, insurance & freight'], ['DDP', 'DDP – Delivered duty paid']]
export const DEPARTMENTS = [
  ['merchandising', 'Merchandising'], ['sourcing', 'Sourcing'], ['qa', 'Quality assurance'],
  ['accounts', 'Accounts'], ['logistics', 'Logistics'], ['management', 'Management'],
]
export const CATEGORIES = [
  ['knits', 'Knits'], ['wovens', 'Wovens'], ['denim', 'Denim'], ['activewear', 'Activewear'],
  ['innerwear', 'Innerwear'], ['kidswear', 'Kidswear'], ['home_textiles', 'Home textiles'],
  ['fabric', 'Fabric'], ['yarn', 'Yarn'],
]
export const CERTIFICATIONS = [
  ['GOTS', 'GOTS'], ['OEKO-TEX', 'OEKO-TEX'], ['BSCI', 'amfori BSCI'], ['SEDEX', 'SEDEX / SMETA'],
  ['WRAP', 'WRAP'], ['GRS', 'GRS'], ['OCS', 'OCS'], ['BCI', 'Better Cotton'], ['ISO 9001', 'ISO 9001'],
]
export const PAYMENT_TERMS = [
  ['advance', '100% advance'], ['lc_sight', 'LC at sight'], ['lc_usance', 'LC usance'],
  ['tt_30', 'TT 30 days'], ['tt_60', 'TT 60 days'], ['tt_90', 'TT 90 days'],
  ['da', 'DA (documents against acceptance)'], ['dp', 'DP (documents against payment)'],
]
export const RISKS = [['low', 'Low'], ['medium', 'Medium'], ['high', 'High']]

export const fmtDate = (v) => (v ? new Date(v).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—')
export const fmtDateTime = (v) => (v ? new Date(v).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—')
export const fmtAmount = (v, currency) => (v == null || v === '' ? '—' : `${currency || ''} ${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`.trim())

// Which tab of the buyer page completes each onboarding step.
export const STEP_TAB = {
  enquiry: 'profile', registration: 'profile', profile: 'profile', contacts: 'contacts',
  requirements: 'requirements', credit: 'credit', approval: 'timeline',
}
export const firstOpenTab = (buyer) => {
  const next = buyer.onboarding.find((s) => !s.done && !s.optional)
  return next ? STEP_TAB[next.key] : 'profile'
}
