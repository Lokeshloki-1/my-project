"""
The only place where stock changes. Always call these inside transaction.atomic().
"""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import StockLevel, StockMovement

# Order statuses in which the goods have left the warehouse.
STOCK_HOLDING_STATUSES = ("confirmed", "invoiced", "paid")


def _locked_level(product, warehouse):
    StockLevel.objects.get_or_create(product=product, warehouse=warehouse)
    return StockLevel.objects.select_for_update().get(product=product, warehouse=warehouse)


def move_stock(*, product, warehouse, quantity, movement_type, user=None, reference="", note="",
               unit_cost=None, sales_order=None):
    """Add (quantity > 0) or remove (quantity < 0) stock and write the ledger entry."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("move_stock must run inside transaction.atomic()")
    quantity = Decimal(quantity)
    if quantity == 0:
        raise ValidationError({"quantity": "Quantity cannot be zero."})
    if product.company_id != warehouse.company_id:
        raise ValidationError({"warehouse": f"{warehouse} belongs to a different company than {product}."})
    if not warehouse.is_active and movement_type != StockMovement.Type.SALE_RETURN:
        raise ValidationError({"warehouse": f"Warehouse {warehouse} is inactive."})

    level = _locked_level(product, warehouse)
    new_balance = level.quantity + quantity
    if new_balance < 0:
        raise ValidationError(
            f"Not enough stock of {product.name} in {warehouse.name}: "
            f"{level.quantity.normalize():f} available, {(-quantity).normalize():f} needed."
        )
    level.quantity = new_balance
    level.save(update_fields=["quantity", "updated_at"])
    return StockMovement.objects.create(
        product=product, warehouse=warehouse, movement_type=movement_type, quantity=quantity,
        balance_after=new_balance, unit_cost=unit_cost, sales_order=sales_order,
        reference=reference, note=note, created_by=user,
    )


def _order_quantities(order):
    """Total quantity per product for an order (the same product can be on two lines)."""
    totals = defaultdict(Decimal)
    products = {}
    for item in order.items.select_related("product"):
        totals[item.product_id] += item.quantity
        products[item.product_id] = item.product
    # Sorted by product id so concurrent orders lock rows in the same order (no deadlocks).
    return [(products[pid], totals[pid]) for pid in sorted(totals)]


def issue_for_order(order, user=None):
    if not order.warehouse_id:
        return
    for product, qty in _order_quantities(order):
        move_stock(product=product, warehouse=order.warehouse, quantity=-qty,
                   movement_type=StockMovement.Type.SALE, sales_order=order, reference=order.order_no or "", user=user)


def return_for_order(order, user=None):
    """Put back exactly what this order took out, according to the ledger."""
    taken = defaultdict(Decimal)
    for mv in order.stock_movements.select_related("product", "warehouse"):
        taken[(mv.product_id, mv.warehouse_id)] += mv.quantity  # sales are negative, returns positive
    movements = {(mv.product_id, mv.warehouse_id): mv for mv in order.stock_movements.all()}
    for key in sorted(taken):
        if taken[key] < 0:
            mv = movements[key]
            move_stock(product=mv.product, warehouse=mv.warehouse, quantity=-taken[key],
                       movement_type=StockMovement.Type.SALE_RETURN, sales_order=order,
                       reference=order.order_no or "", user=user)


def transfer_stock(*, product, from_warehouse, to_warehouse, quantity, user=None, reference="", note=""):
    if from_warehouse.pk == to_warehouse.pk:
        raise ValidationError({"to_warehouse": "Choose a different warehouse."})
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValidationError({"quantity": "Must be more than zero."})
    # Lock in a fixed order to avoid deadlocks between opposite transfers.
    first, second = sorted([from_warehouse, to_warehouse], key=lambda w: w.pk)
    _locked_level(product, first)
    _locked_level(product, second)
    out = move_stock(product=product, warehouse=from_warehouse, quantity=-quantity,
                     movement_type=StockMovement.Type.TRANSFER_OUT, user=user, reference=reference,
                     note=note or f"To {to_warehouse.name}")
    into = move_stock(product=product, warehouse=to_warehouse, quantity=quantity,
                      movement_type=StockMovement.Type.TRANSFER_IN, user=user, reference=reference,
                      note=note or f"From {from_warehouse.name}")
    return out, into
