"""
Buyer onboarding workflow. Every status change goes through a function here:
it locks the row, checks the transition, writes a BuyerStatusLog and logs it.

    registered ──submit──▶ pending_credit ──credit pass──▶ pending_approval ──approve──▶ approved
         ▲                     │  ▲                              │
         │               credit fail  └── submit (after fixes)   │ reject (any open status)
         │                     ▼                                 ▼
         │               credit_failed                        rejected
         └──────────────── reopen (manager) ◀────────────────────┘
"""

import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.sales.models import Customer

from .models import Buyer, BuyerContact, BuyerEnquiry, BuyerStatusLog, CreditCheck

logger = logging.getLogger(__name__)

S = Buyer.Status
OPEN_STATUSES = [S.REGISTERED, S.PENDING_CREDIT, S.CREDIT_FAILED, S.PENDING_APPROVAL]


class Conflict(APIException):
    """The request is valid but the record is in the wrong state for it."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This action is not allowed in the record's current status."
    default_code = "invalid_transition"


def is_manager(user):
    return bool(user and user.is_authenticated and user.is_manager_or_admin)


def is_credit_reviewer(user):
    return is_manager(user) or (user and user.is_authenticated and user.role == "accountant")


# ---------------------------------------------------------------- checklist

PROFILE_FIELDS = [("address", "Address"), ("city", "City"), ("preferred_currency", "Preferred currency")]


def _latest_credit_check(buyer):
    # Uses the prefetched list when the view prefetched it (no extra query per buyer).
    checks = list(buyer.credit_checks.all())
    return max(checks, key=lambda c: (c.checked_at, c.id)) if checks else None


def _requirement(buyer):
    try:
        return buyer.requirement
    except Buyer.requirement.RelatedObjectDoesNotExist:
        return None


def onboarding_steps(buyer):
    """The seven onboarding steps with what is still missing — drives the UI stepper."""
    contacts = list(buyer.contacts.all())
    primary = next((c for c in contacts if c.is_primary), None)
    requirement = _requirement(buyer)
    credit = _latest_credit_check(buyer)

    contact_missing = []
    if not contacts:
        contact_missing.append("At least one contact")
    elif not primary:
        contact_missing.append("A primary contact")
    elif not primary.email:
        contact_missing.append("Email for the primary contact")

    req_missing = []
    if requirement is None:
        req_missing.append("Buyer requirements")
    elif not requirement.product_categories:
        req_missing.append("At least one product category")

    if buyer.status == S.CREDIT_FAILED:
        credit_missing = ["Credit check failed — fix the profile and submit again"]
    elif credit and credit.result == CreditCheck.Result.PASS and buyer.status in (S.PENDING_APPROVAL, S.APPROVED):
        credit_missing = []
    else:
        credit_missing = ["Credit check not passed yet"]

    steps = [
        {"key": "enquiry", "label": "Buyer Enquiry", "optional": True, "missing": []},
        {"key": "registration", "label": "Buyer Registration", "missing": [
            label for field, label in [("legal_name", "Legal name"), ("country", "Country")] if not getattr(buyer, field)
        ]},
        {"key": "profile", "label": "Buyer Profile", "missing": [
            label for field, label in PROFILE_FIELDS if not getattr(buyer, field)
        ]},
        {"key": "contacts", "label": "Contact Details", "missing": contact_missing},
        {"key": "requirements", "label": "Buyer Requirements", "missing": req_missing},
        {"key": "credit", "label": "Credit Verification", "missing": credit_missing},
        {"key": "approval", "label": "Buyer Approval",
         "missing": [] if buyer.status == S.APPROVED else ["Approval by a manager"]},
    ]
    for step in steps:
        step["done"] = not step["missing"]
        step.setdefault("optional", False)
    steps[0]["done"] = buyer.enquiry_id is not None
    return steps


def missing_for_submit(buyer):
    return [m for step in onboarding_steps(buyer)[1:5] for m in step["missing"]]


def allowed_actions(buyer, user):
    actions = []
    if buyer.is_editable or (is_manager(user) and buyer.status != S.REJECTED):
        actions.append("edit")
    if buyer.status in (S.REGISTERED, S.CREDIT_FAILED):
        actions.append("submit")
    if buyer.status == S.PENDING_CREDIT and is_credit_reviewer(user):
        actions.append("record_credit_check")
    if is_manager(user):
        if buyer.status == S.PENDING_APPROVAL:
            actions.append("approve")
        if buyer.status in OPEN_STATUSES:
            actions.append("reject")
        if buyer.status == S.REJECTED:
            actions.append("reopen")
    if buyer.status == S.REGISTERED:
        actions.append("delete")
    return actions


def ensure_editable(buyer, user):
    """Profile, contacts and requirements are frozen once submitted (managers may still correct them)."""
    if buyer.is_editable:
        return
    if is_manager(user) and buyer.status != S.REJECTED:
        return
    raise Conflict(f"Buyer {buyer.buyer_code} is {buyer.get_status_display().lower()} and can no longer be edited.")


# ---------------------------------------------------------------- transitions

def _lock(buyer):
    return Buyer.objects.select_for_update().get(pk=buyer.pk)


def _transition(buyer, to_status, user, note=""):
    from_status = buyer.status
    buyer.status = to_status
    BuyerStatusLog.objects.create(buyer=buyer, from_status=from_status, to_status=to_status, user=user, note=note)
    logger.info(
        "buyer_status_changed buyer=%s %s->%s user=%s", buyer.pk, from_status, to_status, getattr(user, "pk", None),
        extra={"buyer_id": buyer.pk, "from_status": from_status, "to_status": to_status, "user_id": getattr(user, "pk", None)},
    )


def log_created(buyer, user, note="Buyer registered"):
    BuyerStatusLog.objects.create(buyer=buyer, from_status="", to_status=buyer.status, user=user, note=note)


@transaction.atomic
def convert_enquiry(enquiry, user):
    """Create a registered buyer from an enquiry. Calling it again returns the same buyer."""
    enquiry = BuyerEnquiry.objects.select_for_update().get(pk=enquiry.pk)
    existing = Buyer.objects.filter(enquiry=enquiry).first()
    if existing:
        return existing, False
    if enquiry.status == BuyerEnquiry.Status.REJECTED:
        raise Conflict("A rejected enquiry cannot be converted.")

    buyer = Buyer.objects.create(
        company=enquiry.company, enquiry=enquiry, legal_name=enquiry.buyer_name,
        country=enquiry.country, notes=enquiry.notes, created_by=user,
    )
    if enquiry.contact_name and (enquiry.email or enquiry.phone):
        BuyerContact.objects.create(
            buyer=buyer, name=enquiry.contact_name, email=enquiry.email, phone=enquiry.phone, is_primary=True
        )
    enquiry.status = BuyerEnquiry.Status.CONVERTED
    enquiry.save(update_fields=["status", "updated_at"])
    log_created(buyer, user, note=f"Registered from enquiry {enquiry.enquiry_no}")
    return buyer, True


@transaction.atomic
def reject_enquiry(enquiry, user, reason):
    enquiry = BuyerEnquiry.objects.select_for_update().get(pk=enquiry.pk)
    if enquiry.status == BuyerEnquiry.Status.CONVERTED:
        raise Conflict("This enquiry is already converted to a buyer.")
    if not reason:
        raise ValidationError({"reason": "Give a reason for rejecting."})
    enquiry.status = BuyerEnquiry.Status.REJECTED
    enquiry.reject_reason = reason
    enquiry.save(update_fields=["status", "reject_reason", "updated_at"])
    return enquiry


@transaction.atomic
def submit_buyer(buyer, user):
    buyer = _lock(buyer)
    if buyer.status not in (S.REGISTERED, S.CREDIT_FAILED):
        raise Conflict(f"Only registered buyers can be submitted; this one is {buyer.get_status_display().lower()}.")
    missing = missing_for_submit(buyer)
    if missing:
        raise ValidationError({"missing": missing, "detail": "Complete these steps before submitting for the credit check."})
    _transition(buyer, S.PENDING_CREDIT, user, note="Submitted for credit check")
    buyer.save(update_fields=["status", "updated_at"])
    return buyer


@transaction.atomic
def record_credit_check(buyer, user, **data):
    if not is_credit_reviewer(user):
        raise PermissionDenied("Only accountants, managers and admins can record credit checks.")
    buyer = _lock(buyer)
    if buyer.status != S.PENDING_CREDIT:
        raise Conflict(f"Credit can only be checked for buyers pending credit; this one is {buyer.get_status_display().lower()}.")
    check = CreditCheck.objects.create(buyer=buyer, checked_by=user, **data)
    passed = check.result == CreditCheck.Result.PASS
    note = f"Credit {check.get_result_display().lower()}: {check.get_payment_terms_display()}, " \
           f"limit {check.approved_limit} {check.currency}, risk {check.risk_rating}"
    _transition(buyer, S.PENDING_APPROVAL if passed else S.CREDIT_FAILED, user, note=note)
    buyer.save(update_fields=["status", "updated_at"])
    return check


@transaction.atomic
def approve_buyer(buyer, user, note=""):
    """Approve and create the sales Customer. Approving an approved buyer changes nothing."""
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can approve buyers.")
    buyer = _lock(buyer)
    if buyer.status == S.APPROVED:
        return buyer
    if buyer.status != S.PENDING_APPROVAL:
        raise Conflict(f"Only buyers pending approval can be approved; this one is {buyer.get_status_display().lower()}.")
    latest = buyer.credit_checks.latest()
    if latest.result != CreditCheck.Result.PASS:
        raise Conflict("The latest credit check did not pass.")

    primary = buyer.contacts.filter(is_primary=True).first()
    buyer.customer = Customer.objects.create(
        company=buyer.company, name=buyer.legal_name, email=getattr(primary, "email", ""),
        phone=getattr(primary, "phone", ""), tax_id=buyer.tax_id, address=buyer.address,
        city=buyer.city, country=buyer.country,
    )
    buyer.approved_by = user
    buyer.approved_at = timezone.now()
    _transition(buyer, S.APPROVED, user, note=note or "Approved")
    buyer.save(update_fields=["status", "customer", "approved_by", "approved_at", "updated_at"])
    return buyer


@transaction.atomic
def reject_buyer(buyer, user, reason):
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can reject buyers.")
    if not reason:
        raise ValidationError({"reason": "Give a reason for rejecting."})
    buyer = _lock(buyer)
    if buyer.status not in OPEN_STATUSES:
        raise Conflict(f"A buyer that is {buyer.get_status_display().lower()} cannot be rejected.")
    buyer.rejection_reason = reason
    _transition(buyer, S.REJECTED, user, note=reason)
    buyer.save(update_fields=["status", "rejection_reason", "updated_at"])
    return buyer


@transaction.atomic
def reopen_buyer(buyer, user, note=""):
    if not is_manager(user):
        raise PermissionDenied("Only managers and admins can reopen buyers.")
    buyer = _lock(buyer)
    if buyer.status != S.REJECTED:
        raise Conflict("Only rejected buyers can be reopened.")
    buyer.rejection_reason = ""
    _transition(buyer, S.REGISTERED, user, note=note or "Reopened")
    buyer.save(update_fields=["status", "rejection_reason", "updated_at"])
    return buyer
