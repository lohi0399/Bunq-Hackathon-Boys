"""
ReceiptAI — bunq Hackathon 7.0
-------------------------------
Full banking dashboard with:
  • Receipt AI    — scan receipts, auto-categorise, log to bunq, stored in DB
  • X-Ray Vision  — point camera at any item → brutal financial context overlay
  • Banking       — 2 fixed accounts (Savings + Current), payments, requests, transactions
  • Database      — SQLite; every scan and action is persisted locally

Routes:
  GET  /                    web UI
  GET  /api/status          auth status + balance + DB counts
  GET  /api/accounts        list 2 fixed accounts (auto-provision if missing)
  POST /api/accounts/init   force-create Savings + Current accounts
  POST /api/payment         send a payment
  POST /api/request-money   create RequestInquiry
  POST /api/bunqme          create bunq.me payment link
  GET  /api/transactions    list payments from bunq
  POST /api/analyze         Claude vision receipt analysis
  POST /api/log-to-bunq     log expense to bunq + save to DB
  GET  /api/receipts        list saved receipts from DB
  POST /api/xray            X-Ray Spending Vision — identify item + financial impact
  GET  /api/xray/history    list past X-Ray scans
"""

import base64
import json
import os
import secrets
import time

from dotenv import load_dotenv
from flask import (
    Flask, jsonify, redirect, render_template,
    request, url_for, flash,
)
from flask_login import (
    LoginManager, UserMixin, current_user,
    login_required, login_user, logout_user,
)

import database as db
from bunq_client import BunqClient

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)

# ── flask-login setup ─────────────────────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = "login_page"        # redirect here when not logged in
login_manager.login_message = ""               # suppress default message


class User(UserMixin):
    """Thin wrapper around our DB user dict, satisfying flask-login."""
    def __init__(self, user_dict: dict):
        self.id       = user_dict["id"]
        self.username = user_dict["username"]
        self.email    = user_dict["email"]


@login_manager.user_loader
def _load_user(user_id: str) -> User | None:
    row = db.get_user_by_id(int(user_id))
    return User(row) if row else None

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
BUNQ_CURRENCY = "EUR"

CATEGORIES = [
    "FOOD_AND_DRINK", "SHOPPING", "TRANSPORT", "ENTERTAINMENT",
    "HEALTHCARE", "UTILITIES", "TRAVEL", "OTHER",
]
CATEGORY_EMOJI = {
    "FOOD_AND_DRINK": "🍽️", "SHOPPING": "🛍️", "TRANSPORT": "🚗",
    "ENTERTAINMENT": "🎬", "HEALTHCARE": "🏥", "UTILITIES": "⚡",
    "TRAVEL": "✈️", "OTHER": "📋",
}

# Financial constants for X-Ray Vision
HOURLY_WAGE_EUR   = 18.0      # ~Dutch average post-tax
MONTHLY_SALARY_EUR = 2200.0   # ~Dutch average net/month
SP500_10Y_MULTIPLIER = 2.594  # 10% p.a. compound for 10 years

# Initialise DB on startup
db.init_db()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client() -> BunqClient:
    api_key = os.getenv("BUNQ_API_KEY", "").strip()
    if not api_key:
        api_key = BunqClient.create_sandbox_user()
    client = BunqClient(api_key=api_key, sandbox=True)
    client.authenticate()
    return client


def _handle_bunq_error(e: Exception):
    return jsonify({"error": f"bunq API error: {e}"}), 500


def _get_anthropic_client():
    import anthropic
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")
    return anthropic.Anthropic(api_key=key)


def _ensure_two_accounts(client: BunqClient) -> dict:
    """
    Guarantee exactly a 'Savings' and a 'Current' account exist.
    Returns {savings: {...}, current: {...}}.
    """
    raw = client.get(f"user/{client.user_id}/monetary-account-bank")
    accounts = {item["MonetaryAccountBank"]["description"].lower(): item["MonetaryAccountBank"]
                for item in raw if "MonetaryAccountBank" in item
                and item["MonetaryAccountBank"].get("status") == "ACTIVE"}

    def _create(name):
        resp = client.post(f"user/{client.user_id}/monetary-account-bank", {
            "currency": BUNQ_CURRENCY,
            "description": name,
        })
        new_id = resp[0]["Id"]["id"]
        acc_data = client.get(f"user/{client.user_id}/monetary-account-bank/{new_id}")
        return acc_data[0]["MonetaryAccountBank"]

    savings = accounts.get("savings") or _create("Savings")
    current = accounts.get("current") or _create("Current")
    return {"savings": savings, "current": current}


def _format_account(acc: dict) -> dict:
    ibans = [a["value"] for a in acc.get("alias", []) if a.get("type") == "IBAN"]
    balance = acc.get("balance", {})
    return {
        "id": acc.get("id"),
        "description": acc.get("description"),
        "status": acc.get("status"),
        "balance": balance.get("value", "0.00"),
        "currency": balance.get("currency", "EUR"),
        "iban": ibans[0] if ibans else None,
    }


# ── Auth pages ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user_row = db.verify_user(username, password)
        if user_row:
            login_user(User(user_row), remember=True)
            return redirect(url_for("index"))
        error = "Invalid username or password."
    return render_template("login.html", error=error, mode="login")


@app.route("/register", methods=["GET", "POST"])
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")
        if not username or not email or not password:
            error = "All fields are required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif db.get_user_by_username(username):
            error = "Username already taken."
        else:
            user_id = db.create_user(username, email, password)
            user_row = db.get_user_by_id(user_id)
            login_user(User(user_row), remember=True)
            return redirect(url_for("index"))
    return render_template("login.html", error=error, mode="register")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login_page"))


# ── UI ─────────────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("index.html", username=current_user.username)


# ── Status ─────────────────────────────────────────────────────────────────────

@app.route("/api/status")
@login_required
def api_status():
    try:
        client = _get_client()
        accs = _ensure_two_accounts(client)
        savings = _format_account(accs["savings"])
        current = _format_account(accs["current"])
        return jsonify({
            "user_id": client.user_id,
            "savings_balance": savings["balance"],
            "current_balance": current["balance"],
            "currency": BUNQ_CURRENCY,
            "receipt_count": db.count_receipts(),
        })
    except Exception as e:
        return _handle_bunq_error(e)


# ── Accounts ───────────────────────────────────────────────────────────────────

@app.route("/api/accounts", methods=["GET"])
@login_required
def api_list_accounts():
    try:
        client = _get_client()
        accs = _ensure_two_accounts(client)
        return jsonify([
            {**_format_account(accs["savings"]), "type": "savings"},
            {**_format_account(accs["current"]), "type": "current"},
        ])
    except Exception as e:
        return _handle_bunq_error(e)


@app.route("/api/accounts/init", methods=["POST"])
@login_required
def api_init_accounts():
    try:
        client = _get_client()
        accs = _ensure_two_accounts(client)
        return jsonify({
            "success": True,
            "savings": _format_account(accs["savings"]),
            "current": _format_account(accs["current"]),
        })
    except Exception as e:
        return _handle_bunq_error(e)


# ── Payments ───────────────────────────────────────────────────────────────────

@app.route("/api/payment", methods=["POST"])
@login_required
def api_make_payment():
    data = request.get_json(force=True) or {}
    amount   = data.get("amount")
    to_email = str(data.get("to_email") or "sugardaddy@bunq.com")
    to_name  = str(data.get("to_name") or "")
    description = str(data.get("description") or "Payment")[:140]
    account_type = str(data.get("account_type") or "current").lower()

    if not amount:
        return jsonify({"error": "amount is required"}), 400

    try:
        client = _get_client()
        accs = _ensure_two_accounts(client)
        account_id = accs[account_type if account_type in accs else "current"]["id"]

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
        return jsonify({"success": True, "payment_id": resp[0]["Id"]["id"]})
    except Exception as e:
        return _handle_bunq_error(e)


# ── Request money ──────────────────────────────────────────────────────────────

@app.route("/api/request-money", methods=["POST"])
@login_required
def api_request_money():
    data = request.get_json(force=True) or {}
    amount      = data.get("amount")
    from_email  = str(data.get("from_email") or "sugardaddy@bunq.com")
    from_name   = str(data.get("from_name") or "")
    description = str(data.get("description") or "Payment request")[:140]
    account_type = str(data.get("account_type") or "current").lower()

    if not amount:
        return jsonify({"error": "amount is required"}), 400

    try:
        client = _get_client()
        accs = _ensure_two_accounts(client)
        account_id = accs[account_type if account_type in accs else "current"]["id"]
        resp = client.post(f"user/{client.user_id}/monetary-account/{account_id}/request-inquiry", {
            "amount_inquired": {"value": f"{float(amount):.2f}", "currency": BUNQ_CURRENCY},
            "counterparty_alias": {"type": "EMAIL", "value": from_email, "name": from_name},
            "description": description,
            "allow_bunqme": False,
        })
        return jsonify({"success": True, "request_id": resp[0]["Id"]["id"]})
    except Exception as e:
        return _handle_bunq_error(e)


# ── bunq.me ────────────────────────────────────────────────────────────────────

@app.route("/api/bunqme", methods=["POST"])
@login_required
def api_create_bunqme():
    data = request.get_json(force=True) or {}
    amount      = data.get("amount")
    description = str(data.get("description") or "Payment link")[:140]
    account_type = str(data.get("account_type") or "current").lower()

    if not amount:
        return jsonify({"error": "amount is required"}), 400

    try:
        client = _get_client()
        accs = _ensure_two_accounts(client)
        account_id = accs[account_type if account_type in accs else "current"]["id"]
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


# ── Transactions ───────────────────────────────────────────────────────────────

@app.route("/api/transactions")
@login_required
def api_list_transactions():
    count = min(int(request.args.get("count", 20)), 200)
    account_type = request.args.get("account", "current").lower()
    try:
        client = _get_client()
        accs = _ensure_two_accounts(client)
        account_id = accs[account_type if account_type in accs else "current"]["id"]
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


# ── Receipt AI ─────────────────────────────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
@login_required
def analyze():
    if "receipt" not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    file = request.files["receipt"]
    if not file or file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    mime_type = file.content_type or "image/jpeg"
    if mime_type not in ALLOWED_MIME_TYPES:
        return jsonify({"error": f"Unsupported type: {mime_type}"}), 400

    import anthropic

    image_data = base64.standard_b64encode(file.read()).decode("utf-8")
    prompt = (
        "Analyze this receipt image and return ONLY a JSON object with:\n"
        '- "merchant": string\n'
        '- "amount": number (float)\n'
        '- "currency": string (3-letter ISO, default EUR)\n'
        f'- "category": one of {CATEGORIES}\n'
        '- "date": YYYY-MM-DD or null\n'
        '- "items": array of {"name":string,"price":float} (up to 5)\n'
        '- "description": string, max 60 chars, suitable as a bank note\n'
        "Return ONLY valid JSON, no markdown fences."
    )

    try:
        ai = _get_anthropic_client()
        message = ai.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5"),
            max_tokens=1024,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": image_data}},
                {"type": "text", "text": prompt},
            ]}],
        )
    except anthropic.AuthenticationError:
        return jsonify({"error": "Invalid ANTHROPIC_API_KEY"}), 500
    except anthropic.BadRequestError as e:
        msg = str(e)
        if "credit" in msg.lower():
            return jsonify({"error": "Anthropic account has no credits"}), 402
        return jsonify({"error": f"Anthropic error: {msg}"}), 500

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        s, e2 = raw.find("{"), raw.rfind("}") + 1
        if s == -1 or e2 == 0:
            return jsonify({"error": "AI returned unexpected response"}), 500
        result = json.loads(raw[s:e2])

    result["amount"]   = float(result.get("amount") or 0)
    result["currency"] = str(result.get("currency") or "EUR").upper()
    if result.get("category") not in CATEGORIES:
        result["category"] = "OTHER"
    result["emoji"] = CATEGORY_EMOJI[result["category"]]
    result["items"] = result.get("items") or []
    return jsonify(result)


@app.route("/api/log-to-bunq", methods=["POST"])
@login_required
def log_to_bunq():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    amount_raw  = float(data.get("amount") or 1.0)
    currency    = str(data.get("currency") or "EUR").upper()
    merchant    = data.get("merchant") or "Receipt"
    category    = data.get("category") or "OTHER"
    description = data.get("description") or f"{merchant} [{category}]"
    description = description[:140]
    account_type = str(data.get("account_type") or "current").lower()

    if currency != BUNQ_CURRENCY:
        description = f"[orig: {currency} {amount_raw:.2f}] {description}"[:140]

    try:
        client = _get_client()
        accs = _ensure_two_accounts(client)
        account_id = accs[account_type if account_type in accs else "current"]["id"]
        resp = client.post(
            f"user/{client.user_id}/monetary-account/{account_id}/request-inquiry",
            {
                "amount_inquired": {"value": f"{amount_raw:.2f}", "currency": BUNQ_CURRENCY},
                "counterparty_alias": {"type": "EMAIL", "value": "sugardaddy@bunq.com", "name": "Sugar Daddy"},
                "description": description,
                "allow_bunqme": False,
            },
        )
        request_id = str(resp[0].get("Id", {}).get("id", "?"))

        # Persist to local DB
        import json as _json
        receipt_id = db.save_receipt(
            merchant=merchant,
            amount=amount_raw,
            currency=currency,
            category=category,
            receipt_date=data.get("date"),
            description=description,
            bunq_request_id=request_id,
            items_json=_json.dumps(data.get("items") or []),
        )
        return jsonify({"success": True, "request_id": request_id, "receipt_db_id": receipt_id})
    except Exception as e:
        return _handle_bunq_error(e)


@app.route("/api/receipts")
@login_required
def api_list_receipts():
    limit = min(int(request.args.get("limit", 50)), 200)
    receipts = db.list_receipts(limit=limit)
    # parse items_json back to list
    for r in receipts:
        try:
            r["items"] = json.loads(r.get("items_json") or "[]")
        except Exception:
            r["items"] = []
        r.pop("items_json", None)
    return jsonify(receipts)


# ── X-Ray Spending Vision ──────────────────────────────────────────────────────

@app.route("/api/xray", methods=["POST"])
@login_required
def xray_vision():
    """
    Identify an item in the photo and return brutal financial context:
      - estimated price
      - hours of work to afford it
      - S&P 500 value in 10 years if invested instead
      - % of monthly salary
    """
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded (field: 'image')"}), 400
    file = request.files["image"]
    mime_type = file.content_type or "image/jpeg"
    if mime_type not in ALLOWED_MIME_TYPES:
        return jsonify({"error": f"Unsupported type: {mime_type}"}), 400

    import anthropic

    image_data = base64.standard_b64encode(file.read()).decode("utf-8")

    prompt = (
        "You are a financial reality-check assistant. Look at this image.\n\n"
        "1. Identify the main physical product or item visible.\n"
        "2. Estimate its typical retail price in EUR (be specific, realistic).\n\n"
        "Return ONLY a JSON object with these fields:\n"
        '  "item_name"        : string — short product name (e.g. "Nike Air Max 270")\n'
        '  "estimated_price"  : number — price in EUR as a float\n'
        '  "currency"         : "EUR"\n'
        '  "price_confidence" : "low"|"medium"|"high"\n'
        '  "description"      : string — 1-2 sentence product description\n'
        "Return ONLY valid JSON, no markdown fences, no extra text."
    )

    try:
        ai = _get_anthropic_client()
        message = ai.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5"),
            max_tokens=512,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": image_data}},
                {"type": "text", "text": prompt},
            ]}],
        )
    except anthropic.AuthenticationError:
        return jsonify({"error": "Invalid ANTHROPIC_API_KEY"}), 500
    except anthropic.BadRequestError as e:
        msg = str(e)
        if "credit" in msg.lower():
            return jsonify({"error": "Anthropic account has no credits"}), 402
        return jsonify({"error": f"Anthropic error: {msg}"}), 500

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        item_data = json.loads(raw)
    except json.JSONDecodeError:
        s, e2 = raw.find("{"), raw.rfind("}") + 1
        if s == -1 or e2 == 0:
            return jsonify({"error": "AI returned unexpected response"}), 500
        item_data = json.loads(raw[s:e2])

    price = float(item_data.get("estimated_price") or 0)
    hours_of_work = round(price / HOURLY_WAGE_EUR, 1)
    sp500_future  = round(price * SP500_10Y_MULTIPLIER, 2)
    monthly_pct   = round((price / MONTHLY_SALARY_EUR) * 100, 1)

    # Build impact messages
    impacts = []
    if hours_of_work >= 1:
        h = int(hours_of_work)
        m = int((hours_of_work - h) * 60)
        time_str = f"{h}h {m}m" if m else f"{h}h"
        impacts.append(f"You'd work {time_str} to afford this")
    impacts.append(f"Invested in S&P 500 today → €{sp500_future:,.0f} in 10 years")
    if monthly_pct >= 100:
        impacts.append(f"That's {monthly_pct:.0f}% of your monthly salary")
    elif monthly_pct >= 10:
        impacts.append(f"That's {monthly_pct:.1f}% of your monthly salary")
    else:
        impacts.append(f"Just {monthly_pct:.1f}% of your monthly salary — barely noticeable")

    result = {
        **item_data,
        "estimated_price": price,
        "hours_of_work": hours_of_work,
        "sp500_10yr": sp500_future,
        "monthly_pct": monthly_pct,
        "impacts": impacts,
    }

    # Persist to DB
    db.save_xray(
        item_name=item_data.get("item_name", "Unknown"),
        estimated_price=price,
        currency="EUR",
        hours_of_work=hours_of_work,
        sp500_10yr=sp500_future,
        monthly_pct=monthly_pct,
        ai_description=item_data.get("description", ""),
    )

    return jsonify(result)


@app.route("/api/xray/history")
@login_required
def xray_history():
    limit = min(int(request.args.get("limit", 20)), 100)
    return jsonify(db.list_xray_scans(limit=limit))


# ── Database viewer ───────────────────────────────────────────────────────────

@app.route("/db-viewer")
@login_required
def db_viewer():
    stats = db.db_stats()
    users = db.list_users()
    receipts = db.list_receipts(limit=200)
    for r in receipts:
        try:
            r["items"] = json.loads(r.get("items_json") or "[]")
        except Exception:
            r["items"] = []
        r.pop("items_json", None)
    xray_scans = db.list_xray_scans(limit=200)
    return render_template(
        "db_viewer.html",
        stats=stats,
        users=users,
        receipts=receipts,
        xray_scans=xray_scans,
        username=current_user.username,
    )


# ── Legacy aliases ─────────────────────────────────────────────────────────────

@app.route("/analyze", methods=["POST"])
@login_required
def analyze_legacy():
    return analyze()

@app.route("/log-to-bunq", methods=["POST"])
@login_required
def log_to_bunq_legacy():
    return log_to_bunq()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"\n  ReceiptAI → http://localhost:{port}\n")
    app.run(debug=True, port=port)
