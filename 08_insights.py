"""
Tutorial 08 — Spending Insights

Fetches categorised spending insights from the bunq Insights API.
Shows a breakdown of expenses by category for a given month.

Endpoints used:
  GET /v1/user/{userId}/insights
  GET /v1/user/{userId}/insights-search
"""

import os
from datetime import datetime

from dotenv import load_dotenv

from bunq_client import BunqClient

load_dotenv()

# Month to query — defaults to current month
TODAY = datetime.today()
MONTH_START = TODAY.replace(day=1).strftime("%Y-%m-%d 00:00:00")
NEXT_MONTH = (TODAY.replace(day=28) + __import__("datetime").timedelta(days=4)).replace(day=1)
MONTH_END = NEXT_MONTH.strftime("%Y-%m-%d 00:00:00")


def main() -> None:
    api_key = os.getenv("BUNQ_API_KEY", "").strip()
    if not api_key:
        print("No BUNQ_API_KEY found — creating a sandbox user...")
        api_key = BunqClient.create_sandbox_user()
        print(f"  API key: {api_key}\n")

    client = BunqClient(api_key=api_key, sandbox=True)
    client.authenticate()
    print(f"Authenticated as user {client.user_id}\n")

    # ---- Fetch insights for current month ----
    print(f"Fetching insights for {MONTH_START} → {MONTH_END}...")
    print("-" * 70)

    try:
        insights = client.get(
            f"user/{client.user_id}/insights",
            params={
                "time_start": MONTH_START,
                "time_end": MONTH_END,
            },
        )
    except Exception as e:
        print(f"  Error fetching insights: {e}")
        insights = []

    if not insights:
        print("  No insights data returned for this period.")
        print("  (Make some transactions first, or try a past month with activity)")
    else:
        print(f"\n{'Category':<30} {'# Transactions':>15} {'Total Spent':>15}")
        print("-" * 65)
        total = 0.0
        currency = "EUR"
        for item in insights:
            ins = item.get("InsightCategory", item)
            cat_obj = ins.get("category", {})
            category = cat_obj.get("category", "UNKNOWN") if isinstance(cat_obj, dict) else str(cat_obj)
            count = ins.get("number_of_transactions", "?")
            amount_obj = ins.get("amount_total", ins.get("total_amount", {}))
            value = float(amount_obj.get("value", 0)) if isinstance(amount_obj, dict) else 0.0
            currency = amount_obj.get("currency", "EUR") if isinstance(amount_obj, dict) else "EUR"
            total += abs(value)
            print(f"  {category:<28} {str(count):>15} {f'{abs(value):.2f} {currency}':>15}")

        print("-" * 65)
        print(f"  {'TOTAL':<28} {'':>15} {f'{total:.2f} {currency}':>15}")

    # ---- Also try insights-search for more granular data ----
    print(f"\n\nSearching all categorised transactions ({MONTH_START} → {MONTH_END})...")
    print("-" * 70)

    try:
        search_results = client.get(
            f"user/{client.user_id}/insights-search",
            params={
                "time_start": MONTH_START,
                "time_end": MONTH_END,
            },
        )
    except Exception as e:
        print(f"  insights-search not available: {e}")
        search_results = []

    if not search_results:
        print("  No results from insights-search for this period.")
    else:
        print(f"\n  {'Date':<12} {'Amount':>12}  {'Category':<20} {'Description'}")
        print("-" * 70)
        for item in search_results:
            p = item.get("Payment", item.get("TransactionCategory", item))
            date = p.get("created", p.get("date", ""))[:10]
            amount_obj = p.get("amount", {})
            value = amount_obj.get("value", "?")
            curr = amount_obj.get("currency", "")
            category = p.get("category", "?")
            description = p.get("description", "")[:40]
            print(f"  {date:<12} {f'{value} {curr}':>12}  {category:<20} {description}")

        print(f"\n  {len(search_results)} transaction(s) found")


if __name__ == "__main__":
    main()
