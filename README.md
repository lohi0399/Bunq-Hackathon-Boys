# ReceiptAI — bunq Hackathon 7.0

A multimodal AI web app that scans receipts and logs expenses directly to your bunq account.

**Upload a receipt photo → Claude AI extracts merchant, amount, category, and line items → one click logs it as a payment in bunq.**

Built for [bunq Hackathon 7.0 — Multimodal AI](https://bunq-hackathon-7-0.devpost.com/).

---

## What it does

1. You drag and drop (or upload) a photo of any receipt
2. Claude's vision AI reads it and extracts: merchant name, total amount, currency, category, date, and individual items
3. You review the result and optionally edit the payment note
4. Click **Log to bunq** — it creates a real payment request in your bunq account

---

## Prerequisites

- Python 3.10 or newer
- A free [Anthropic account](https://platform.anthropic.com) with API credits
- That's it — the app auto-creates a bunq sandbox account for you

---

## Step-by-step setup

### 1. Clone the repo

```bash
git clone https://github.com/lohi0399/Bunq-Hackathon-Boys.git
cd Bunq-Hackathon-Boys
git checkout receipt-ai
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Get your API keys

**Anthropic (Claude AI) — required**

1. Sign up at [platform.anthropic.com](https://platform.anthropic.com)
2. Go to **API Keys** → create a new key (starts with `sk-ant-...`)
3. Add credits under **Plans & Billing** (even $5 is enough for demos)

**bunq sandbox — optional (auto-created if you skip this)**

Run this to generate a free sandbox key instantly:
```bash
python -c "from bunq_client import BunqClient; print(BunqClient.create_sandbox_user())"
```
This prints a key like `sandbox_abc123...` — copy it.

### 4. Create your `.env` file

Create a file called `.env` in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
BUNQ_API_KEY=sandbox_...
```

> If you skip `BUNQ_API_KEY`, the app will auto-create a sandbox user each time — fine for demos.

### 5. Run the app

```bash
python app.py
```

You should see:
```
  ReceiptAI running → http://localhost:5000
```

### 6. Open it in your browser

Go to **[http://localhost:5000](http://localhost:5000)**

- Drag and drop a receipt image (JPG, PNG, or WebP)
- Click **Analyse with Claude AI**
- Review the extracted details
- Click **Log to bunq** to record the expense

---

## Project structure

```
├── app.py                  ← Flask backend (Claude vision + bunq API)
├── templates/
│   └── index.html          ← Web UI (drag-drop, results, bunq logging)
├── bunq_client.py          ← Shared bunq API client (auth + signing)
├── requirements.txt        ← Python dependencies
├── .env                    ← Your API keys (never committed)
└── 01_authentication.py    ← bunq auth tutorial (standalone)
```

## Tech stack

| Layer | Technology |
|---|---|
| AI vision | Anthropic Claude (claude-opus-4-5) |
| Banking API | bunq sandbox API |
| Backend | Python / Flask |
| Frontend | Vanilla HTML/CSS/JS |

---

## Where to see logged expenses in bunq

After clicking **Log to bunq**, the expense is created as a payment request in your sandbox account. You can view it in two ways:

**Option 1 — bunq web app**
1. Go to [web.bunq.com](https://web.bunq.com)
2. Log in with your sandbox credentials (the email bunq sent when your sandbox account was created)
3. Open your account → navigate to **Requests** or the transaction feed

**Option 2 — Terminal**
```bash
python 04_request_money.py
```
This lists all pending payment requests for your account.

---

## Troubleshooting

**"Anthropic account has no credits"**
→ Add credits at [platform.anthropic.com/settings/billing](https://platform.anthropic.com/settings/billing)

**"No BUNQ_API_KEY found"**
→ This is fine — the app creates a temporary sandbox user automatically. Add one to `.env` to persist across restarts.

**Port 5000 already in use**
→ Set a different port: `PORT=8080 python app.py`

**"Log to bunq" shows an error**
→ Your sandbox session may have expired. Delete `bunq_context.json` and try again — it will re-authenticate automatically.

---

## API rate limits (bunq sandbox)

| Method | Limit |
|---|---|
| GET | 3 requests / 3 seconds |
| POST | 5 requests / 3 seconds |
