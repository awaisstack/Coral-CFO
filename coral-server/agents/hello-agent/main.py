import os
import logging
import math
from dotenv import load_dotenv
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List

# --- FIX: load .env from parent directory of 'agents' ---
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(dotenv_path=ENV_PATH)

print("DEBUG: Loading .env from:", ENV_PATH)
print("DEBUG: GOOGLE_API_KEY =", os.getenv("GOOGLE_API_KEY"))
# Optional Gemini import
try:
    from google import genai
    GEMINI_AVAILABLE = True
except Exception:
    GEMINI_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("cfo-agent")

# Heuristics / thresholds
OLD_THRESHOLD_DAYS = 180
HIGH_COST_FACTOR = 1.5
TOP_FOR_LLM = 10  # how many top cancellation candidates to include in a Gemini prompt

# --- CSV reading + mapping utilities -------------------------
def try_read_csv(path: str) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "latin1"]
    delimiters = [",", "\t", ";", "|"]
    last_exc = None
    for enc in encodings:
        for delim in delimiters:
            try:
                df = pd.read_csv(path, delimiter=delim, encoding=enc, engine="python")
                if df.shape[1] == 1 and delim != ",":
                    # probably wrong delimiter
                    continue
                df.columns = df.columns.astype(str).str.strip()
                return df
            except Exception as e:
                last_exc = e
    # final fallback
    try:
        df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
        df.columns = df.columns.astype(str).str.strip()
        return df
    except Exception:
        logger.error("Failed to read CSV. Last exception: %s", last_exc)
        raise

COLUMN_CANDIDATES = {
    "service": ["service", "vendor", "plan", "subscription", "description", "name"],
    "amount": ["amount", "price", "cost", "charge", "price_usd", "value"],
    "currency": ["currency", "curr"],
    "frequency": ["frequency", "freq", "billing_frequency", "period"],
    "start_date": ["start_date", "start", "date_started", "created_at"],
    "last_charge_date": ["last_charge_date", "last_charge", "last_billed", "last_payment_date"],
    "last_used_date": ["last_used_date", "last_used", "last_activity", "last_accessed", "last_seen"],
    "usage_count": ["usage_count", "uses", "count", "times_used"],
    "uses_per_month": ["uses_per_month", "uses/month", "usage_per_month", "uses_per_mo"],
    "is_automatic": ["is_automatic", "auto", "auto_renew", "automatic", "is_autorenew"],
    "category": ["category", "type", "tag"],
    "notes": ["notes", "comment", "info", "details"],
    "subscription_id": ["subscription_id", "id", "sub_id"]
}

def map_columns(df: pd.DataFrame) -> Dict[str, str]:
    found = {}
    lower_cols = {c.lower(): c for c in df.columns}
    for canonical, candidates in COLUMN_CANDIDATES.items():
        picked = None
        for cand in candidates:
            if cand.lower() in lower_cols:
                picked = lower_cols[cand.lower()]
                break
        if not picked:
            # fuzzy partial
            for col_l, col_orig in lower_cols.items():
                for cand in candidates:
                    if cand.lower() in col_l or col_l in cand.lower():
                        picked = col_orig
                        break
                if picked:
                    break
        found[canonical] = picked
    return found

def parse_amount(x):
    try:
        if pd.isna(x):
            return 0.0
        s = str(x).replace(",", "").strip()
        for sym in ["$", "£", "€"]:
            s = s.replace(sym, "")
        return float(s)
    except Exception:
        return 0.0

def parse_bool(x):
    if pd.isna(x):
        return False
    s = str(x).strip().lower()
    return s in ("1", "true", "t", "yes", "y", "auto", "automatic")

def parse_number(x):
    try:
        if pd.isna(x):
            return 0.0
        return float(x)
    except Exception:
        import re
        m = re.search(r"[\d\.]+", str(x))
        return float(m.group(0)) if m else 0.0

# --- scoring / recommendation logic ---------------------------------------
def compute_recommendations(df: pd.DataFrame, colmap: Dict[str, str]) -> List[Dict[str, Any]]:
    rows = []
    def col(name): return colmap.get(name)
    amount_vals = []
    for _, r in df.iterrows():
        a = parse_amount(r[col("amount")]) if col("amount") else 0.0
        amount_vals.append(a)
    median_amount = float(pd.Series(amount_vals).median()) if amount_vals else 0.0
    today = pd.Timestamp.now()

    for _, r in df.iterrows():
        # identify service label
        service = None
        if col("service"):
            service = r[col("service")]
        elif col("subscription_id"):
            service = r[col("subscription_id")]
        else:
            service = "Unknown Service"

        amount = parse_amount(r[col("amount")]) if col("amount") else 0.0
        currency = r[col("currency")] if col("currency") else "USD"
        freq = r[col("frequency")] if col("frequency") else "monthly"
        category = r[col("category")] if col("category") else None
        notes = r[col("notes")] if col("notes") else ""
        uses_per_month = parse_number(r[col("uses_per_month")]) if col("uses_per_month") else None
        usage_count = parse_number(r[col("usage_count")]) if col("usage_count") else None

        # parse last_used_date
        last_used_raw = r[col("last_used_date")] if col("last_used_date") else None
        last_used = pd.to_datetime(last_used_raw, errors="coerce")
        days_since_last_use = (today - last_used).days if pd.notna(last_used) else math.inf

        is_auto = parse_bool(r[col("is_automatic")]) if col("is_automatic") else True

        score = 50.0

        # usage
        if uses_per_month is not None:
            if uses_per_month >= 5:
                score += 30
            elif uses_per_month >= 1:
                score += 10
            else:
                score -= 20
        elif usage_count is not None:
            if usage_count >= 50:
                score += 20
            elif usage_count >= 5:
                score += 5
            else:
                score -= 15
        else:
            score -= 5

        # recency
        if days_since_last_use == math.inf:
            score -= 5
        elif days_since_last_use > OLD_THRESHOLD_DAYS:
            score -= 25
        elif days_since_last_use > 30:
            score -= 5
        else:
            score += 10

        # cost
        if median_amount > 0 and amount > median_amount * HIGH_COST_FACTOR:
            score -= 15
        elif amount == 0:
            score += 20

        # essential categories -> boost
        essential_cats = {"infrastructure", "accounting", "payment", "crm", "devops", "security"}
        if category and str(category).strip().lower() in essential_cats:
            score += 30

        # auto renew slightly favored
        score += 5 if is_auto else -2

        score = max(0, min(100, score))
        decision = "keep" if score >= 50 else "cancel"

        reasons = []
        if uses_per_month is not None:
            reasons.append(f"uses_per_month={uses_per_month}")
        if usage_count is not None:
            reasons.append(f"usage_count={int(usage_count)}")
        if days_since_last_use != math.inf:
            reasons.append(f"days_since_last_use={int(days_since_last_use)}")
        reasons.append(f"amount={amount} {currency}")
        reasons.append("auto-renew" if is_auto else "manual")
        reason_text = "; ".join(reasons)

        rows.append({
            "Service": str(service),
            "Amount": float(amount),
            "Currency": currency,
            "Frequency": str(freq),
            "Category": str(category) if category is not None else "",
            "UsesPerMonth": uses_per_month if uses_per_month is not None else None,
            "UsageCount": usage_count if usage_count is not None else None,
            "DaysSinceLastUse": (int(days_since_last_use) if days_since_last_use != math.inf else None),
            "IsAutoRenew": bool(is_auto),
            "Score": score,
            "Decision": decision,
            "ReasonSummary": reason_text,
            "Notes": str(notes)
        })

    rows_sorted = sorted(rows, key=lambda x: x["Score"])
    return rows_sorted

# --- Gemini (optional) integration ----------------------------------------
def call_gemini_for_explanations(top_candidates: List[Dict[str, Any]]) -> str:
    # Hardcoded API key (test only)
    api_key = "AIzaSyALyeKtM7eazs__zjzF9J_EmnIsW1Jb5O8"  

    if not GEMINI_AVAILABLE:
        logger.info("Gemini client not available; skipping LLM explanations.")
        return ""
    if not api_key:
        logger.info("No API key found; skipping LLM explanations.")
        return ""
    try:
        client = genai.Client(api_key=api_key)
        prompt_lines = [
           """
You are a pragmatic, senior CFO assistant. Given the following list of subscriptions flagged for potential cancellation, produce a compact, high-signal result.
For each item produce:
1) One short reason to cancel (8-12 words).
2) One concrete next step the finance team should take (very actionable: exact menu click, API call, or email subject + recipient role).
3) A 1-line risk check (what to verify if anything might break).

Format: JSON array of objects with keys: service, monthly_amount_usd, reason, next_step, risk_check
Do not add any extra prose outside the JSON array.
Limit to the top {top_n} items.

Example output element:
{{
  "service": "ExampleApp",
  "monthly_amount_usd": 450.0,
  "reason": "No active users in last 6 months; duplicate functionality.",
  "next_step": "Export invoices (Billing → Invoices), disable auto-renew in Provider Portal → pause subscription.",
  "risk_check": "Ensure 30-day data export exists and notify product owner (PO@example.com)."
}}
"""
        ]
        for c in top_candidates:
            prompt_lines.append(f"- {c['Service']} ({c['Category']}): ${c['Amount']}. Reasons: {c['ReasonSummary']}")
        prompt = "\n".join(prompt_lines)
        logger.info("Sending prompt to Gemini (trimmed to %d items).", len(top_candidates))
        resp = client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)
        text = getattr(resp, "text", None) or getattr(resp, "content", None) or str(resp)
        return str(text)
    except Exception as e:
        logger.exception("Gemini call failed: %s", e)
        return ""

# --- Friendly summary composition ------------------------------------------
def compose_summary(recs: List[Dict[str, Any]], llm_explanation: str = "") -> str:
    total = len(recs)
    cancel_count = len([r for r in recs if r["Decision"] == "cancel"])
    keep_count = total - cancel_count

    lines = [
        f"Total subscriptions analyzed: {total}",
        f"Suggested to CANCEL: {cancel_count}",
        f"Suggested to KEEP: {keep_count}",
        "",
        "Top cancellation recommendations (highest priority first):"
    ]
    top_cancels = [r for r in recs if r["Decision"] == "cancel"]
    if not top_cancels:
        lines.append(" - None. Your subscriptions look fine under current heuristics.")
    else:
        for r in top_cancels[:20]:
            lines.append(f"- {r['Service']} (${r['Amount']}) => RECOMMENDATION: {r['Decision'].upper()}. Why: {r['ReasonSummary']}")

    if llm_explanation:
        lines += ["", "LLM Explanation / Suggested Actions:", llm_explanation]

    lines += [
        "",
        "Suggested next steps:",
        "1) For each CANCEL candidate: review billing, check if shared accounts exist, pause auto-renew or cancel from provider portal.",
        "2) For high-cost KEEP candidates: negotiate enterprise discount or downgrade plan.",
        "3) For unclear items: manually inspect notes/usage or attach invoices for deeper audit."
    ]
    return "\n".join(lines)

# --- main ------------------------------------------------------------------
def main():
    print("CFO Agent starting (combined)...")

    csv_path = "subscriptions.csv"
    if not os.path.exists(csv_path):
        logger.error("CSV file not found at %s", csv_path)
        print("Put subscriptions.csv next to this main.py and re-run.")
        return

    df = try_read_csv(csv_path)
    logger.info("Loaded CSV: %s rows, %s columns", df.shape[0], df.shape[1])
    print("Loaded transactions (first 5 rows):")
    print(df.head(5))
    colmap = map_columns(df)
    logger.info("Column mapping detected: %s", colmap)

    recs = compute_recommendations(df, colmap)
    # Print a short table of top candidates
    print("\nSample scored subscriptions (lowest score first - top cancellation candidates):")
    for r in recs[:10]:
        print(f"{r['Service']} | ${r['Amount']} | Score={r['Score']:.1f} | Decision={r['Decision']} | {r['ReasonSummary']}")

    # Prepare LLM explanation only for top cancellation candidates
    cancel_candidates = [r for r in recs if r["Decision"] == "cancel"]
    llm_text = ""
    if cancel_candidates:
        top_for_llm = cancel_candidates[:TOP_FOR_LLM]
        llm_text = call_gemini_for_explanations(top_for_llm)
        if llm_text:
            logger.info("Received LLM explanation text (len=%d).", len(llm_text))

    summary = compose_summary(recs, llm_text)
    print("\n===== CFO Agent Summary =====")
    print(summary)
    print("===== End of Summary =====\n")

    # Return structure (useful for Coral or other orchestration)
    return {
        "recommendations": recs,
        "llm_explanation": llm_text,
        "summary_text": summary
    }

if __name__ == "__main__":
    main()