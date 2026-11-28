"""
AQL sampling plans: single sampling, normal inspection, General Inspection Level II
(ANSI/ASQ Z1.4 / ISO 2859-1), in the simplified chart form commonly used for garments:
where the standard table has an arrow (“use the plan above/below”), the row's own sample
size is kept with acceptance number 0. Critical defects: AQL 0 → accept 0.
"""

# (upper lot size, code letter, sample size)
LOT_ROWS = [
    (8, "A", 2), (15, "B", 3), (25, "C", 5), (50, "D", 8), (90, "E", 13), (150, "F", 20), (280, "G", 32),
    (500, "H", 50), (1200, "J", 80), (3200, "K", 125), (10000, "L", 200), (35000, "M", 315),
    (150000, "N", 500), (500000, "P", 800), (None, "Q", 1250),
]

# Acceptance number per row (A…Q) for each AQL.
ACCEPT = {
    "1.5": [0, 0, 0, 0, 0, 0, 1, 2, 3, 5, 7, 10, 14, 21, 21],
    "2.5": [0, 0, 0, 0, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21],
    "4.0": [0, 0, 0, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21, 21],
    "6.5": [0, 0, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21, 21, 21],
}
AQL_CHOICES = list(ACCEPT)


def plan(lot_size, aql):
    """{'code', 'sample_size', 'accept', 'reject'} for a lot size and AQL ('0' for critical)."""
    lot_size = int(lot_size)
    if lot_size < 2:
        raise ValueError("Lot size must be at least 2.")
    idx = next(i for i, (upper, _, _) in enumerate(LOT_ROWS) if upper is None or lot_size <= upper)
    _, code, n = LOT_ROWS[idx]
    n = min(n, lot_size)
    accept = 0 if str(aql) in ("0", "0.0") else ACCEPT[str(aql)][idx]
    return {"code": code, "sample_size": n, "accept": accept, "reject": accept + 1}
