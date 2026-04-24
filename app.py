"""
ReceiptAI — bunq Hackathon 7.0
-------------------------------
Full banking dashboard with multimodal AI receipt scanning.

Routes:
  GET  /                        — web UI
  POST /api/analyze             — analyse receipt image with Claude vision
  POST /api/log-to-bunq         — create a bunq RequestInquiry for the expense
  GET  /api/accounts            — list monetary accounts
  POST /api/accounts            — create a new monetary account
  POST /api/payment             — send a payment
  POST /api/request-money       — request money (RequestInquiry)
  POST /api/bunqme              — create a bunq.me payment link
  GET  /api/transactions        — list recent transactions
  GET  /api/status              — check auth status / user info
"""

import base64
import json
import os
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from bunq_client import BunqClient

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max upload

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

CATEGORIES = [
    "FOOD_AND_DRINK", "SHOPPING", "TRANSPORT", "ENTERTAINMENT",
    "HEALTHCARE", "UTILITIES", "TRAVEL", "OTHER",
]
CATEGORY_EMOJI = {
    "FOOD_AND_DRINK": "🍽️", "SHOPPING": "🛍️", "TRANSPORT": "🚗",
    "ENTERTAINMENT": "🎬", "HEALTHCARE": "🏥", "UTILITIES": "⚡",
    "TRAVEL": "✈️", "OTHER": "📋",
}

# bunq sandbox only supports EUR
BUNQ_CURRENCY = "EUR"


def _get_client() -> BunqClient:
    """Return an authenticated BunqClient, auto-creating a sandbox user if needed."""
    api_key = os.getenv("BUNQ_API_KEY", "").strip()
    if not api_key:
        api_key = BunqClient.create_sandbox_user()
    client = BunqClient(api_key=api_key, sandbox=True)
    client.authenticate()
    return client


def _handle_bunq_error(e: Exception):
    """Turn a bunq HTTPError into a clean JSON response."""
    msg = str(e)
    return jsonify({"error": f"bunq API error: {msg}"}), 500


# ── UI ──────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Status / auth ────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    try:
        client = _get_client()
        accounts = client.get(f"user/{client.user_id}/monetary-account-bank")
        primary = accounts[0]["MonetaryAccountBank"] if accounts else {}
        balance = primary.get("balance", {})
        return jsonify({
            "user_id": client.user_id,
            "account_count": len(accounts),
            "primary_balance": balance.get("value", "0.00"),
            "primary_currency": balance.get("currency", "EUR"),
        })
    except Exception as e:
        return _handle_bunq_error(e)


# ── Accounts ─────────────────────────────────────────────────────────────────

@app.route("/api/accounts", methods=["GET"])
def api_list_accounts():
    try:
        client = _get_client()
        raw = client.get(f"user/{client.user_id}/monetary-account-bank")
        accounts = []
        for item in raw:
            acc = item.get("MonetaryAccountBank", {})
            ibans = [a["value"] for a in acc.get("alias", []) if a.get("type") == "IBAN"]
            balance = acc.get("balance", {})
            accounts.append({
                "id": acc.get("id"),
                "description": acc.get("description"),
                "status": acc.get("status"),
                "balance": balance.get("value", "0.00"),
                "currency": balance.get("currency", "EUR"),
                "iban": ibans[0] if ibans else None,
            })
        return jsonify(accounts)
    except Exception as e:
        return _handle_bunq_error(e)


@app.route("/api/accounts", methods=["POST"])
def api_create_account():
    data = request.get_json(force=True) or {}
    description = str(data.get("description") or "New Account")[:50]
    try:
        client = _get_client()
        resp = client.post(f"user/{client.user_id}/monetary-account-bank", {
            "currency": BUNQ_CURRENCY,
            "description": description,
        })
        new_id = resp[0]["Id"]["id"]
        return jsonify({"success": True, "account_id": new_id, "description": description})
    except Exception as e:
        return _handle_bunq_error(e)


# ── Payments ─────────────────────────────────────────────────────────────────

@app.route("/api/payment", methods=["POST"])
def api_make_payment():
    data = request.get_json(force=True) or {}
    amount = data.get("amount")
    description = str(data.get("description") or "Payment")[:140]
    to_email = str(data.get("to_email") or "sugardaddy@bunq.com")
    to_name = str(data.get("to_name") or "")

    if not amount:
        return jsonify({"error": "amount is required"}), 400

    try:
        client = _get_client()
        account_id = client.get_primary_account_id()

        # Fund account from sugar daddy first if needed
        if data.get("fund_first"):
            client.post(f"user/{client.user_id}/monetary-account/{account_id}/request-inquiry", {
                "amount_inquired": {"value": "500.00", "currency": BUNQ_CURRENCY},
                "counterparty_alias": {"type": "EMAIL", "value": "sugardaddy@bunq.com", "name": "Sugar Daddy"},
                "description": "Hackathon test funds",
                "allow_bunqme": False,
            })
            time.sleep(2)

        resp = client.post(f"user/{client.user_id}/monetary-account/{account_id}/payment", {
            "amount": {"value": f"{float(amount):.2f}", "currency": BUNQ_CURRENCY},
            "counterparty_alias": {"type": "EMAIL", "value": to_email, "name": to_name},
            "description": description,
        })
        payment_id = resp[0]["Id"]["id"]
        return jsonify({"success": True, "payment_id": payment_id})
    except Exception as e:
        return _handle_bunq_error(e)


# ── Request money ─────────────────────────────────────────────────────────────

@app.route("/api/request-money", methods=["POST"])
def api_request_money():
    data = request.get_json(force=True) or {}
    amount = data.get("amount")
    description = str(data.get("description") or "Payment request")[:140]
    from_email = str(data.get("from_email") or "sugardaddy@bunq.com")
    from_name = str(data.get("from_name") or "")

    if not amount:
        return jsonify({"error": "amount is required"}), 400

    try:
        client = _get_client()
        account_id = client.get_primary_account_id()
        resp = client.post(f"user/{client.user_id}/monetary-account/{account_id}/request-inquiry", {
            "amount_inquired": {"value": f"{float(amount):.2f}", "currency": BUNQ_CURRENCY},
            "counterparty_alias": {"type": "EMAIL", "value": from_email, "name": from_name},
            "description": description,
            "allow_bunqme": False,
        })
        request_id = resp[0]["Id"]["id"]
        return jsonify({"success": True, "request_id": request_id})
    except Exception as e:
        return _handle_bunq_error(e)


# ── bunq.me ───────────────────────────────────────────────────────────────────

@app.route("/api/bunqme", methods=["POST"])
def api_create_bunqme():
    data = request.get_json(force=True) or {}
    amount = data.get("amount")
    description = str(data.get("description") or "Payment link")[:140]

    if not amount:
        return jsonify({"error": "amount is required"}), 400

    try:
        client = _get_client()
        account_id = client.get_primary_account_id()
        resp = client.post(f"user/{client.user_id}/monetary-account/{account_id}/bunqme-tab", {
            "bunqme_tab_entry": {
                "amount_inquired": {"value": f"{float(amount):.2f}", "currency": BUNQ_CURRENCY},
                "description": description,
            },
        })
        tab_id = resp[0]["Id"]["id"]
        tab_data = client.get(f"user/{client.user_id}/monetary-account/{account_id}/bunqme-tab/{tab_id}")
        tab = tab_data[0]["BunqMeTab"]
        return jsonify({
            "success": True,
            "tab_id": tab_id,
            "url": tab.get("bunqme_tab_share_url", ""),
            "status": tab.get("status"),
        })
    except Exception as e:
        return _handle_bunq_error(e)


# ── Transactions ──────────────────────────────────────────────────────────────

@app.route("/api/transactions")
def api_list_transactions():
    count = min(int(request.args.get("count", 20)), 200)
    try:
        client = _get_client()
        account_id = client.get_primary_account_id()
        raw = client.get(
            f"user/{client.user_id}/monetary-account/{account_id}/payment",
            params={"count": count},
        )
        txns = []
        for item in raw:
            p = item.get("Payment", {})
            txns.append({
                "id": p.get("id"),
                "date": p.get("created", "")[:19],
                "amount": p.get("amount", {}).get("value"),
                "currency": p.get("amount", {}).get("currency"),
                "counterparty": p.get("counterparty_alias", {}).get("display_name", "?"),
                "description": p.get("description", ""),
                "type": p.get("type"),
            })
        return jsonify(txns)
    except Exception as e:
        return _handle_bunq_error(e)


# ── Receipt AI ────────────────────────────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Analyze a receipt image using Claude vision AI."""
    if "receipt" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files["receipt"]
    if not file or file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    mime_type = file.content_type or "image/jpeg"
    if mime_type not in ALLOWED_MIME_TYPES:
        return jsonify({"error": f"Unsupported file type: {mime_type}. Use JPG, PNG, or WebP."}), 400

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not anthropic_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set in .env"}), 500

    import anthropic

    image_data = base64.standard_b64encode(file.read()).decode("utf-8")
    prompt = (
        "Analyze this receipt image carefully and return ONLY a JSON object with these exact fields:\n"
        '- "merchant": string — store or restaurant name\n'
        '- "amount": number — total amount as a float (e.g. 12.50)\n'
        '- "currency": string — 3-letter ISO code, default "EUR"\n'
        f'- "category": string — must be one of exactly: {CATEGORIES}\n'
        '- "date": string or null — format YYYY-MM-DD, or null if not visible\n'
        '- "items": array — up to 5 objects with {"name": string, "price": float}\n'
        '- "description": string — short bank transaction note, max 60 characters\n'
        "\nReturn ONLY valid JSON. No markdown fences, no explanation, no extra text."
    )

    client = anthropic.Anthropic(api_key=anthropic_key)
    try:
        message = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5"),
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": image_data}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
    except anthropic.AuthenticationError:
        return jsonify({"error": "Invalid ANTHROPIC_API_KEY — check your .env file."}), 500
    except anthropic.BadRequestError as e:
        msg = str(e)
        if "credit balance" in msg.lower():
            return jsonify({"error": "Anthropic account has no credits. Go to platform.anthropic.com → Plans & Billing."}), 402
        return jsonify({"error": f"Anthropic API error: {msg}"}), 500
    except anthropic.APIError as e:
        return jsonify({"error": f"Anthropic API error: {e}"}), 500

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start == -1 or end == 0:
            return jsonify({"error": "AI returned an unexpected response. Please try again."}), 500
        result = json.loads(raw[start:end])

    result["amount"] = float(result.get("amount") or 0)
    result["currency"] = str(result.get("currency") or "EUR").upper()
    if result.get("category") not in CATEGORIES:
        result["category"] = "OTHER"
    result["emoji"] = CATEGORY_EMOJI[result["category"]]
    result["items"] = result.get("items") or []
    return jsonify(result)


@app.route("/api/log-to-bunq", methods=["POST"])
def log_to_bunq():
    """Create a bunq RequestInquiry to log the scanned expense."""
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    amount_raw = float(data.get("amount") or 1.0)
    currency = str(data.get("currency") or "EUR").upper()
    merchant = data.get("merchant") or "Receipt"
    category = data.get("category") or "OTHER"
    description = data.get("description") or f"{merchant} [{category}]"
    description = description[:140]

    # bunq sandbox only supports EUR — preserve original currency in the note
    if currency != BUNQ_CURRENCY:
        description = f"[orig: {currency} {amount_raw:.2f}] {description}"[:140]

    try:
        client = _get_client()
        accounts = client.get(f"user/{client.user_id}/monetary-account-bank")
        account_id = accounts[0]["MonetaryAccountBank"]["id"]

        resp = client.post(
            f"user/{client.user_id}/monetary-account/{account_id}/request-inquiry",
            {
                "amount_inquired": {"value": f"{amount_raw:.2f}", "currency": BUNQ_CURRENCY},
                "counterparty_alias": {"type": "EMAIL", "value": "sugardaddy@bunq.com", "name": "Sugar Daddy"},
                "description": description,
                "allow_bunqme": False,
            },
        )
        request_id = resp[0].get("Id", {}).get("id", "?")
        return jsonify({"success": True, "request_id": request_id})
    except Exception as e:
        return _handle_bunq_error(e)


# Legacy route aliases so old frontend paths still work
@app.route("/analyze", methods=["POST"])
def analyze_legacy():
    return analyze()

@app.route("/log-to-bunq", methods=["POST"])
def log_to_bunq_legacy():
    return log_to_bunq()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"\n  ReceiptAI running → http://localhost:{port}\n")
    app.run(debug=True, port=port)

