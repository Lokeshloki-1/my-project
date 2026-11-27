"""
Small Razorpay API client for UPI QR codes (stdlib only, no SDK needed).

Docs: https://razorpay.com/docs/api/qr-codes/
  - amounts are in paise (₹1 = 100)
  - a single_use QR must have fixed_amount=true and closes 2 minutes to 2 hours after creation
  - webhooks are signed: X-Razorpay-Signature = HMAC-SHA256(raw body, webhook secret), hex
"""

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request

from django.conf import settings

TIMEOUT_SECONDS = 15


class RazorpayError(Exception):
    """Razorpay rejected the request or could not be reached."""


def is_configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def _request(method, path, body=None):
    if not is_configured():
        raise RazorpayError("Razorpay is not set up. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to backend/.env.")
    token = base64.b64encode(f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()).decode()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{settings.RAZORPAY_API_BASE}{path}", data=data, method=method,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("error", {}).get("description")
        except ValueError:
            detail = None
        raise RazorpayError(f"Razorpay error ({exc.code}): {detail or exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RazorpayError(f"Could not reach Razorpay: {exc}") from exc


def create_upi_qr(*, amount_paise, name, description, close_by, notes):
    return _request("POST", "/payments/qr_codes", {
        "type": "upi_qr",
        "name": name[:100],
        "usage": "single_use",
        "fixed_amount": True,
        "payment_amount": amount_paise,
        "description": description[:255],
        "close_by": close_by,
        "notes": notes,
    })


def close_qr(qr_id):
    return _request("POST", f"/payments/qr_codes/{qr_id}/close")


def fetch_qr_payments(qr_id):
    return _request("GET", f"/payments/qr_codes/{qr_id}/payments").get("items", [])


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
