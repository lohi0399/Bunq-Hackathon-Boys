# 🌀 Lenz — bunq Hackathon 7.0

> **Your AI-powered financial lens.** Point at a receipt to log it. Point at a product to know if you can afford it. Built on bunq's sandbox API and Claude's multimodal AI.

**Submission for [bunq Hackathon 7.0 — Multimodal AI](https://bunq-hackathon-7-0.devpost.com/)**  
**Branch:** `main` · **Team:** Bunq-Hackathon-Boys

---

## Table of Contents

- [The Idea](#the-idea)
- [Core Features](#core-features)
- [Demo](#demo)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Run](#setup--run)
- [API Reference](#api-reference)
- [AI Models Used](#ai-models-used)
- [bunq Integration](#bunq-integration)
- [Database Schema](#database-schema)
- [Design Decisions](#design-decisions)

---

## The Idea

Most people have no idea where their money goes. Receipts pile up, spending categories blur together, and impulse purchases go unquestioned.

**Lenz** uses multimodal AI to turn every camera interaction into a financial moment of truth:

- **Scan a receipt** → Claude reads it, categorises it, and logs the expense directly to your bunq account
- **Point at any product** → Lenz AI (powered by Claude Haiku) instantly tells you if you can afford it, how many hours of work it costs, what the S&P 500 would make of that money in 10 years, and whether you've bought something similar recently

Everything is persistent: receipts, spending categories, AI feedback, all stored locally in SQLite and visualised on a live dashboard.

---

## Core Features

### 1. Receipt AI — Multimodal Receipt Scanning
Upload or photograph any receipt. Claude's vision model extracts:
- Merchant name, total amount, currency, date
- Spending category (FOOD_AND_DRINK, SHOPPING, TRANSPORT, etc.)
- Individual line items (product name + price)

One click logs it as a payment request to your **real bunq sandbox account** via the bunq REST API. All receipts are stored in SQLite and shown on a searchable history page with a **live SVG category donut chart**.

### 2. Lenz AI : Real-Time AR Financial Guidance
Point your camera (or upload a photo) at any physical product. Claude Haiku processes the image and returns:
- **Item identification** — name, brand, category, price estimate or visible price tag
- **Affordability verdict** — can you afford it right now? (calculated from your live bunq balance, not guessed by AI)
- **Hours of work** — how long you'd need to work at the Dutch average wage (€18/hr) to buy this
- **S&P 500 opportunity cost** — what that money would be worth in 10 years if invested instead
- **Worth it verdict** — a hard yes/no with reasoning, incorporating your actual spending history from the previous month
- **Duplicate purchase warning** — automatically checks if you've bought something similar in the last 30–90 days (smart window based on product category: 90 days for electronics/appliances, 30 days for everything else)

The affordability logic is **server-side math**  we never trust the AI's opinion on whether you can afford something. We fetch your actual bunq balance and do the arithmetic ourselves.

### 3. Full Banking Dashboard
A complete view of your bunq finances:
- **Accounts** — Savings and Current accounts, auto-provisioned on first login
- **Transactions** — live feed from bunq API
- **Payments** — send money, request money, generate bunq.me links
- **Balance** — real-time from bunq API

### 4. AI Feedback System
Every AI response (Receipt AI and Lenz AI) includes a 👍/👎 feedback bar. Ratings are stored in SQLite with the Claude `message_id`, source, and context. This data could be used to fine-tune prompts or surface quality issues.

### 5. PWA — Works on Mobile
Lenz is installable as a Progressive Web App (PWA). It has a custom manifest, service worker, and branded SVG icon. The camera feature works natively on mobile — point your phone at a product and get an instant verdict.

### 6. User Accounts & Auth
Multi-user support with bcrypt password hashing. Each user has their own bunq sandbox account, receipts, and spending history. Sessions via Flask-Login.

---

## Demo

```
Desktop: http://localhost:5000
Mobile (same WiFi): http://<your-local-ip>:5000
ngrok (public): https://<tunnel>.ngrok-free.dev
```

**Quick demo flow:**
1. Register an account → bunq sandbox credentials are auto-provisioned
2. Go to **Receipt AI** → upload any receipt photo
3. Click **Analyse with Claude AI** → see extracted merchant, amount, items, category
4. Click **Log to bunq** → expense is recorded in your bunq sandbox account
5. Go to **🌀 Lenz AI** → point camera at your laptop, phone, or any product
6. Get instant: affordability, hours of work, S&P 500 opportunity cost, worth-it verdict
7. Check **History** → see all scanned receipts with the category donut chart
8. Check **Transactions** → your logged expense appears in the bunq feed

---

## Architecture

### System Diagram

![Lenz Architecture](images/image.png)

### Component Overview

```
Browser (PWA)
     │
     │  HTTP/JSON
     ▼
Flask App (app.py)
     │
     ├──▶ Anthropic Claude API
     │       • claude-opus-4-5  (Receipt AI — detailed extraction)
     │       • claude-haiku-4-5 (Lenz AI — real-time, <1s response)
     │
     ├──▶ bunq Sandbox API
     │       • Auth via HMAC-signed requests (bunq_client.py)
     │       • Auto-provision user + 2 accounts on register
     │       • Real payment requests, transactions, bunq.me links
     │
     └──▶ SQLite (receiptai.db)
             • users, receipts, ai_feedback tables
             • Persists all scans, ratings, spending history
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| AI Vision | Anthropic Claude (`claude-opus-4-5`) | Best multimodal model for receipt parsing |
| AI Real-time | Anthropic Claude (`claude-haiku-4-5`) | ~0.5s responses for live camera UX |
| Banking API | bunq Sandbox REST API | Real payment requests, accounts, transactions |
| Backend | Python 3.12 / Flask 3.x | Lightweight, fast iteration |
| Auth | Flask-Login + bcrypt | Secure multi-user sessions |
| Database | SQLite + custom ORM layer | Zero-config persistence |
| Frontend | Vanilla JS / CSS (no framework) | Fast load, no build step, works as PWA |
| PWA | Web App Manifest + Service Worker | Installable, works offline for static assets |
| Tunneling | ngrok | Mobile demo over HTTPS |

---

## Project Structure

```
Bunq-Hackathon-Boys/
├── app.py                    ← Flask app — all routes, AI calls, bunq integration
├── database.py               ← SQLite ORM — users, receipts, ai_feedback
├── bunq_client.py            ← bunq REST API client (HMAC auth, request signing)
├── requirements.txt          ← Python dependencies
├── receiptai.db              ← SQLite database (auto-created on first run)
│
├── templates/
│   ├── index.html            ← Main SPA — all pages, CSS, JS in one file
│   └── login.html            ← Login/register page (PWA meta tags)
│
├── static/
│   ├── sw.js                 ← Service worker (PWA offline caching)
│   └── icon.svg              ← Lenz branded SVG icon (L lettermark, neon gradient)
│
├── docs/
│   ├── API_REFERENCE.md      ← Full API endpoint documentation
│   └── TROUBLESHOOTING.md    ← Common issues and fixes
│
└── 01_authentication.py      ← Standalone bunq auth tutorial
    02_create_monetary_account.py
    03_list_monetary_accounts.py
    03_make_payment.py
    04_request_money.py
    05_create_bunqme_link.py
    06_list_transactions.py
    07_setup_callbacks.py
```

---

## Setup & Run

### Prerequisites
- Python 3.10+
- An [Anthropic API key](https://platform.anthropic.com) with credits
- Bunq sandbox credentials are auto-created for each user

### 1. Clone & install

```bash
git clone https://github.com/lohi0399/Bunq-Hackathon-Boys.git
cd Bunq-Hackathon-Boys
git checkout receipt-ai
pip install -r requirements.txt
```

### 2. Set environment variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-...
# Optional — auto-created per user if omitted:
# BUNQ_API_KEY=sandbox_...
```

### 3. Run

```bash
python app.py
```

Output:
```
  ┌──────────────────────────────────────────────────────────
  │  Lenz — bunq Hackathon 7.0
  ├──────────────────────────────────────────────────────────
  │  Desktop:  http://localhost:5000
  │  Mobile:   http://192.168.x.x:5000  (same WiFi)
  │  Admin DB: http://localhost:5000/admin/db
  └──────────────────────────────────────────────────────────
```

### 4. Register & go

1. Open http://localhost:5000
2. Click **Register** bunq sandbox credentials are provisioned automatically
3. You now have a Savings account + Current account in the bunq sandbox

---

## API Reference

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Main SPA (requires login) |
| `GET` | `/api/status` | Auth status, live bunq balance, DB counts |
| `POST` | `/api/analyze` | Claude vision receipt analysis |
| `POST` | `/api/log-to-bunq` | Log expense → bunq payment request + save to DB |
| `GET` | `/api/receipts` | List saved receipts from DB |
| `DELETE` | `/api/receipts/clear` | Delete all receipts for current user |
| `POST` | `/api/ar-vision` | **Lenz AI** — image → financial guidance |
| `GET` | `/api/accounts` | List bunq accounts (auto-provision if missing) |
| `POST` | `/api/accounts/init` | Force-create Savings + Current accounts |
| `GET` | `/api/transactions` | List transactions from bunq |
| `POST` | `/api/payment` | Send a payment via bunq |
| `POST` | `/api/request-money` | Create a bunq RequestInquiry |
| `POST` | `/api/bunqme` | Generate a bunq.me payment link |
| `POST` | `/api/feedback` | Submit 👍/👎 AI feedback |
| `GET` | `/admin/db` | Developer DB viewer |
| `GET` | `/manifest.json` | PWA manifest |

---

## AI Models Used

### Receipt AI  `claude-opus-4-5`
Used for thorough receipt parsing. The prompt asks Claude to return structured JSON with merchant, amount, currency, date, category, and an array of line items. We use opus here because receipt text can be blurry, rotated, or in any language.

**Prompt strategy:** We provide the full category list and emoji map so Claude outputs a valid category enum every time. Line items are parsed as `[{name, price}]` and stored as JSON in SQLite.

### Lenz AI `claude-haiku-4-5`
Used for real-time camera scanning. Haiku is ~3× faster and much cheaper than Opus, making it suitable for a motion-triggered scan loop. The prompt is carefully engineered to:
- Reject non-product images (people, animals) with a specific fallback JSON
- Extract or estimate price in EUR
- Return a structured verdict with `worth_it`, `hours_of_work`, `affordability_status`, etc.

**Server-side affordability override:** We never trust the AI's affordability judgement. After the AI responds, we fetch the user's real bunq balance and override `can_afford` and `affordability_status` with hard math:
- `balance < price` → `impossible`
- `balance - price < balance * 10%` → `tight`
- Otherwise → `comfortable`

**Monthly spending context injection:** Before calling Claude, we query the DB for the user's category spending in the previous calendar month and inject it into the prompt. Claude then factors in "you've already spent €240 on Electronics this month" when giving a verdict.

---

## bunq Integration

All banking operations go through `bunq_client.py`, which implements bunq's REST API with HMAC-SHA256 request signing.

### What we use

| Feature | bunq Endpoint |
|---|---|
| Create sandbox user | `POST /v1/sandbox-user-person` |
| List monetary accounts | `GET /v1/user/{id}/monetary-account` |
| Create account | `POST /v1/user/{id}/monetary-account-bank` |
| Send payment | `POST /v1/user/{id}/monetary-account/{id}/payment` |
| Request money | `POST /v1/user/{id}/monetary-account/{id}/request-inquiry` |
| Create bunq.me link | `POST /v1/user/{id}/bunqme-tab` |
| List transactions | `GET /v1/user/{id}/monetary-account/{id}/payment` |

### Auto-provisioning flow
When a user registers:
1. A new bunq sandbox user is created via `POST /v1/sandbox-user-person`
2. Their API key, user ID, and IBAN are stored in SQLite
3. On first dashboard load, a **Savings** and **Current** account are provisioned if they don't exist

---

## Database Schema

```sql
-- Registered users (one per bunq sandbox account)
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    iban          TEXT    NOT NULL UNIQUE,
    savings_iban  TEXT,
    current_iban  TEXT,
    bunq_api_key  TEXT    NOT NULL,
    bunq_user_id  INTEGER NOT NULL,
    created_at    TEXT    NOT NULL
);

-- Every scanned receipt
CREATE TABLE receipts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    merchant        TEXT    NOT NULL,
    amount          REAL    NOT NULL,
    currency        TEXT    NOT NULL DEFAULT 'EUR',
    category        TEXT    NOT NULL DEFAULT 'OTHER',
    receipt_date    TEXT,
    description     TEXT,
    bunq_request_id TEXT,         -- bunq payment request ID if logged
    items_json      TEXT,         -- JSON array of line items
    created_at      TEXT    NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- AI feedback (thumbs up/down on any AI response)
CREATE TABLE ai_feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    message_id   TEXT    NOT NULL,  -- Claude message ID
    source       TEXT    NOT NULL,  -- 'receipt' | 'ar'
    rating       INTEGER NOT NULL,  -- 1 = thumbs up, -1 = thumbs down
    context_json TEXT,              -- item/category/price at time of rating
    created_at   TEXT    NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## Design Decisions

**Why a single-page app in one HTML file?**  
For a hackathon, the fastest path to a polished demo is zero build tooling. The entire frontend is ~2,000 lines of vanilla JS/CSS in `index.html`. No webpack, no React, no compilation step `python app.py` and you're live.

**Why SQLite?**  
Zero ops. No Docker, no Postgres setup for judges. The DB is a single file (`receiptai.db`) that appears automatically on first run. The `database.py` layer includes schema migrations so the DB evolves gracefully.

**Why two Claude models?**  
Receipt parsing needs accuracy (blurry text, multi-language receipts, complex layouts) → `claude-opus-4-5`. Real-time camera scanning needs speed (<1s) → `claude-haiku-4-5`. Using the right model for each job gives the best UX at the lowest cost.

**Why not trust Claude for affordability?**  
Large language models can hallucinate financial facts. Telling Claude "the user has €500" and asking "can they afford this?" is unreliable. Instead, we fetch the real balance from bunq and do the math ourselves, then pass that result back to the frontend. Claude only decides *what the product is and what it costs*.

**PWA for mobile demo**  
The Lenz AI feature (point camera at products) only makes sense on mobile. Making Lenz installable as a PWA means judges can add it to their home screen and use the native camera with no app store required.