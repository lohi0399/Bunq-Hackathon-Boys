"""
ReceiptAI — bunq Hackathon 7.0
-------------------------------
Multimodal AI that sees a receipt and acts:
  1. Upload a receipt image
  2. Claude vision AI extracts merchant, amount, category, items
  3. Logs the expense to your bunq account as a payment request

Routes:
  GET  /           — web UI
  POST /analyze    — analyze receipt image with Claude vision
  POST /log-to-bunq — create a bunq RequestInquiry for the expense
"""

import base64
import json
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from bunq_client import BunqClient

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max upload

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

CATEGORIES = [
    "FOOD_AND_DRINK",
    "SHOPPING",
    "TRANSPORT",
    "ENTERTAINMENT",
    "HEALTHCARE",
    "UTILITIES",
    "TRAVEL",
    "OTHER",
]

CATEGORY_EMOJI = {
    "FOOD_AND_DRINK": "🍽️",
    "SHOPPING": "🛍️",
    "TRANSPORT": "🚗",
    "ENTERTAINMENT": "🎬",
    "HEALTHCARE": "🏥",
    "UTILITIES": "⚡",
    "TRAVEL": "✈️",
    "OTHER": "📋",
}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
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
        return jsonify({
            "error": "ANTHROPIC_API_KEY not set. Add it to your .env file:\n  ANTHROPIC_API_KEY=sk-ant-..."
        }), 500

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
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except anthropic.AuthenticationError:
        return jsonify({"error": "Invalid ANTHROPIC_API_KEY — check your .env file."}), 500
    except anthropic.BadRequestError as e:
        msg = str(e)
        if "credit balance" in msg.lower():
            return jsonify({"error": "Anthropic account has no credits. Go to platform.anthropic.com → Plans & Billing to add credits (or redeem the hackathon offer code)."}), 402
        return jsonify({"error": f"Anthropic API error: {msg}"}), 500
    except anthropic.APIError as e:
        return jsonify({"error": f"Anthropic API error: {e}"}), 500

    raw = message.content[0].text.strip()
    # Strip markdown fences if the model added them anyway
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return jsonify({"error": "AI returned an unexpected response. Please try again."}), 500
        result = json.loads(raw[start:end])

    # Validate/normalise fields
    result["amount"] = float(result.get("amount") or 0)
    result["currency"] = str(result.get("currency") or "EUR").upper()
    if result.get("category") not in CATEGORIES:
        result["category"] = "OTHER"
    result["emoji"] = CATEGORY_EMOJI[result["category"]]
    result["items"] = result.get("items") or []

    return jsonify(result)


@app.route("/log-to-bunq", methods=["POST"])
def log_to_bunq():
    """Create a bunq RequestInquiry to log the expense."""
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    api_key = os.getenv("BUNQ_API_KEY", "").strip()
    if not api_key:
        print("No BUNQ_API_KEY — creating a sandbox user for the demo...")
        api_key = BunqClient.create_sandbox_user()

    bunq = BunqClient(api_key=api_key, sandbox=True)
    bunq.authenticate()

    accounts = bunq.get(f"user/{bunq.user_id}/monetary-account-bank")
    account_id = accounts[0]["MonetaryAccountBank"]["id"]

    amount = f"{float(data.get('amount') or 1.0):.2f}"
    currency = str(data.get("currency") or "EUR").upper()
    merchant = data.get("merchant") or "Receipt"
    category = data.get("category") or "OTHER"
    description = data.get("description") or f"{merchant} [{category}]"
    # bunq description max 140 chars
    description = description[:140]

    resp = bunq.post(
        f"user/{bunq.user_id}/monetary-account/{account_id}/request-inquiry",
        {
            "amount_inquired": {"value": amount, "currency": currency},
            "counterpart_alias": {"type": "EMAIL", "value": "sugardaddy@bunq.com"},
            "description": description,
            "allow_bunqme": False,
        },
    )

    request_id = resp[0].get("Id", {}).get("id", "?")
    return jsonify({
        "success": True,
        "request_id": request_id,
        "message": f"Expense logged to bunq! Request #{request_id}",
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"\n  ReceiptAI running → http://localhost:{port}\n")
    app.run(debug=True, port=port)
