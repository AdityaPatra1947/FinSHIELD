"""Finance layer builder (synthetic): turns the base fraud ledger into a structured personal-finance dataset.

`build(tx, cust)` is a pure function -> dict of DataFrames (no I/O) so it is testable and deterministic (seed 777).
It (1) classifies every existing ledger row (type, category/subcategory, merchant, payment method, need/want,
fixed/variable, tags), (2) assigns each customer an income profile with gross/net pay, (3) appends realistic extra
rows (bills, subscriptions, insurance, EMIs, other income, social spending), (4) builds accounts with opening
balances, loans, investments (+monthly valuations), recurring items, budgets, goals and customer profiles.

Base rows are never deleted. Fraud-eligible rows keep their original purpose/amount, so the frozen fraud models'
feature contract is untouched (the feature builder only reads eligible rows).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.finance import taxonomy as T
from app.ml.generator import DAY, ORIGIN_TS

IST = timezone(timedelta(hours=5, minutes=30))
SEED = 777
WINDOW = [(2025 + (9 + i) // 12, (9 + i) % 12 + 1) for i in range(12)]  # (year, month) Oct-2025 .. Sep-2026
DATA_END_TS = ORIGIN_TS + 365 * DAY
ACCT_IDX = {"bank": 1, "savings": 2, "cash": 3, "credit_card": 4}
ACCT_NAME = {"bank": "Primary bank account", "savings": "Savings account", "cash": "Cash wallet", "credit_card": "Credit card"}
INSTITUTIONS = ["HDFC Bank", "ICICI Bank", "SBI", "Axis Bank", "Kotak Bank", "Yes Bank"]

PURPOSE_TYPE = {
    "salary": "income", "interest_income": "income", "other_earned_income": "income",
    "purchase": "expense", "fee": "expense", "interest_expense": "expense", "refund": "expense",
    "expense_reversal": "expense",
    "own_transfer": "transfer", "cash_withdrawal": "transfer", "cash_deposit": "transfer",
    "card_repayment": "transfer", "external_transfer": "transfer",
    "investment_contribution": "investment", "investment_redemption": "investment",
    "loan_principal": "debt", "loan_disbursement": "debt",
}
NEW_COLS = ["account_id", "txn_type", "subcategory", "merchant_name", "payment_method", "need_want", "fixed_variable",
            "is_recurring", "recurring_id", "tags", "notes", "income_type", "gross_minor", "pf_minor", "tds_minor",
            "other_ded_minor", "class_category", "class_subcategory", "source", "base_amount_minor", "base_purpose",
            "voided"]


def ts_of(y: int, m: int, day: int, hour: int = 10) -> int:
    return int(datetime(y, m, min(day, 28), hour, tzinfo=IST).timestamp())


def _ym_shift(y: int, m: int, delta: int) -> tuple[int, int]:
    k = y * 12 + (m - 1) + delta
    return k // 12, k % 12 + 1


# --------------------------------------------------------------------------------------------- classification
def classify_base(tx: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    t = tx.copy()
    t["source"] = "base"
    t["txn_type"] = t.purpose.map(PURPOSE_TYPE).fillna("expense")

    names, subs = [], []
    for rid, cat, mk in zip(t.id.values, t.category.values, t.merchant_key.values):
        name = sub = None
        if cat in T.GEN_MERCHANTS:
            n = -1
            if isinstance(mk, str) and mk.startswith("m") and mk[1:].isdigit():
                n = int(mk[1:])
            if 0 <= n < 54 and T.GEN_ORDER[n // 6] == cat:
                name, sub = T.GEN_MERCHANTS[cat][n % 6]
            else:
                name, sub = T.GEN_MERCHANTS[cat][int(rid) % 6]
        elif cat == "rent":
            name, sub = "Landlord", "rent"
        elif cat == "fees":
            name, sub = "Bank charges", "bank_fee"
        names.append(name)
        subs.append(sub)
    t["merchant_name"], t["subcategory"] = names, subs

    ch, kind, pur = t.channel, t.account_kind, t.purpose
    pm = pd.Series("Bank transfer", index=t.index)
    pm[ch == "upi"] = "UPI"
    pm[(ch == "card") & (kind == "credit_card")] = "Credit card"
    pm[(ch == "card") & (kind != "credit_card")] = "Debit card"
    pm[ch == "netbanking"] = "Net banking"
    pm[ch == "atm"] = "Cash (ATM)"
    pm[(ch == "manual") & (kind == "cash")] = "Cash"
    pm[(ch == "manual") & (kind != "cash")] = "Manual entry"
    pm[ch == "derived"] = "Cash (wallet)"
    pm[(ch == "bank") & (pur == "salary")] = "Bank transfer"
    pm[(ch == "bank") & pur.isin(["own_transfer", "card_repayment"])] = "Net banking"
    pm[(ch == "bank") & (pur == "investment_contribution")] = "Auto-debit (SIP)"
    pm[(ch == "bank") & (pur == "fee")] = "Bank charge"
    pm[(ch == "bank") & (pur == "refund")] = "Refund to source"
    pm[(ch == "bank") & (t.category == "rent") & (pur == "purchase")] = "Net banking"
    t["payment_method"] = pm

    exp = t.txn_type == "expense"
    t["need_want"] = [T.need_want(c) if e else None for c, e in zip(t.category, exp)]
    fixed_lookup = {c: v["fixed"] for c, v in T.CATEGORIES.items()}
    t["fixed_variable"] = [("fixed" if (s in fixed_lookup.get(c, set())) else "variable") if e and isinstance(c, str) else None
                           for c, s, e in zip(t.category, t.subcategory, exp)]
    t["is_recurring"] = ((t.category == "rent") & (t.purpose == "purchase")) | t.purpose.isin(["salary", "investment_contribution"])
    t["recurring_id"] = np.nan
    t["income_type"] = np.where(t.purpose == "salary", "salary", None)
    # tags: ~12% of expenses carry one tag
    tg = np.array(T.TAGS, dtype=object)
    pick = rng.random(len(t)) < 0.12
    t["tags"] = np.where(pick & exp.values, tg[rng.integers(0, len(tg), len(t))], None)
    t["notes"] = None
    for c in ("gross_minor", "pf_minor", "tds_minor", "other_ded_minor", "base_amount_minor"):
        t[c] = np.nan
    t["base_purpose"] = None
    t["class_category"] = None
    t["class_subcategory"] = None
    t["voided"] = False
    t["account_id"] = t.customer_id * 10 + t.account_kind.map(ACCT_IDX)

    # classify ~65% of genuine (non-fraud, posted) external transfers so the rest can show up in a review queue
    ext = (t.purpose == "external_transfer") & (t.status == "posted") & (t.fraud == 0)
    chosen = ext & (rng.random(len(t)) < 0.65)
    opts = [("social", "gifts"), ("social", "festival"), ("social", "family_support"), ("education", "coaching"),
            ("health", "doctor"), ("household_help", "domestic"), ("social", "donations"), ("rent", "maintenance")]
    wts = np.array([0.22, 0.14, 0.2, 0.08, 0.1, 0.1, 0.1, 0.06])
    idx = rng.choice(len(opts), size=int(chosen.sum()), p=wts / wts.sum())
    t.loc[chosen, "class_category"] = [opts[i][0] for i in idx]
    t.loc[chosen, "class_subcategory"] = [opts[i][1] for i in idx]
    return t


# --------------------------------------------------------------------------------------------- helpers
def _net_deduction_rate(net: float) -> float:
    return 0.06 if net < 25000 else 0.10 if net < 50000 else 0.14 if net < 100000 else 0.20 if net < 200000 else 0.26


def salary_breakup(net_minor: float, kind: str):
    """Gross vs net for a salary credit: returns (gross, pf, tds, other) all in paise. Net is what reaches the account."""
    if kind != "salary":
        return net_minor, 0, 0, 0
    d = _net_deduction_rate(net_minor / 100)
    gross = net_minor / (1 - d)
    pf = round(0.048 * gross)
    pt = 20000 if gross > 1_500_000 else 0
    tds = gross - net_minor - pf - pt
    if tds < 0:
        tds = 0
        gross = net_minor + pf + pt
    return round(gross), pf, round(tds), pt


def amortize(emi: float, rate_pa: float, n_total: int):
    r = rate_pa / 1200
    principal = emi * (1 - (1 + r) ** -n_total) / r
    return principal, r


def balance_after(principal: float, r: float, emi: float, k: int) -> float:
    return max(0.0, principal * (1 + r) ** k - emi * ((1 + r) ** k - 1) / r)


# --------------------------------------------------------------------------------------------- main builder
def build(tx_base: pd.DataFrame, cust: pd.DataFrame, seed: int = SEED, log=print) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    base = tx_base.copy()
    # restore a previous enrichment if re-running (drop finance rows, undo income edits)
    if "source" in base.columns:
        mod = base.base_purpose.notna() | base.base_amount_minor.notna()
        base.loc[mod, "amount_minor"] = base.loc[mod, "base_amount_minor"].fillna(base.loc[mod, "amount_minor"]).astype("int64")
        base.loc[base.base_purpose.notna(), "purpose"] = base.loc[base.base_purpose.notna(), "base_purpose"]
        base = base[base.source == "base"]
        base = base[[c for c in base.columns if c not in NEW_COLS]]
    base["amount_minor"] = base.amount_minor.astype("int64")
    t = classify_base(base, rng)
    next_id = int(t.id.max()) + 1

    ids = cust.customer_id.values
    income = t[t.purpose == "salary"].groupby("customer_id").amount_minor.median() / 100
    income = income.reindex(ids).fillna(30000.0)
    open_day = dict(zip(cust.customer_id, cust.open_day))
    open_ts = {c: ORIGIN_TS + (int(d) - 1) * DAY for c, d in open_day.items()}

    # ---- income profiles & modification of base income rows
    profile = {}
    for c in ids:
        inc = income[c]
        if inc < 18000:
            profile[c] = rng.choice(["student", "gig"], p=[0.6, 0.4])
        else:
            profile[c] = rng.choice(["salaried", "freelancer", "business"], p=[0.74, 0.14, 0.12])
    itype_choice = {"salaried": ["salary"], "student": ["stipend"], "gig": ["gig"],
                    "freelancer": ["freelance", "consulting", "tuition"], "business": ["shop_revenue", "online_business"]}
    sigma = {"freelancer": 0.35, "business": 0.25, "gig": 0.2, "student": 0.0, "salaried": 0.0}
    cust_itype = {c: rng.choice(itype_choice[profile[c]]) for c in ids}
    sal = t[t.purpose == "salary"].index
    for i in sal:
        c = t.at[i, "customer_id"]
        p = profile[c]
        net = float(t.at[i, "amount_minor"])
        it = cust_itype[c]
        if p != "salaried":
            t.at[i, "base_amount_minor"] = net
            t.at[i, "base_purpose"] = "salary"
            net = round(net * float(np.exp(rng.normal(0, sigma[p]))) / 100) * 100 if sigma[p] else net
            t.at[i, "amount_minor"] = int(net)
            t.at[i, "purpose"] = "other_earned_income"
        g, pf, tds, oth = salary_breakup(net, "salary" if p == "salaried" else "other")
        t.at[i, "income_type"] = it
        t.at[i, "gross_minor"], t.at[i, "pf_minor"], t.at[i, "tds_minor"], t.at[i, "other_ded_minor"] = g, pf, tds, oth
        t.at[i, "is_recurring"] = p == "salaried"
    t["tags"] = t["tags"].astype(object)

    # ---- accounts: need cumulative flows later; build new rows first
    new: list[dict] = []

    def add(c, ts, amount, direction, purpose, category=None, sub=None, merchant=None, method="Net banking",
            kind="bank", channel="bank", itype=None, recurring=None, fixed=None, tags=None, notes=None, gross=None,
            pf=0, tds=0, oth=0):
        nonlocal next_id
        amount = int(round(amount))
        if amount <= 0 or ts >= DATA_END_TS or ts < open_ts[c]:
            return
        ttype = PURPOSE_TYPE.get(purpose, "expense")
        new.append(dict(
            id=next_id, customer_id=c, account_kind=kind, amount_minor=amount, direction=direction, status="posted",
            purpose=purpose, category=category, merchant_key=None, channel=channel, ts=int(ts), device_token=None,
            payee_token=None, eligible=False, fraud=0, linked_id=np.nan, day=int((ts - ORIGIN_TS) // DAY + 1),
            posted_ts=float(ts + 60), is_derived=False, account_id=c * 10 + ACCT_IDX[kind], txn_type=ttype,
            subcategory=sub, merchant_name=merchant, payment_method=method,
            need_want=T.need_want(category) if ttype == "expense" else None,
            fixed_variable=(fixed if fixed else None) if ttype == "expense" else None,
            is_recurring=recurring is not None, recurring_id=recurring if recurring is not None else np.nan,
            tags=tags, notes=notes, income_type=itype, gross_minor=gross if gross is not None else (amount if ttype == "income" else np.nan),
            pf_minor=pf if ttype == "income" else np.nan, tds_minor=tds if ttype == "income" else np.nan,
            other_ded_minor=oth if ttype == "income" else np.nan, class_category=None, class_subcategory=None,
            source="finance", base_amount_minor=np.nan, base_purpose=None, voided=False))
        next_id += 1

    recurring: list[dict] = []
    loans: list[dict] = []
    rec_id = 1
    fixed_sub = {c: v["fixed"] for c, v in T.CATEGORIES.items()}

    def new_rec(c, name, kind, amount, freq, day, direction, category, sub, account_kind="bank", last_month=None, itype=None):
        nonlocal rec_id
        r = dict(recurring_id=rec_id, customer_id=c, name=name, kind=kind, amount_minor=int(amount), frequency=freq,
                 day_of_month=int(min(day, 28)), direction=direction, category=category, subcategory=sub,
                 account_id=c * 10 + ACCT_IDX[account_kind], income_type=itype, confirmed=True)
        recurring.append(r)
        rec_id += 1
        return r["recurring_id"]

    # recurring items for the base recurring rows (salary, rent, SIP) get created per customer below
    # existing base rows get recurring ids too
    base_rec = {}
    for c in ids:
        inc = float(income[c])
        scale = inc / 50000.0
        p = profile[c]
        # base salary / income
        rid = new_rec(c, f"{T.INCOME_TYPES[cust_itype[c]][0]}", "income", int(inc * 100), "monthly", 1, "credit", None, None,
                      itype=cust_itype[c])
        base_rec[(c, "salary")] = rid
        base_rec[(c, "rent")] = new_rec(c, "Rent", "rent", int(round(inc * 0.28, -2) * 100), "monthly", 5, "debit", "rent", "rent")
        base_rec[(c, "sip")] = new_rec(c, "Monthly SIP / investments", "sip", int(round(inc * 0.08, -2) * 100), "monthly", 10,
                                       "debit", None, None)
    t.loc[t.purpose.isin(["salary", "other_earned_income"]) & (t.source == "base") & t.income_type.notna(), "recurring_id"] = \
        [base_rec.get((c, "salary")) for c in t.loc[t.purpose.isin(["salary", "other_earned_income"]) & (t.source == "base") & t.income_type.notna(), "customer_id"]]
    rent_mask = (t.category == "rent") & (t.purpose == "purchase") & (t.source == "base")
    t.loc[rent_mask, "recurring_id"] = [base_rec[(c, "rent")] for c in t.loc[rent_mask, "customer_id"]]
    sip_mask = (t.purpose == "investment_contribution") & (t.source == "base")
    t.loc[sip_mask, "recurring_id"] = [base_rec[(c, "sip")] for c in t.loc[sip_mask, "customer_id"]]
    t.loc[sip_mask, "notes"] = "Monthly SIP"
    t.loc[rent_mask, "notes"] = "Monthly rent"

    sav_inflow = t[(t.account_kind == "savings") & (t.direction == "credit") & (t.purpose == "own_transfer")]
    sav_by_month = {}
    for c, g in sav_inflow.groupby("customer_id"):
        mm = ((pd.to_datetime(g.ts, unit="s", utc=True).dt.tz_convert(IST)).dt.strftime("%Y-%m"))
        sav_by_month[c] = g.amount_minor.groupby(mm.values).sum().to_dict()

    # opening-wealth components decided now so dividends/interest can use them
    opening_savings = {c: float(income[c]) * float(rng.uniform(1.5, 5.0)) * 100 for c in ids}

    subs_pool = [("Netflix", "ott", 649), ("Prime Video", "ott", 299), ("Disney+ Hotstar", "ott", 299),
                 ("Spotify Premium", "music", 119), ("YouTube Premium", "ott", 149), ("iCloud+", "ott", 75)]
    loan_kinds = {
        "personal_loan": ("Personal loan", ["HDFC Bank", "ICICI Bank", "Bajaj Finserv"], (11, 16), (24, 60)),
        "vehicle_loan": ("Vehicle loan", ["SBI", "Axis Bank", "Tata Capital"], (8.5, 11), (36, 84)),
        "home_loan": ("Home loan", ["SBI", "HDFC Ltd", "LIC Housing"], (8.2, 9.5), (120, 240)),
        "education_loan": ("Education loan", ["SBI", "Bank of Baroda"], (9, 12), (60, 120)),
        "gadget_emi": ("Gadget EMI", ["Bajaj Finserv", "Amazon Pay EMI"], (0, 0), (6, 18)),
    }
    loan_id = 1
    for c in ids:
        inc = float(income[c])
        scale = inc / 50000.0
        p = profile[c]
        start = open_ts[c]
        # ---------------- utility bills
        if rng.random() < 0.72:
            rid = new_rec(c, "Electricity bill", "bill", int(inc * 100 * 0.018), "monthly", 12, "debit", "utilities", "electricity")
            for (y, mo) in WINDOW:
                season = 1.5 if mo in (4, 5, 6) else 1.0
                add(c, ts_of(y, mo, 12), max(30000, inc * 100 * 0.018 * season * rng.uniform(0.85, 1.15)), "debit", "purchase",
                    "utilities", "electricity", "BESCOM", "UPI", "bank", "bank", recurring=rid, fixed="variable",
                    notes="Electricity bill")
            plan = int(rng.choice([239, 299, 399, 599, 719])) * 100
            rid = new_rec(c, "Mobile plan", "bill", plan, "monthly", 7, "debit", "utilities", "mobile")
            for (y, mo) in WINDOW:
                add(c, ts_of(y, mo, 7), plan, "debit", "purchase", "utilities", "mobile", "Jio", "Auto-debit", "bank", "bank",
                    recurring=rid, fixed="fixed", notes="Mobile recharge")
            if rng.random() < 0.7:
                plan2 = int(rng.choice([499, 699, 899, 999, 1199])) * 100
                rid = new_rec(c, "Broadband", "bill", plan2, "monthly", 9, "debit", "utilities", "internet")
                for (y, mo) in WINDOW:
                    add(c, ts_of(y, mo, 9), plan2, "debit", "purchase", "utilities", "internet", "Airtel Fibre", "Auto-debit",
                        "bank", "bank", recurring=rid, fixed="fixed", notes="Broadband")
            if rng.random() < 0.5:
                gas = int(rng.integers(850, 1010)) * 100
                rid = new_rec(c, "Gas cylinder", "bill", gas, "monthly", 15, "debit", "utilities", "gas")
                for (y, mo) in WINDOW:
                    add(c, ts_of(y, mo, 15), gas, "debit", "purchase", "utilities", "gas", "Indane Gas", "UPI", "bank", "upi",
                        recurring=rid, fixed="fixed", notes="LPG refill")
        # ---------------- subscriptions
        n_sub = int(min(len(subs_pool), rng.poisson(0.4 + 1.8 * min(scale, 2.5)))) if inc >= 15000 else int(rng.random() < 0.2)
        for name, sub, amt in [subs_pool[i] for i in rng.choice(len(subs_pool), size=n_sub, replace=False)] if n_sub else []:
            day = int(rng.integers(1, 28))
            rid = new_rec(c, name, "subscription", amt * 100, "monthly", day, "debit", "entertainment", sub)
            for (y, mo) in WINDOW:
                add(c, ts_of(y, mo, day), amt * 100, "debit", "purchase", "entertainment", sub, name, "Auto-debit", "bank",
                    "bank", recurring=rid, fixed="fixed", tags="subscription")
        if inc >= 25000 and rng.random() < 0.22:
            amt = int(rng.integers(8, 26)) * 100 * 100
            day = int(rng.integers(1, 28))
            rid = new_rec(c, "Gym membership", "subscription", amt, "monthly", day, "debit", "personal_care", "gym")
            for (y, mo) in WINDOW:
                add(c, ts_of(y, mo, day), amt, "debit", "purchase", "personal_care", "gym", "Cult.fit", "Auto-debit", "bank",
                    "bank", recurring=rid, fixed="fixed")
        # ---------------- insurance (annual)
        ins = []
        if inc >= 25000 and rng.random() < 0.55:
            ins.append(("health_insurance", "Health insurance premium", "Star Health", int(rng.integers(6, 26)) * 1000))
        if inc >= 50000 and rng.random() < 0.4:
            ins.append(("term_life", "Term life premium", "LIC", int(rng.integers(8, 21)) * 1000))
        if inc >= 30000 and rng.random() < 0.25:
            ins.append(("vehicle", "Vehicle insurance", "ICICI Lombard", int(rng.integers(3, 10)) * 1000))
        for sub, name, merchant, amt in ins:
            mo_idx = int(rng.integers(0, 12))
            y, mo = WINDOW[mo_idx]
            rid = new_rec(c, name, "insurance", amt * 100, "annual", 15, "debit", "insurance", sub)
            add(c, ts_of(y, mo, 15), amt * 100, "debit", "purchase", "insurance", sub, merchant, "Net banking", "bank", "bank",
                recurring=rid, fixed="fixed", notes="Annual premium (80C/80D eligible)")
        # ---------------- loans / EMI
        pl = 0.05 if inc < 15000 else 0.25 if inc < 40000 else 0.45 if inc < 100000 else 0.55
        if rng.random() < pl:
            opts = (["gadget_emi", "personal_loan"] if inc < 15000 else
                    ["personal_loan", "gadget_emi", "vehicle_loan"] if inc < 40000 else
                    ["personal_loan", "vehicle_loan", "home_loan", "education_loan"] if inc < 100000 else
                    ["home_loan", "vehicle_loan", "personal_loan", "education_loan"])
            kind = str(rng.choice(opts))
            lname, lenders, (rlo, rhi), (nlo, nhi) = loan_kinds[kind]
            share = {"home_loan": (0.22, 0.34), "vehicle_loan": (0.10, 0.18), "personal_loan": (0.08, 0.16),
                     "education_loan": (0.08, 0.14), "gadget_emi": (0.03, 0.07)}[kind]
            emi = round(inc * float(rng.uniform(*share)), -2)
            emi = max(emi, 500.0)
            rate = round(float(rng.uniform(rlo, rhi)), 2) if rhi else 0.0
            n_total = int(rng.integers(nlo, nhi + 1))
            # EMIs already paid before the data window starts (always leaves >= 10 EMIs still to pay)
            k0 = int(rng.integers(0, max(1, min(24, n_total - 10))))
            if rate == 0:
                principal, r = emi * n_total, 1e-9
            else:
                principal, r = amortize(emi, rate, n_total)
            day = int(rng.choice([2, 5, 8, 10]))
            rid = new_rec(c, lname, "emi", int(emi * 100), "monthly", day, "debit", "debt_emi", kind)
            first_y, first_m = _ym_shift(2025, 10, -k0)
            loans.append(dict(loan_id=loan_id, customer_id=c, kind=kind, name=lname, lender=str(rng.choice(lenders)),
                              principal_minor=int(round(principal * 100)), rate_pct=rate, tenure_months=n_total,
                              emi_minor=int(emi * 100), first_emi_date=f"{first_y:04d}-{first_m:02d}-{day:02d}",
                              pay_day=day, recurring_id=rid, account_id=c * 10 + 1))
            for wi, (y, mo) in enumerate(WINDOW):
                n = k0 + wi + 1
                if n > n_total:
                    break
                bal_prev = balance_after(principal, r, emi, n - 1)
                interest = bal_prev * r if rate else 0.0
                princ_row = int(round((emi - interest) * 100))
                emi_minor = int(emi * 100)
                int_row = emi_minor - princ_row
                tsx = ts_of(y, mo, day, 9)
                add(c, tsx, princ_row, "debit", "loan_principal", "debt_emi", kind, lname, "Auto-debit (ECS)", "bank", "bank",
                    recurring=rid, notes=f"EMI {n}/{n_total}: principal part")
                if int_row > 0:
                    add(c, tsx + 1, int_row, "debit", "interest_expense", "debt_emi", kind, lname, "Auto-debit (ECS)", "bank",
                        "bank", recurring=rid, fixed="fixed", notes=f"EMI {n}/{n_total}: interest part")
            loan_id += 1
        # ---------------- lifestyle extras
        if rng.random() < 0.45:
            for (y, mo) in WINDOW:
                if rng.random() < 0.85:
                    add(c, ts_of(y, mo, int(rng.integers(1, 28)), 17), 30000 * max(0.6, min(scale, 3) ** 0.3) * rng.uniform(1, 4),
                        "debit", "purchase", "personal_care", "salon", str(rng.choice(["Looks Salon", "Naturals", "Urban Company"])),
                        "UPI", "bank", "upi", fixed="variable")
        if inc >= 35000 and rng.random() < 0.18:
            amt = int(rng.integers(15, 61)) * 100 * 100
            rid = new_rec(c, "Domestic help", "bill", amt, "monthly", 1, "debit", "household_help", "domestic")
            for (y, mo) in WINDOW:
                add(c, ts_of(y, mo, 1, 8), amt, "debit", "purchase", "household_help", "domestic", "Domestic help", "UPI", "bank",
                    "upi", recurring=rid, fixed="fixed")
        for _ in range(int(rng.integers(4, 11))):
            y, mo = WINDOW[int(rng.integers(0, 12))]
            sub = str(rng.choice(["gifts", "festival", "donations", "gifts"]))
            tags = {"gifts": "gift", "festival": "festival", "donations": None}[sub]
            add(c, ts_of(y, mo, int(rng.integers(1, 28)), 14), 50000 * max(0.5, min(scale, 3)) * rng.uniform(0.8, 8),
                "debit", "purchase", "social", sub, {"gifts": "Gift shop", "festival": "Festival shopping", "donations": "Temple / charity"}[sub],
                "UPI", "bank", "upi", fixed="variable", tags=tags)
        if inc >= 30000 and rng.random() < 0.12:
            amt = round(inc * float(rng.uniform(0.05, 0.1)), -2) * 100
            rid = new_rec(c, "Support to family", "bill", int(amt), "monthly", 3, "debit", "social", "family_support")
            for (y, mo) in WINDOW:
                add(c, ts_of(y, mo, 3, 12), amt, "debit", "purchase", "social", "family_support", "Family", "UPI", "bank", "upi",
                    recurring=rid, fixed="fixed", tags="family")
        # ---------------- extra income
        if p == "salaried" and rng.random() < 0.55:
            net = inc * 100 * float(rng.uniform(1.0, 2.0))
            tds = round(net * 0.3 / 0.7)
            add(c, ts_of(2026, 3, 28, 11), net, "credit", "other_earned_income", None, None, "Employer", "Bank transfer", "bank",
                "bank", itype="bonus", gross=int(net + tds), tds=int(tds), notes="Annual bonus")
        if p == "salaried" and rng.random() < 0.12:
            for wi in rng.choice(12, size=int(rng.integers(3, 7)), replace=False):
                y, mo = WINDOW[int(wi)]
                add(c, ts_of(y, mo, 27, 11), inc * 100 * rng.uniform(0.05, 0.15), "credit", "other_earned_income", None, None,
                    "Employer", "Bank transfer", "bank", "bank", itype="overtime")
        sav_open = opening_savings[c]
        cum = 0.0
        for qi, wi in enumerate((2, 5, 8, 11)):
            y, mo = WINDOW[wi]
            for k in range(max(0, wi - 2), wi + 1):
                cum += sav_by_month.get(c, {}).get(f"{WINDOW[k][0]:04d}-{WINDOW[k][1]:02d}", 0)
            add(c, ts_of(y, mo, 28, 6), (sav_open + cum) * 0.035 / 4, "credit", "interest_income", None, None, "Bank interest",
                "Bank credit", "savings", "bank", itype="interest", notes="Quarterly savings interest")
        if inc >= 100000 and rng.random() < 0.14:
            amt = round(inc * float(rng.uniform(0.12, 0.22)), -2) * 100
            rid = new_rec(c, "Rent from property", "income", int(amt), "monthly", 3, "credit", None, None, itype="rent_income")
            for (y, mo) in WINDOW:
                add(c, ts_of(y, mo, 3, 10), amt, "credit", "other_earned_income", None, None, "Tenant", "Bank transfer", "bank",
                    "bank", itype="rent_income", recurring=rid)
        if rng.random() < 0.08:
            y, mo = WINDOW[int(rng.integers(0, 12))]
            it = str(rng.choice(["gift", "scholarship", "prize", "tax_refund", "resale"]))
            add(c, ts_of(y, mo, int(rng.integers(1, 28)), 15), inc * 100 * rng.uniform(0.2, 1.0), "credit", "other_earned_income",
                None, None, T.INCOME_TYPES[it][0], "Bank transfer", "bank", "bank", itype=it)

    tx_new = pd.DataFrame(new)
    t = pd.concat([t, tx_new], ignore_index=True)
    t["recurring_id"] = pd.to_numeric(t.recurring_id)
    t["is_recurring"] = t.is_recurring.fillna(False).astype(bool)
    t["voided"] = t.voided.fillna(False).astype(bool)

    # ---- realism: the base generator drew income independently of spending, so ~35% of customers would overspend.
    # Scale income (never spending) for customers with a clearly negative savings rate to a plausible target rate.
    ps = t[t.status == "posted"]
    eff = np.where((ps.purpose == "external_transfer") & ps.class_category.notna(), "purchase", ps.purpose)
    inc_c = ps[np.isin(eff, ["salary", "interest_income", "other_earned_income"])].groupby("customer_id").amount_minor.sum()
    g_c = ps[np.isin(eff, ["purchase", "fee", "interest_expense"])].groupby("customer_id").amount_minor.sum()
    cr_c = ps[np.isin(eff, ["refund", "expense_reversal"])].groupby("customer_id").amount_minor.sum()
    net_c = g_c.sub(cr_c, fill_value=0)
    factor = {}
    for c in ids:
        i_, n_ = float(inc_c.get(c, 0)), float(net_c.get(c, 0))
        if i_ > 0 and (i_ - n_) / i_ < -0.05:
            target = float(np.clip(rng.normal(0.20, 0.14), -0.08, 0.5))
            factor[c] = max(1.0, (n_ / (1 - target)) / i_)
    if factor:
        isinc = (t.txn_type == "income") & t.customer_id.isin(list(factor))
        f = t.loc[isinc, "customer_id"].map(factor).values
        base_inc = isinc & (t.source == "base") & t.base_amount_minor.isna()
        t.loc[base_inc, "base_amount_minor"] = t.loc[base_inc, "amount_minor"]
        newamt = (np.round(t.loc[isinc, "amount_minor"].values * f / 100) * 100).astype("int64")
        t.loc[isinc, "amount_minor"] = newamt
        for col in ("gross_minor", "pf_minor", "other_ded_minor"):
            t.loc[isinc, col] = np.round(t.loc[isinc, col].values * f)
        t.loc[isinc, "tds_minor"] = (t.loc[isinc, "gross_minor"] - t.loc[isinc, "amount_minor"] - t.loc[isinc, "pf_minor"]
                                     - t.loc[isinc, "other_ded_minor"]).clip(lower=0)
        t.loc[isinc, "gross_minor"] = t.loc[isinc, ["amount_minor", "pf_minor", "tds_minor", "other_ded_minor"]].sum(axis=1)
        income = income * pd.Series({c: factor.get(c, 1.0) for c in ids})
    log(f"income scaled for {len(factor)} overspending customers")

    # ------------------------------------------------------------------ accounts + opening balances
    posted = t[t.status == "posted"].sort_values(["ts", "id"])
    acc_rows = []
    sign = np.where(posted.direction == "credit", 1, -1) * posted.amount_minor.values
    posted = posted.assign(_flow=sign)
    cum_min = posted.groupby("account_id")._flow.apply(lambda s: float(np.minimum.accumulate(np.cumsum(s.values)).min()))
    card_max = posted[(posted.account_kind == "credit_card") & (posted.direction == "debit")]
    card_max_m = card_max.groupby(["customer_id", (card_max.ts // (30 * DAY))]).amount_minor.sum().groupby("customer_id").max()
    for c in ids:
        inc = float(income[c])
        kinds_present = set(t[t.customer_id == c].account_kind.unique()) | {"bank", "savings", "cash"}
        inst = INSTITUTIONS[int(c) % len(INSTITUTIONS)]
        for kind in ("bank", "savings", "cash", "credit_card"):
            if kind not in kinds_present:
                continue
            aid = c * 10 + ACCT_IDX[kind]
            mn = float(cum_min.get(aid, 0.0))
            opening = 0.0
            limit = apr = None
            if kind == "bank":
                opening = max(0.5 * inc * 100, -mn + 0.25 * inc * 100)
            elif kind == "savings":
                opening = opening_savings[c]
            elif kind == "cash":
                opening = max(0.0, -mn) + 50000
            else:
                limit = int(max(50000, math.ceil(3 * float(card_max_m.get(c, 0)) / 100 / 10000) * 10000)) * 100
                apr = 36.0
            acc_rows.append(dict(
                account_id=aid, customer_id=int(c), kind=kind, name=ACCT_NAME[kind],
                institution=inst if kind in ("bank", "savings") else ("Cash" if kind == "cash" else f"{inst} Credit Card"),
                masked_ref=f"XXXX{(int(c) * 37 + ACCT_IDX[kind] * 11) % 10000:04d}" if kind != "cash" else None,
                opening_minor=int(round(opening)), opening_ts=int(open_ts[c]), credit_limit_minor=limit, apr_pct=apr,
                purpose={"bank": "Day-to-day", "savings": "Emergency fund & savings", "cash": "Cash in hand",
                         "credit_card": "Credit"}[kind]))
    accounts = pd.DataFrame(acc_rows)

    # ------------------------------------------------------------------ investments + monthly valuations
    holdings, vals = [], []
    hid = 1
    sip_rows = t[(t.purpose == "investment_contribution") & (t.status == "posted")]
    sip_by = {c: g.assign(m=pd.to_datetime(g.ts, unit="s", utc=True).dt.tz_convert(IST).dt.strftime("%Y-%m")).groupby("m").amount_minor.sum().to_dict()
              for c, g in sip_rows.groupby("customer_id")}
    funds = [("Nifty 50 Index Fund", "equity", 0.0085, 0.040, False), ("Flexi Cap Fund", "equity", 0.0095, 0.047, False),
             ("ELSS Tax Saver Fund", "equity", 0.0092, 0.046, True), ("Short-term Debt Fund", "debt", 0.0055, 0.006, False)]
    months = [f"{y:04d}-{m:02d}" for y, m in WINDOW]
    for c in ids:
        inc = float(income[c])
        n_f = int(rng.integers(1, 4)) if c in sip_by else 0
        picks = rng.choice(len(funds), size=n_f, replace=False) if n_f else []
        w = rng.dirichlet(np.ones(max(n_f, 1))) if n_f else []
        for j, fi in enumerate(picks):
            name, ac, drift, vol, elss = funds[fi]
            val = 0.0
            inv = 0.0
            if inc >= 60000:  # pre-existing corpus
                val = inc * 100 * float(rng.uniform(0.5, 3.0)) * float(w[j])
                inv = val * 0.85
            opening_v = val
            for mi, mon in enumerate(months):
                contrib = round(sip_by.get(c, {}).get(mon, 0) * float(w[j]))
                val = val * (1 + float(rng.normal(drift, vol))) + contrib
                inv += contrib
                vals.append(dict(holding_id=hid, customer_id=int(c), month=mon, contributed_minor=int(contrib),
                                 invested_cum_minor=int(round(inv)), value_minor=int(round(val))))
            holdings.append(dict(holding_id=hid, customer_id=int(c), name=name, kind="sip_mf", asset_class=ac,
                                 sip_minor=int(round(sum(v["contributed_minor"] for v in vals[-12:]) / 12)),
                                 opening_value_minor=int(round(opening_v)), invested_minor=int(round(inv)),
                                 current_value_minor=int(round(val)), tax_80c=bool(elss)))
            hid += 1
        if inc >= 60000:  # lump-sum holdings: FD / stocks / gold
            for name, kind, ac, drift, vol in rng.choice(
                    np.array([("Fixed deposit", "fd", "debt", 0.0058, 0.0), ("Direct equity portfolio", "stock", "equity", 0.011, 0.065),
                              ("Gold (digital / ETF)", "gold", "gold", 0.007, 0.03)], dtype=object), size=int(rng.integers(1, 3)), replace=False):
                v0 = inc * 100 * float(rng.uniform(1.5, 8.0))
                val = v0
                for mi, mon in enumerate(months):
                    val = val * (1 + float(rng.normal(drift, vol)))
                    vals.append(dict(holding_id=hid, customer_id=int(c), month=mon, contributed_minor=0,
                                     invested_cum_minor=int(round(v0)), value_minor=int(round(val))))
                holdings.append(dict(holding_id=hid, customer_id=int(c), name=name, kind=kind, asset_class=ac, sip_minor=0,
                                     opening_value_minor=int(round(v0)), invested_minor=int(round(v0)),
                                     current_value_minor=int(round(val)), tax_80c=False))
                hid += 1
    holdings = pd.DataFrame(holdings)
    valuations = pd.DataFrame(vals)

    # ------------------------------------------------------------------ recurring items (+ next due)
    rec = pd.DataFrame(recurring)
    # drop recurring items that never produced a ledger row (e.g. late joiners)
    used = set(t.recurring_id.dropna().astype(int).unique())
    rec = rec[rec.recurring_id.isin(used)].copy()
    last = t[t.recurring_id.notna()].groupby(t.recurring_id.fillna(0).astype(int)).ts.max()
    rec["last_paid_ts"] = rec.recurring_id.map(last)
    step = {"monthly": 1, "quarterly": 3, "annual": 12}

    def nxt(r):
        d = datetime.fromtimestamp(r.last_paid_ts, IST)
        y, mo = _ym_shift(d.year, d.month, step[r.frequency])
        return ts_of(y, mo, r.day_of_month, 9)

    rec["next_due_ts"] = rec.apply(nxt, axis=1)
    loans_df = pd.DataFrame(loans)

    # ------------------------------------------------------------------ budgets from realised spending
    exp = t[(t.status == "posted") & (t.txn_type == "expense") & t.category.notna()].copy()
    exp["eff"] = np.where(exp.direction == "credit", -exp.amount_minor, exp.amount_minor)
    exp["month"] = pd.to_datetime(exp.ts, unit="s", utc=True).dt.tz_convert(IST).dt.strftime("%Y-%m")
    avg = exp.groupby(["customer_id", "category"]).eff.sum().div(12.0)
    budget_cats = ["groceries", "dining", "transport", "shopping", "entertainment", "utilities", "health", "travel",
                   "personal_care", "education", "rent"]
    brows = []
    for (c, cat), v in avg.items():
        if cat not in budget_cats or v < 50000:
            continue
        f = float(rng.uniform(0.95, 1.22))
        amt = int(round(v * f / 10000) * 10000)
        for mon in months:
            brows.append(dict(customer_id=int(c), month=mon, category=cat, amount_minor=amt))
    budgets = pd.DataFrame(brows)

    # ------------------------------------------------------------------ goals
    needs = exp[exp.need_want.isin(["need", "financial"])].groupby("customer_id").eff.sum() / 12.0
    goals = []
    gid = 1
    gnames = [("Laptop", "gadget", 40000, 120000), ("Trip", "travel", 30000, 150000), ("New phone", "gadget", 25000, 90000),
              ("Wedding fund", "event", 150000, 600000), ("Course / certification", "education", 20000, 100000)]
    for c in ids:
        inc = float(income[c])
        tgt = round(float(needs.get(c, inc * 100 * 0.3)) * 6 / 100000) * 100000
        goals.append(dict(goal_id=gid, customer_id=int(c), name="Emergency fund (6 months of needs)", kind="emergency",
                          target_minor=int(max(tgt, 3000000)), saved_minor=None, deadline="2027-03-31", linked_account_id=int(c * 10 + 2)))
        gid += 1
        for gi in rng.choice(len(gnames), size=int(rng.integers(0, 3)), replace=False):
            n, k, lo, hi = gnames[gi]
            target = round(float(rng.uniform(lo, hi)) * min(1.5, max(0.6, inc / 50000)) / 1000) * 1000 * 100
            goals.append(dict(goal_id=gid, customer_id=int(c), name=n, kind=k, target_minor=int(target),
                              saved_minor=int(target * float(rng.uniform(0.08, 0.75))),
                              deadline=(datetime(2026, 10, 1) + timedelta(days=int(rng.integers(150, 1000)))).strftime("%Y-%m-%d"),
                              linked_account_id=None))
            gid += 1
        if inc >= 100000 and rng.random() < 0.35:
            target = int(round(inc * float(rng.uniform(15, 40)), -4) * 100)
            goals.append(dict(goal_id=gid, customer_id=int(c), name="House down payment", kind="house", target_minor=target,
                              saved_minor=int(target * float(rng.uniform(0.1, 0.5))), deadline="2029-12-31", linked_account_id=None))
            gid += 1
    goals = pd.DataFrame(goals)

    # ------------------------------------------------------------------ customer profile
    monthly = t[(t.status == "posted") & (t.txn_type == "income")].groupby("customer_id").amount_minor.sum() / 12.0
    br = pd.DataFrame(T.DEFAULT_BRACKETS)

    def bracket(net_m):
        inr = net_m / 100
        for b in T.DEFAULT_BRACKETS:
            if b["min_inr"] <= inr < b["max_inr"]:
                return b["code"], b["mode"]
        return "B5", "advanced"

    prof = []
    for c in ids:
        code, mode = bracket(float(monthly.get(c, 0)))
        prof.append(dict(customer_id=int(c), income_profile=profile[c], primary_income_type=cust_itype[c],
                         avg_monthly_income_minor=int(monthly.get(c, 0)), bracket_code=code, preferred_mode=mode,
                         month_start_day=1, currency="INR"))
    profile_df = pd.DataFrame(prof)

    # ------------------------------------------------------------------ reference tables
    cat_rows = []
    for code, v in T.CATEGORIES.items():
        for sub, sl in v["subs"].items():
            cat_rows.append(dict(category=code, category_label=v["label"], grp=v["group"], need_want=v["nw"], subcategory=sub,
                                 subcategory_label=sl, fixed_default=sub in v["fixed"]))
    merch_rows = []
    for cat, lst in T.GEN_MERCHANTS.items():
        for i, (n, s) in enumerate(lst):
            merch_rows.append(dict(name=n, category=cat, subcategory=s))
    inc_types = pd.DataFrame([dict(code=k, label=v[0], cls=v[1]) for k, v in T.INCOME_TYPES.items()])
    brackets = pd.DataFrame([dict(code=b["code"], label=b["label"], min_inr=b["min_inr"], max_inr=b["max_inr"],
                                  default_mode=b["mode"], situation=b["situation"], emphasis="|".join(b["emphasis"]))
                             for b in T.DEFAULT_BRACKETS])

    # final column order for the ledger
    t = t.sort_values(["ts", "id"], kind="stable").reset_index(drop=True)
    log(f"finance layer: {len(t):,} ledger rows (+{len(tx_new):,} new), {len(accounts):,} accounts, {len(loans_df)} loans, "
        f"{len(holdings)} holdings, {len(rec)} recurring items, {len(budgets):,} budget rows, {len(goals)} goals")
    return {"transactions": t, "accounts": accounts, "categories": pd.DataFrame(cat_rows), "merchants": pd.DataFrame(merch_rows),
            "income_types": inc_types, "income_brackets": brackets, "loans": loans_df, "holdings": holdings,
            "holding_valuations": valuations, "recurring_items": rec, "budgets": budgets, "goals": goals,
            "customer_profile": profile_df}
