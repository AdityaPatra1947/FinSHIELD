"""Authoritative spending formulas (spending-v1, spec 5.2 / 5.5). All money in integer paise."""
from __future__ import annotations

import pandas as pd

CALC_VERSION = "spending-v1"
GROSS = {"purchase", "fee", "interest_expense"}
CREDITS = {"refund", "expense_reversal"}
INCOME = {"salary", "interest_income", "other_earned_income"}
UNRESOLVED = {"external_transfer", "unclassified"}


def effective(tx: pd.DataFrame) -> pd.DataFrame:
    """Apply the user's classification overlay: an external transfer the customer has classified (e.g. 'gifts',
    'family support') is an expense in that category; unclassified ones stay unresolved. Original rows are untouched."""
    if "voided" in tx.columns:
        tx = tx[~tx.voided.fillna(False).astype(bool)]
    if "class_category" not in tx.columns:
        return tx
    any_cls = tx.class_category.notna()
    if not any_cls.any():
        return tx
    ext = (tx.purpose == "external_transfer") & any_cls
    d = tx.copy()
    d["purpose"] = d.purpose.where(~ext, "purchase")
    d["category"] = d.category.where(~any_cls, d.class_category)
    if "class_subcategory" in d.columns and "subcategory" in d.columns:
        d["subcategory"] = d.subcategory.where(~any_cls, d.class_subcategory)
    return d


def spending_totals(tx: pd.DataFrame, start_ts: int, end_ts: int) -> dict:
    """Half-open [start_ts, end_ts) on posted_ts; only posted, non-derived-duplicate rows count.

    Wallet credits derived from ATM legs and cash-account movements are asset moves with
    purpose cash_withdrawal and therefore carry no spending/income effect.
    """
    d = effective(tx)
    d = d[(d.status == "posted") & (d.posted_ts >= start_ts) & (d.posted_ts < end_ts)]
    gross = d[d.purpose.isin(GROSS)]
    cred = d[d.purpose.isin(CREDITS)]
    inc = d[d.purpose.isin(INCOME)]
    g, c, i = int(gross.amount_minor.sum()), int(cred.amount_minor.sum()), int(inc.amount_minor.sum())
    net = g - c
    surplus = i - net
    unres = d[d.purpose.isin(UNRESOLVED)]
    out = {
        "calculation_version": CALC_VERSION, "currency": "INR",
        "gross_spending_minor": str(g), "expense_credits_minor": str(c), "net_spending_minor": str(net),
        "recognized_income_minor": str(i), "budget_surplus_minor": str(surplus),
        "budget_surplus_rate": (100.0 * surplus / i) if i > 0 else None,
        "budget_surplus_rate_reason": None if i > 0 else "no recognized income in period",
        "unclassified_outflow_minor": str(int(unres[unres.direction == "debit"].amount_minor.sum())),
        "unclassified_inflow_minor": str(int(unres[unres.direction == "credit"].amount_minor.sum())),
        "transactions_counted": int(len(gross) + len(cred) + len(inc)),
    }
    return out


def category_breakdown(tx: pd.DataFrame, start_ts: int, end_ts: int) -> list[dict]:
    d = effective(tx)
    d = d[(d.status == "posted") & (d.posted_ts >= start_ts) & (d.posted_ts < end_ts)]
    gross = d[d.purpose.isin(GROSS)].groupby(d.category.fillna("uncategorized")).amount_minor.sum()
    cred = d[d.purpose.isin(CREDITS)].groupby(d.category.fillna("uncategorized")).amount_minor.sum()
    cats = sorted(set(gross.index) | set(cred.index))
    tg = int(gross.sum())
    rows = []
    for c in cats:
        g, cr = int(gross.get(c, 0)), int(cred.get(c, 0))
        rows.append({"category": c, "gross_minor": str(g), "credits_minor": str(cr), "net_minor": str(g - cr),
                     "gross_share": (100.0 * g / tg) if tg > 0 else None})
    return sorted(rows, key=lambda r: -int(r["net_minor"]))


def monthly_trend(tx: pd.DataFrame, start_ts: int, end_ts: int, tz: str = "Asia/Kolkata") -> list[dict]:
    """Calendar-month buckets in the reporting timezone, zero-filled."""
    d = effective(tx)
    d = d[(d.status == "posted") & (d.posted_ts >= start_ts) & (d.posted_ts < end_ts)].copy()
    local = pd.to_datetime(d.posted_ts, unit="s", utc=True).dt.tz_convert(tz)
    d["month"] = local.dt.strftime("%Y-%m")
    months = pd.period_range(pd.Timestamp(start_ts, unit="s", tz="UTC").tz_convert(tz).tz_localize(None),
                             pd.Timestamp(end_ts - 1, unit="s", tz="UTC").tz_convert(tz).tz_localize(None),
                             freq="M").strftime("%Y-%m")
    out = []
    for m in months:
        r = d[d.month == m]
        g = int(r[r.purpose.isin(GROSS)].amount_minor.sum())
        c = int(r[r.purpose.isin(CREDITS)].amount_minor.sum())
        i = int(r[r.purpose.isin(INCOME)].amount_minor.sum())
        out.append({"bucket": m, "gross_spending_minor": str(g), "expense_credits_minor": str(c),
                    "net_spending_minor": str(g - c), "recognized_income_minor": str(i)})
    return out


def cash_reconciliation(tx: pd.DataFrame, opening_minor: int = 0, observed_minor: int | None = None) -> dict:
    """expected = opening + withdrawals into wallet - cash purchases (- deposits). Suggestions never post."""
    cash = tx[(tx.account_kind == "cash") & (tx.status == "posted")]
    w = int(cash[(cash.purpose == "cash_withdrawal") & (cash.direction == "credit")].amount_minor.sum())
    dep = int(cash[(cash.purpose == "cash_deposit") & (cash.direction == "debit")].amount_minor.sum())
    sp = int(cash[(cash.purpose == "purchase") & (cash.direction == "debit")].amount_minor.sum())
    expected = opening_minor + w - sp - dep
    return {"opening_minor": str(opening_minor), "withdrawals_minor": str(w), "cash_purchases_minor": str(sp),
            "deposits_minor": str(dep), "expected_closing_minor": str(expected),
            "observed_closing_minor": None if observed_minor is None else str(observed_minor),
            "difference_minor": None if observed_minor is None else str(expected - observed_minor)}
