"""Personal-finance calculations with built-in explanations.

Every metric is returned as {key,label,value,kind,sub,tone,explain:{formula,inputs,meaning,reading,caveat}} so the UI
can show exactly how a number was produced on click. Money is integer paise (strings in JSON). Periods are calendar
months in Asia/Kolkata. 'As of' = the end of the data (or later if the customer added newer entries).
"""
from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.finance import taxonomy as T
from app.ml.generator import DAY, ORIGIN_TS
from app.services.spending import CREDITS, GROSS, INCOME, effective

IST = timezone(timedelta(hours=5, minutes=30))
DATA_END_TS = ORIGIN_TS + 365 * DAY
ASSET_KINDS = ("bank", "savings", "cash")
NEED_GROUPS = {"need", "financial"}
WANT_GROUPS = {"want", "social"}


# ------------------------------------------------------------------------------------------------ small helpers
def mkey(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), IST).strftime("%Y-%m")


def month_bounds(m: str) -> tuple[int, int]:
    y, mo = map(int, m.split("-"))
    s = datetime(y, mo, 1, tzinfo=IST)
    e = datetime(y + (mo == 12), mo % 12 + 1, 1, tzinfo=IST)
    return int(s.timestamp()), int(e.timestamp())


def shift_month(m: str, d: int) -> str:
    y, mo = map(int, m.split("-"))
    k = y * 12 + mo - 1 + d
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def month_label(m: str) -> str:
    y, mo = map(int, m.split("-"))
    return f"{calendar.month_abbr[mo]} {y}"


def days_in(m: str) -> int:
    y, mo = map(int, m.split("-"))
    return calendar.monthrange(y, mo)[1]


def M(v) -> str:
    return str(int(round(float(v))))


def inp(label: str, value, kind: str = "money") -> dict:
    return {"label": label, "value": (M(value) if kind == "money" and value is not None else value), "kind": kind}


def E(key, label, value, kind, formula, inputs, meaning, reading, caveat=None, sub=None, tone=None) -> dict:
    if kind == "money" and value is not None:
        value = M(value)
    return {"key": key, "label": label, "value": value, "kind": kind, "sub": sub, "tone": tone,
            "explain": {"formula": formula, "inputs": inputs, "meaning": meaning, "reading": reading, "caveat": caveat}}


def pct(a: float, b: float) -> float | None:
    return (100.0 * a / b) if b else None


def nw_of(cat) -> str | None:
    c = T.CATEGORIES.get(cat) if isinstance(cat, str) else None
    return c["nw"] if c else None


def lbl_cat(cat) -> str:
    c = T.CATEGORIES.get(cat) if isinstance(cat, str) else None
    return c["label"] if c else (cat or "Uncategorised")


def lbl_sub(cat, sub) -> str | None:
    return T.sub_label(cat, sub) if isinstance(sub, str) else None


# ------------------------------------------------------------------------------------------------ context
@dataclass
class Ctx:
    cid: int
    tx: pd.DataFrame          # raw ledger for the customer (posted+other statuses), not voided
    led: pd.DataFrame         # effective, posted, with helper columns
    accounts: pd.DataFrame
    loans: pd.DataFrame
    holdings: pd.DataFrame
    vals: pd.DataFrame
    rec: pd.DataFrame
    budgets: pd.DataFrame
    goals: pd.DataFrame
    profile: dict
    as_of_ts: int
    month: str


def build_ctx(s, cid: int, month: str | None = None) -> Ctx:
    raw = s.by_cust[cid]
    if "voided" in raw.columns:
        raw = raw[~raw.voided.fillna(False).astype(bool)]
    eff = effective(raw)
    led = eff[eff.status == "posted"].copy()
    led["month"] = pd.to_datetime(led.posted_ts, unit="s", utc=True).dt.tz_convert(IST).dt.strftime("%Y-%m")
    led["nw"] = led.category.map(nw_of)
    led["sx"] = np.where(led.purpose.isin(GROSS), led.amount_minor, np.where(led.purpose.isin(CREDITS), -led.amount_minor, 0))
    fin = s.fin
    g = lambda name: fin[name].get(cid, fin["_empty"][name])
    last_ts = int(led.posted_ts.max()) if len(led) else DATA_END_TS
    as_of = max(DATA_END_TS, last_ts + 1)
    m = month or mkey(as_of - 1)
    return Ctx(cid, raw, led, g("accounts"), g("loans"), g("holdings"), g("vals"), g("rec"), g("budgets"), g("goals"),
               fin["profile"].get(cid, {}), as_of, m)


# ------------------------------------------------------------------------------------------------ monthly table
def month_table(led: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar month with every building block used by the headline metrics."""
    if led.empty:
        return pd.DataFrame()
    g = led.groupby("month")
    cols = {}
    cols["income_net"] = led[led.purpose.isin(INCOME)].groupby("month").amount_minor.sum()
    gross = led[led.purpose.isin(INCOME)]
    cols["income_gross"] = gross.assign(gv=gross.gross_minor.fillna(gross.amount_minor)).groupby("month").gv.sum()
    cols["gross_spend"] = led[led.purpose.isin(GROSS)].groupby("month").amount_minor.sum()
    cols["credits"] = led[led.purpose.isin(CREDITS)].groupby("month").amount_minor.sum()
    cols["needs"] = led[led.nw.isin(NEED_GROUPS)].groupby("month").sx.sum()
    cols["wants"] = led[led.nw.isin(WANT_GROUPS)].groupby("month").sx.sum()
    cols["debt_principal"] = led[led.purpose == "loan_principal"].groupby("month").amount_minor.sum()
    cols["invest"] = led[led.purpose == "investment_contribution"].groupby("month").amount_minor.sum()
    ext = led[(led.purpose == "external_transfer") & (led.direction == "debit")]
    cols["unclassified"] = ext.groupby("month").amount_minor.sum()
    emi = led[(led.category == "debt_emi") & led.purpose.isin(["loan_principal", "interest_expense"])]
    cols["emi_total"] = emi.groupby("month").amount_minor.sum()
    df = pd.DataFrame(cols).fillna(0.0)
    df["net_spend"] = df.gross_spend - df.credits
    df = df.reindex(sorted(df.index))
    return df


def row_for(mt: pd.DataFrame, m: str) -> pd.Series:
    if m in mt.index:
        return mt.loc[m]
    return pd.Series({c: 0.0 for c in mt.columns}) if len(mt.columns) else pd.Series(dtype=float)


def trailing(mt: pd.DataFrame, m: str, col: str, n: int = 3) -> tuple[float, int]:
    """Average of `col` over up to n months ending at m (only months that have data)."""
    months = [shift_month(m, -i) for i in range(n)]
    vals = [float(mt.at[x, col]) for x in months if x in mt.index]
    return (sum(vals) / len(vals), len(vals)) if vals else (0.0, 0)


# ------------------------------------------------------------------------------------------------ balances
def flows_by_account(c: Ctx) -> pd.DataFrame:
    p = c.tx[(c.tx.status == "posted")].sort_values("posted_ts")
    return p.assign(f=np.where(p.direction == "credit", 1, -1) * p.amount_minor)


def balances(c: Ctx, at_ts: float | None = None) -> pd.DataFrame:
    """Asset accounts: opening + credits - debits. Credit card: liability = debits - credits (opening 0)."""
    p = flows_by_account(c)
    if at_ts is not None:
        p = p[p.posted_ts < at_ts]
    flow = p.groupby("account_id").f.sum()
    credits = p[p.direction == "credit"].groupby("account_id").amount_minor.sum()
    debits = p[p.direction == "debit"].groupby("account_id").amount_minor.sum()
    a = c.accounts.copy()
    a["credits"] = a.account_id.map(credits).fillna(0)
    a["debits"] = a.account_id.map(debits).fillna(0)
    a["flow"] = a.account_id.map(flow).fillna(0)
    a["balance"] = np.where(a.kind == "credit_card", a.debits - a.credits, a.opening_minor + a.flow)
    return a


def loan_state(l, at_ts: float) -> dict:
    """Payments made and outstanding principal at a moment, from the loan's amortisation schedule."""
    fy, fm, _ = map(int, l.first_emi_date.split("-"))
    t = datetime.fromtimestamp(at_ts, IST)
    n = (t.year * 12 + t.month) - (fy * 12 + fm) + (1 if t.day >= l.pay_day else 0)
    n = max(0, min(int(l.tenure_months), n))
    r = l.rate_pct / 1200 if l.rate_pct else 0.0
    P, emi = float(l.principal_minor), float(l.emi_minor)
    if r == 0:
        out = max(0.0, P - emi * n)
    else:
        out = max(0.0, P * (1 + r) ** n - emi * ((1 + r) ** n - 1) / r)
    return {"paid": n, "left": int(l.tenure_months) - n, "outstanding": out}


def loan_end_date(l) -> str:
    fy, fm, _ = map(int, l.first_emi_date.split("-"))
    k = fy * 12 + fm - 1 + int(l.tenure_months) - 1
    return f"{k // 12:04d}-{k % 12 + 1:02d}-{l.pay_day:02d}"


def holdings_value(c: Ctx, m: str) -> tuple[float, float]:
    """(current value, invested) at the latest valuation month <= m."""
    if c.vals.empty:
        return 0.0, 0.0
    v = c.vals[c.vals.month <= m]
    if v.empty:
        return 0.0, 0.0
    last = v.sort_values("month").groupby("holding_id").tail(1)
    return float(last.value_minor.sum()), float(last.invested_cum_minor.sum())


def net_worth_at(c: Ctx, m: str, flows: pd.DataFrame | None = None) -> dict:
    s, e = month_bounds(m)
    b = balances(c, e)
    liquid = float(b[b.kind.isin(ASSET_KINDS)].balance.sum())
    cards = float(b[b.kind == "credit_card"].balance.sum())
    inv_val, inv_cost = holdings_value(c, m)
    loan = sum(loan_state(l, e - 1)["outstanding"] for l in c.loans.itertuples()) if len(c.loans) else 0.0
    return {"liquid": liquid, "investments": inv_val, "invested": inv_cost, "cards": cards, "loans": loan,
            "assets": liquid + inv_val, "liabilities": cards + loan, "net_worth": liquid + inv_val - cards - loan}


# ------------------------------------------------------------------------------------------------ profile / bracket
def bracket_for(s, c: Ctx) -> dict:
    inr = c.profile.get("avg_monthly_income_minor", 0) / 100
    br = s.fin["brackets"]
    for r in br.itertuples():
        if r.min_inr <= inr < r.max_inr:
            return {"code": r.code, "label": r.label, "situation": r.situation, "emphasis": r.emphasis.split("|"),
                    "default_mode": r.default_mode}
    r = br.iloc[-1]
    return {"code": r.code, "label": r.label, "situation": r.situation, "emphasis": r.emphasis.split("|"), "default_mode": r.default_mode}


# ------------------------------------------------------------------------------------------------ overview
def overview(s, c: Ctx) -> dict:
    mt = month_table(c.led)
    m = c.month
    cur = row_for(mt, m)
    prev_m = shift_month(m, -1)
    prev = row_for(mt, prev_m)
    s_ts, e_ts = month_bounds(m)
    inc, gross_inc = float(cur.get("income_net", 0)), float(cur.get("income_gross", 0))
    g_sp, cred, net_sp = (float(cur.get(k, 0)) for k in ("gross_spend", "credits", "net_spend"))
    deductions = gross_inc - inc
    left = inc - net_sp
    rate = pct(left, inc)
    needs, wants = float(cur.get("needs", 0)) + float(cur.get("debt_principal", 0)), float(cur.get("wants", 0))
    unclassified, invest, debt_pr = float(cur.get("unclassified", 0)), float(cur.get("invest", 0)), float(cur.get("debt_principal", 0))
    save_split = inc - needs - wants
    metrics: list[dict] = []

    metrics.append(E("income", "Income received", inc, "money",
                     "Income received = salary + other earnings + interest credited to your accounts in the month",
                     [inp("Income received (net)", inc), inp("Before deductions (gross)", gross_inc),
                      inp("Tax / PF / other deductions", deductions)],
                     "The money that actually reached your accounts this month (net pay). Gross pay is higher; the difference "
                     "is tax, provident fund and other deductions taken before you are paid.",
                     "Compare with spending below. For irregular income see the Income page, which shows a monthly average.",
                     caveat="Transfers between your own accounts, refunds and loans are not income.",
                     sub=f"Gross ₹{gross_inc / 100:,.0f} before deductions", tone="blue"))
    metrics.append(E("gross_spending", "Gross spending", g_sp, "money",
                     "Gross spending = purchases + fees + loan interest (all debits that are real expenses)",
                     [inp("Gross spending", g_sp), inp("Number of expense debits", int((c.led[(c.led.month == m) & c.led.purpose.isin(GROSS)]).shape[0]), "count")],
                     "Everything you paid for in the month before any refund is taken off.",
                     "This is what left your accounts for goods and services. It excludes moving money between your own accounts, "
                     "ATM withdrawals (the later cash purchase counts), credit-card bill payments (the original card purchases "
                     "count), SIP/investments, and the principal part of loan EMIs.",
                     caveat="Unclassified transfers to other people are not counted until you say what they were for."))
    metrics.append(E("refunds", "Expense credits (refunds)", cred, "money",
                     "Expense credits = refunds + reversals posted in the month",
                     [inp("Refunds and reversals", cred), inp("As % of gross spending", pct(cred, g_sp), "pct")],
                     "Money that came back for earlier purchases.",
                     "A refund lowers the month it is posted, not the month of the original purchase."))
    metrics.append(E("net_spending", "Net spending", net_sp, "money",
                     "Net spending = gross spending − expense credits",
                     [inp("Gross spending", g_sp), inp("− Expense credits", cred), inp("= Net spending", net_sp)],
                     "What you really spent after refunds. This is the number used for savings rate and budgets.",
                     "If it exceeds income you are spending more than you earn this month.", tone="coral"))
    metrics.append(E("money_left", "Money left after expenses", left, "money",
                     "Money left = income − net spending",
                     [inp("Income received", inc), inp("− Net spending", net_sp), inp("= Money left", left)],
                     "What remains after your expenses. It is split between investments, loan principal, transfers still to be "
                     "classified, and plain leftover cash.",
                     "Positive is good. Negative means you used savings or borrowed.",
                     caveat="It is a budgeting figure, not your bank balance change."))
    metrics.append(E("savings_rate", "Savings rate", rate, "pct",
                     "Savings rate = (income − expenses) ÷ income × 100",
                     [inp("Income received", inc), inp("Net spending", net_sp), inp("Money left", left),
                      inp("Savings rate", rate, "pct")],
                     "The share of income you keep after expenses.",
                     "20% or more is a healthy target; 10–20% is okay; under 10% leaves little cushion. Negative means overspending.",
                     caveat=None if inc > 0 else "Not available: no income was received this month, so a rate cannot be computed.",
                     sub=("Not available (no income this month)" if rate is None else None)))

    # 50/30/20
    def share(x):
        return pct(x, inc)
    split = {"needs": {"amount": M(needs), "pct": share(needs), "benchmark": 50},
             "wants": {"amount": M(wants), "pct": share(wants), "benchmark": 30},
             "savings": {"amount": M(save_split), "pct": share(save_split), "benchmark": 20}}
    metrics.append(E("needs_wants_savings", "Needs / wants / savings", save_split, "money",
                     "Needs = essential spending + loan principal repaid;  Wants = lifestyle + social spending;  "
                     "Savings = income − needs − wants",
                     [inp("Needs (essential spending)", needs - debt_pr), inp("+ Loan principal repaid", debt_pr),
                      inp("= Needs", needs), inp("Wants (lifestyle + social)", wants), inp("Savings (remainder)", save_split),
                      inp("of which investments", invest), inp("of which unclassified transfers out", unclassified)],
                     "Compares your split with the 50 / 30 / 20 rule of thumb: about 50% needs, 30% wants, 20% savings.",
                     "Higher needs than 50% means essentials are squeezing you; wants above 30% is where to trim first.",
                     caveat="Savings is a remainder, so it also contains leftover cash and transfers you have not yet classified."))

    # runway / burn / emergency
    burn, nb = trailing(mt, m, "net_spend", 3)
    dp_avg, _ = trailing(mt, m, "debt_principal", 3)
    burn_total = burn + dp_avg
    b_end = balances(c, e_ts)
    liquid = float(b_end[b_end.kind.isin(ASSET_KINDS)].balance.sum())
    runway = (liquid / burn_total) if burn_total > 0 else None
    metrics.append(E("burn_rate", "Burn rate", burn_total, "money",
                     "Burn rate = average monthly (net spending + loan principal) over the last 3 months",
                     [inp(f"Avg net spending ({nb} month{'s' if nb != 1 else ''})", burn), inp("Avg loan principal", dp_avg),
                      inp("= Burn rate per month", burn_total)],
                     "How much money you go through each month to live and pay your debts.",
                     "Use it to judge how long your savings would last."))
    metrics.append(E("runway", "Runway", None if runway is None else round(runway, 1), "months",
                     "Runway (months) = cash in bank + savings + wallet ÷ burn rate",
                     [inp("Liquid money (bank + savings + cash)", liquid), inp("÷ Burn rate per month", burn_total),
                      inp("= Months of runway", None if runway is None else round(runway, 1), "months")],
                     "How many months you could keep living at your current pace if income stopped today.",
                     "Under 3 months is thin; 3–6 months is solid; over 6 months is a strong cushion.",
                     caveat=None if burn_total > 0 else "Not available: no spending recorded in the last 3 months."))
    sav_acc = b_end[b_end.kind == "savings"]
    ef = float(sav_acc.balance.sum())
    needs_avg, _ = trailing(mt, m, "needs", 3)
    needs_avg_all = needs_avg + dp_avg
    cov = (ef / needs_avg_all) if needs_avg_all > 0 else None
    cov_status = None if cov is None else ("Below 3 months: build this first" if cov < 3 else "On target (3–6 months)" if cov <= 6 else "Strong (over 6 months)")
    metrics.append(E("emergency_cover", "Emergency fund cover", None if cov is None else round(cov, 1), "months",
                     "Emergency fund cover = savings-account balance ÷ average monthly essential spending (3 months)",
                     [inp("Savings account balance", ef), inp("÷ Avg monthly essentials (needs + loan principal)", needs_avg_all),
                      inp("= Months covered", None if cov is None else round(cov, 1), "months")],
                     "How many months of essential bills your emergency savings could pay.",
                     "Target 3–6 months. Self-employed or irregular earners should aim for the top of that range.",
                     sub=cov_status))

    # DTI
    emi_avg, _ = trailing(mt, m, "emi_total", 3)
    cards_out = float(b_end[b_end.kind == "credit_card"].balance.sum())
    card_min = max(0.0, 0.05 * cards_out)
    gross_avg, _ = trailing(mt, m, "income_gross", 3)
    dti = pct(emi_avg + card_min, gross_avg)
    metrics.append(E("dti", "Debt-to-income ratio", dti, "pct",
                     "Debt-to-income = (monthly EMIs + credit-card minimum due) ÷ gross monthly income × 100",
                     [inp("Avg monthly EMIs (3 months)", emi_avg), inp("+ Card minimum due (5% of outstanding)", card_min),
                      inp("÷ Avg gross monthly income (3 months)", gross_avg), inp("= Debt-to-income", dti, "pct")],
                     "The share of your pre-tax income that goes to debt repayments.",
                     "Under 20% is comfortable; 20–35% is manageable; above 40% is considered stressed by most lenders.",
                     caveat=None if gross_avg > 0 else "Not available: no income in the last 3 months."))

    # net worth
    nwm = net_worth_at(c, m)
    metrics.append(E("net_worth", "Net worth", nwm["net_worth"], "money",
                     "Net worth = assets − liabilities,  where assets = bank + savings + cash + investments  and  "
                     "liabilities = credit-card dues + loan principal outstanding",
                     [inp("Bank + savings + cash", nwm["liquid"]), inp("+ Investments (current value)", nwm["investments"]),
                      inp("= Assets", nwm["assets"]), inp("Credit-card outstanding", nwm["cards"]),
                      inp("+ Loan principal outstanding", nwm["loans"]), inp("= Liabilities", nwm["liabilities"]),
                      inp("Net worth", nwm["net_worth"])],
                     "What you would own after paying off everything you owe, at the end of the month.",
                     "Watch the trend over months rather than the single number; it should rise over time.",
                     caveat="Home or vehicle value is not included.", tone="blue"))

    # budgets & safe to spend
    bud = budget_status(c, m)
    days_left = max(1, days_in(m) - (datetime.fromtimestamp(c.as_of_ts - 1, IST).day if m == mkey(c.as_of_ts - 1) else days_in(m)) + 1)
    remaining = max(0.0, bud["total_budget"] - bud["total_spent"])
    safe = remaining / days_left
    metrics.append(E("safe_to_spend", "Safe to spend today", safe, "money",
                     "Safe to spend = (total budget − spent in budgeted categories) ÷ days left in the month",
                     [inp("Total budget this month", bud["total_budget"]), inp("− Spent in budgeted categories", bud["total_spent"]),
                      inp("= Budget remaining", remaining), inp("÷ Days left (including today)", days_left, "count"),
                      inp("= Per day", safe)],
                     "A simple daily allowance that keeps you inside your monthly budgets.",
                     "If you spend less than this today, tomorrow's allowance grows.",
                     caveat="Based on your category budgets, which include fixed bills already paid, so it is a conservative guide."))

    # categories with trends
    cats = category_table(c, m)
    series = []
    for x in [shift_month(m, -i) for i in range(11, -1, -1)]:
        r = row_for(mt, x) if x in mt.index else None
        if r is None:
            series.append({"month": x, "label": month_label(x), "income": None, "expenses": None, "savings_rate": None, "net_worth": None})
            continue
        ii, nn = float(r["income_net"]), float(r["net_spend"])
        series.append({"month": x, "label": month_label(x), "income": M(ii), "expenses": M(nn),
                       "savings_rate": pct(ii - nn, ii), "net_worth": M(net_worth_at(c, x)["net_worth"])})
    unresolved = c.led[(c.led.purpose == "external_transfer") & (c.led.direction == "debit") & (c.led.month == m)]
    return {
        "customer_id": c.cid, "month": m, "month_label": month_label(m), "as_of_ts": c.as_of_ts,
        "available_months": [x for x in mt.index], "bracket": bracket_for(s, c), "profile": c.profile,
        "metrics": metrics, "split": split, "categories": cats, "series": series,
        "budget_summary": {k: bud[k] if not isinstance(bud[k], float) else M(bud[k]) for k in ("n_over", "n_near", "n_ok")}
        | {"total_budget": M(bud["total_budget"]), "total_spent": M(bud["total_spent"]), "used_pct": bud["used_pct"]},
        "to_classify": {"count": int(len(unresolved)), "amount": M(unresolved.amount_minor.sum())},
    }


# ------------------------------------------------------------------------------------------------ categories
def category_table(c: Ctx, m: str) -> list[dict]:
    s_ts, e_ts = month_bounds(m)
    led = c.led
    cur = led[(led.month == m) & led.purpose.isin(GROSS | CREDITS) & led.category.notna()]
    prev_m, ly_m = shift_month(m, -1), shift_month(m, -12)
    first_month = led.month.min() if len(led) else m
    gross_total = float(cur[cur.purpose.isin(GROSS)].amount_minor.sum())
    rows = []
    for cat, g in cur.groupby("category"):
        gr = float(g[g.purpose.isin(GROSS)].amount_minor.sum())
        cr = float(g[g.purpose.isin(CREDITS)].amount_minor.sum())
        net = gr - cr
        pm = led[(led.month == prev_m) & (led.category == cat)].sx.sum()
        ly = led[(led.month == ly_m) & (led.category == cat)].sx.sum()
        d_prev = None if pm == 0 else 100.0 * (net - pm) / abs(pm)
        ly_ok = first_month <= ly_m
        d_ly = None if (not ly_ok or ly == 0) else 100.0 * (net - ly) / abs(ly)
        rows.append({
            "category": cat, "label": lbl_cat(cat), "group": (T.CATEGORIES.get(cat) or {}).get("group", "Other"),
            "need_want": nw_of(cat), "gross": M(gr), "credits": M(cr), "net": M(net),
            "share_of_gross": pct(gr, gross_total), "count": int(len(g)), "prev_net": M(pm), "vs_prev_pct": d_prev,
            "vs_prev_reason": None if d_prev is not None else "no spending in this category last month",
            "vs_last_year_pct": d_ly,
            "vs_last_year_reason": None if d_ly is not None else (f"history starts {month_label(first_month)}" if not ly_ok else "no spending a year ago"),
            "explain": {
                "formula": "Category net = gross spent in the category − refunds for that category.  "
                           "Share of gross = category gross ÷ total gross spending × 100.",
                "inputs": [inp("Gross spent", gr), inp("− Refunds", cr), inp("= Net", net), inp("Transactions", len(g), "count"),
                           inp("Share of all gross spending", pct(gr, gross_total), "pct"), inp("Last month (net)", pm),
                           inp("Change vs last month", d_prev, "pct")],
                "meaning": f"How much you spent on {lbl_cat(cat).lower()} in {month_label(m)}.",
                "reading": "A refund reduces the category in the month it is received. The % change compares with the previous "
                           "month; a year-on-year comparison appears only once there is a year of history.",
                "caveat": None}})
    rows.sort(key=lambda r: -int(r["net"]))
    return rows


def category_detail(c: Ctx, m: str, cat: str) -> dict:
    led = c.led
    g = led[(led.month == m) & (led.category == cat) & led.purpose.isin(GROSS | CREDITS)]
    sub = []
    for sc, x in g.groupby(g.subcategory.fillna("other")):
        sub.append({"subcategory": sc, "label": lbl_sub(cat, sc) or "Other", "net": M(x.sx.sum()), "count": int(len(x))})
    mer = []
    for name, x in g[g.purpose.isin(GROSS)].groupby(g.merchant_name.fillna("Other")):
        mer.append({"merchant": name, "total": M(x.amount_minor.sum()), "count": int(len(x))})
    return {"category": cat, "label": lbl_cat(cat), "month": m, "subcategories": sorted(sub, key=lambda r: -int(r["net"])),
            "merchants": sorted(mer, key=lambda r: -int(r["total"]))[:8]}


# ------------------------------------------------------------------------------------------------ budgets
def budget_status(c: Ctx, m: str) -> dict:
    b = c.budgets[c.budgets.month == m] if len(c.budgets) else c.budgets
    led = c.led[(c.led.month == m) & c.led.purpose.isin(GROSS | CREDITS)]
    spent = led.groupby("category").sx.sum()
    rows = []
    for r in b.itertuples():
        sp = float(spent.get(r.category, 0))
        used = pct(sp, r.amount_minor)
        status = "over" if used is not None and used >= 100 else "near" if used is not None and used >= 80 else "ok"
        rows.append({"category": r.category, "label": lbl_cat(r.category), "budget": M(r.amount_minor), "spent": M(sp),
                     "remaining": M(r.amount_minor - sp), "used_pct": used, "status": status,
                     "explain": {
                         "formula": "Used % = net spending in the category ÷ monthly budget × 100;  Remaining = budget − net spending",
                         "inputs": [inp("Monthly budget", r.amount_minor), inp("Net spent so far", sp), inp("Remaining", r.amount_minor - sp),
                                    inp("Used", used, "pct")],
                         "meaning": f"Your {lbl_cat(r.category).lower()} limit for {month_label(m)}.",
                         "reading": "Amber at 80% and red at 100% of the budget. Refunds in the category lower what counts as spent.",
                         "caveat": None}})
    tb = float(sum(float(x["budget"]) for x in rows))
    ts_ = float(sum(float(x["spent"]) for x in rows))
    return {"rows": sorted(rows, key=lambda r: -(r["used_pct"] or 0)), "total_budget": tb, "total_spent": ts_,
            "used_pct": pct(ts_, tb), "n_over": sum(r["status"] == "over" for r in rows),
            "n_near": sum(r["status"] == "near" for r in rows), "n_ok": sum(r["status"] == "ok" for r in rows)}


# ------------------------------------------------------------------------------------------------ accounts
def accounts_view(c: Ctx) -> dict:
    b = balances(c, c.as_of_ts)
    rows = []
    for a in b.itertuples():
        if a.kind == "credit_card":
            lim = float(a.credit_limit_minor or 0)
            out = float(a.balance)
            util = pct(out, lim)
            ex = {"formula": "Amount owed = card purchases − payments and refunds;  Utilisation = amount owed ÷ credit limit × 100",
                  "inputs": [inp("Card purchases", a.debits), inp("− Payments and refunds", a.credits), inp("= Amount owed", out),
                             inp("Credit limit", lim), inp("Utilisation", util, "pct"), inp("Minimum due (5%)", max(0, 0.05 * out))],
                  "meaning": "What you currently owe on this card.",
                  "reading": "Keep utilisation under 30% to protect your credit score. Pay the full amount before the due date to avoid interest.",
                  "caveat": None}
            rows.append({"account_id": int(a.account_id), "kind": a.kind, "name": a.name, "institution": a.institution,
                         "masked_ref": a.masked_ref, "balance": M(-out), "owed": M(out), "limit": M(lim), "utilisation": util, "explain": ex})
        else:
            ex = {"formula": "Balance = opening balance + money in − money out (posted entries only)",
                  "inputs": [inp("Opening balance", a.opening_minor), inp("+ Money in", a.credits), inp("− Money out", a.debits),
                             inp("= Balance", a.balance)],
                  "meaning": f"What is in your {a.name.lower()} as of the latest entry.",
                  "reading": "Money in/out includes transfers between your own accounts, which cancel when you look at all accounts together.",
                  "caveat": "Pending and failed entries are ignored."}
            rows.append({"account_id": int(a.account_id), "kind": a.kind, "name": a.name, "institution": a.institution,
                         "masked_ref": a.masked_ref, "balance": M(a.balance), "money_in": M(a.credits), "money_out": M(a.debits),
                         "purpose": a.purpose, "explain": ex})
    nw = net_worth_at(c, mkey(c.as_of_ts - 1))
    return {"accounts": rows, "totals": {k: M(v) for k, v in nw.items()}}


# ------------------------------------------------------------------------------------------------ debts
def debts_view(c: Ctx) -> dict:
    out = []
    for l in c.loans.itertuples():
        st = loan_state(l, c.as_of_ts)
        r = l.rate_pct / 1200 if l.rate_pct else 0.0
        remaining_interest = max(0.0, l.emi_minor * st["left"] - st["outstanding"])
        out.append({
            "loan_id": int(l.loan_id), "name": l.name, "kind": l.kind, "lender": l.lender, "rate_pct": l.rate_pct,
            "principal": M(l.principal_minor), "emi": M(l.emi_minor), "tenure_months": int(l.tenure_months),
            "paid": st["paid"], "left": st["left"], "outstanding": M(st["outstanding"]),
            "payoff_date": loan_end_date(l), "next_due_day": int(l.pay_day), "remaining_interest": M(remaining_interest),
            "progress_pct": pct(st["paid"], l.tenure_months),
            "explain": {
                "formula": "EMI split each month: interest = outstanding × rate ÷ 12;  principal = EMI − interest;  "
                           "outstanding after n EMIs = P(1+r)ⁿ − EMI × ((1+r)ⁿ − 1) ÷ r  (r = monthly rate)",
                "inputs": [inp("Original loan amount", l.principal_minor), inp("Interest rate (per year)", l.rate_pct, "pct"),
                           inp("Monthly EMI", l.emi_minor), inp("EMIs paid", st["paid"], "count"), inp("EMIs left", st["left"], "count"),
                           inp("Principal still owed", st["outstanding"]), inp("Interest still to pay (approx.)", remaining_interest),
                           inp("Last EMI on", loan_end_date(l), "text")],
                "meaning": "How much of this loan you still owe and when it will be fully paid.",
                "reading": "Early EMIs are mostly interest; later ones are mostly principal. Prepaying principal shortens the loan and saves interest.",
                "caveat": "In your spending only the interest part of an EMI counts as an expense; the principal part reduces what you owe."}})
    b = balances(c, c.as_of_ts)
    cards = []
    for a in b[b.kind == "credit_card"].itertuples():
        owed = float(a.balance)
        cards.append({"account_id": int(a.account_id), "name": a.name, "institution": a.institution, "owed": M(owed),
                      "limit": M(a.credit_limit_minor), "utilisation": pct(owed, a.credit_limit_minor), "apr_pct": a.apr_pct,
                      "min_due": M(max(0.0, 0.05 * owed)), "due_day": 10})
    total_out = sum(int(x["outstanding"]) for x in out) + sum(int(x["owed"]) for x in cards)
    return {"loans": out, "cards": cards, "total_owed": M(total_out),
            "monthly_emi": M(sum(int(x["emi"]) for x in out))}


def loan_schedule(c: Ctx, loan_id: int, limit: int = 400) -> dict:
    l = c.loans[c.loans.loan_id == loan_id]
    if l.empty:
        return {}
    l = next(l.itertuples())
    r = l.rate_pct / 1200 if l.rate_pct else 0.0
    P, emi = float(l.principal_minor), float(l.emi_minor)
    fy, fm, _ = map(int, l.first_emi_date.split("-"))
    bal = P
    rows = []
    for n in range(1, int(l.tenure_months) + 1):
        interest = bal * r
        princ = min(emi - interest, bal)
        bal = max(0.0, bal - princ)
        k = fy * 12 + fm - 1 + n - 1
        rows.append({"n": n, "date": f"{k // 12:04d}-{k % 12 + 1:02d}-{l.pay_day:02d}", "emi": M(emi), "principal": M(princ),
                     "interest": M(interest), "balance": M(bal)})
    return {"loan_id": loan_id, "name": l.name, "rows": rows[:limit], "paid": loan_state(l, c.as_of_ts)["paid"]}


# ------------------------------------------------------------------------------------------------ investments
def investments_view(c: Ctx) -> dict:
    m = mkey(c.as_of_ts - 1)
    rows = []
    cur_total = inv_total = 0.0
    alloc: dict[str, float] = {}
    if len(c.holdings):
        last = c.vals[c.vals.month <= m].sort_values("month").groupby("holding_id").tail(1).set_index("holding_id") if len(c.vals) else None
        first = c.vals.sort_values("month").groupby("holding_id").head(1).set_index("holding_id") if len(c.vals) else None
        for h in c.holdings.itertuples():
            v = float(last.at[h.holding_id, "value_minor"]) if last is not None and h.holding_id in last.index else float(h.current_value_minor)
            invested = float(last.at[h.holding_id, "invested_cum_minor"]) if last is not None and h.holding_id in last.index else float(h.invested_minor)
            ret = v - invested
            ret_pct = pct(ret, invested)
            cur_total += v
            inv_total += invested
            alloc[h.asset_class] = alloc.get(h.asset_class, 0.0) + v
            rows.append({"holding_id": int(h.holding_id), "name": h.name, "kind": h.kind, "asset_class": h.asset_class,
                         "sip": M(h.sip_minor), "invested": M(invested), "value": M(v), "gain": M(ret), "return_pct": ret_pct,
                         "tax_80c": bool(h.tax_80c),
                         "explain": {
                             "formula": "Gain = current value − amount invested;  Return % = gain ÷ amount invested × 100;  "
                                        "Value each month = last month's value × (1 + that month's market return) + new SIP",
                             "inputs": [inp("Monthly SIP", h.sip_minor), inp("Total invested", invested), inp("Current value", v),
                                        inp("Gain / loss", ret), inp("Return", ret_pct, "pct")],
                             "meaning": "How this holding has performed since you started investing in it.",
                             "reading": "This is a simple return on money invested (not annualised). Equity moves up and down month to month.",
                             "caveat": "Synthetic market returns, for demonstration only."}})
    series = []
    if len(c.vals):
        tot = c.vals.groupby("month").agg(value=("value_minor", "sum"), invested=("invested_cum_minor", "sum")).reset_index()
        series = [{"month": r.month, "label": month_label(r.month), "value": M(r.value), "invested": M(r.invested)} for r in tot.itertuples()]
    return {"holdings": rows, "totals": {"value": M(cur_total), "invested": M(inv_total), "gain": M(cur_total - inv_total),
                                         "return_pct": pct(cur_total - inv_total, inv_total)},
            "allocation": [{"asset_class": k, "value": M(v), "share_pct": pct(v, cur_total)} for k, v in sorted(alloc.items(), key=lambda kv: -kv[1])],
            "series": series}


# ------------------------------------------------------------------------------------------------ income
def income_view(c: Ctx, m: str) -> dict:
    led = c.led[c.led.purpose.isin(INCOME)].copy()
    led["g"] = led.gross_minor.fillna(led.amount_minor)
    last12 = [shift_month(m, -i) for i in range(11, -1, -1)]
    led12 = led[led.month.isin(last12)]
    by_month = []
    for x in last12:
        r = led12[led12.month == x]
        by_month.append({"month": x, "label": month_label(x), "net": M(r.amount_minor.sum()), "gross": M(r.g.sum())})
    nets = np.array([float(b["net"]) for b in by_month if float(b["net"]) > 0])
    avg12 = float(nets.mean()) if len(nets) else 0.0
    cv = float(nets.std() / nets.mean()) if len(nets) > 1 and nets.mean() > 0 else 0.0
    types = []
    for it, x in led12.groupby("income_type"):
        info = T.INCOME_TYPES.get(it, (it, "Other"))
        types.append({"income_type": it, "label": info[0], "class": info[1], "net": M(x.amount_minor.sum()), "gross": M(x.g.sum()),
                      "deductions": M(x.g.sum() - x.amount_minor.sum()), "count": int(len(x)),
                      "explain": {"formula": "Net = what reached your account;  Gross = net + tax + PF + other deductions",
                                  "inputs": [inp("Gross", x.g.sum()), inp("− Tax (TDS)", x.tds_minor.fillna(0).sum()),
                                             inp("− Provident fund", x.pf_minor.fillna(0).sum()),
                                             inp("− Other deductions", x.other_ded_minor.fillna(0).sum()), inp("= Net received", x.amount_minor.sum()),
                                             inp("Payments received", len(x), "count")],
                                  "meaning": f"Income from {info[0].lower()} in the last 12 months.",
                                  "reading": "Gross is what your employer or client agreed; net is what you can spend.", "caveat": None}})
    types.sort(key=lambda r: -int(r["net"]))
    stability = "Very steady" if cv < 0.1 else "Somewhat variable" if cv < 0.3 else "Irregular"
    tot_net, tot_gross = float(led12.amount_minor.sum()), float(led12.g.sum())
    metrics = [
        E("avg_income", "Monthly average income (12 months)", avg12, "money",
          "Monthly average = total net income of the last 12 months ÷ months with income",
          [inp("Total net income", tot_net), inp("Months with income", len(nets), "count"), inp("= Monthly average", avg12)],
          "A smoothed figure so one big or small month does not swing your plans.",
          "Plan budgets on this average, especially if your income is irregular (freelance, business, gig).", tone="blue"),
        E("gross_vs_net", "Gross vs net income (12 months)", tot_net, "money",
          "Net = Gross − tax (TDS) − provident fund − other deductions",
          [inp("Gross income", tot_gross), inp("− Total deductions", tot_gross - tot_net), inp("= Net received", tot_net),
           inp("Deductions as % of gross", pct(tot_gross - tot_net, tot_gross), "pct")],
          "Gross is before deductions; net is what actually arrives in your account.",
          "Only net income is available to spend or save."),
        E("variability", "Income stability", round(cv * 100, 1), "pct",
          "Variability = standard deviation of monthly income ÷ average monthly income × 100",
          [inp("Monthly average", avg12), inp("Variability", cv * 100, "pct")],
          "How much your monthly income moves around.", "Under 10% is steady like a salary; over 30% is irregular.", sub=stability),
    ]
    return {"metrics": metrics, "by_month": by_month, "types": types, "profile": c.profile}


# ------------------------------------------------------------------------------------------------ recurring
def recurring_view(c: Ctx) -> dict:
    rows = []
    for r in c.rec.itertuples():
        rows.append({"recurring_id": int(r.recurring_id), "name": r.name, "kind": r.kind, "amount": M(r.amount_minor),
                     "frequency": r.frequency, "direction": r.direction, "category": r.category,
                     "category_label": lbl_cat(r.category) if r.category else None,
                     "subcategory_label": lbl_sub(r.category, r.subcategory) if r.category else None,
                     "last_paid_ts": int(r.last_paid_ts) if pd.notna(r.last_paid_ts) else None,
                     "next_due_ts": int(r.next_due_ts) if pd.notna(r.next_due_ts) else None})
    rows.sort(key=lambda r: r["next_due_ts"] or 0)
    horizon = c.as_of_ts + 30 * DAY
    due = [r for r in rows if r["direction"] == "debit" and r["next_due_ts"] and r["next_due_ts"] <= horizon]
    monthly_out = sum(int(r["amount"]) * (1 if r["frequency"] == "monthly" else 1 / 12) for r in rows if r["direction"] == "debit")
    monthly_in = sum(int(r["amount"]) for r in rows if r["direction"] == "credit" and r["frequency"] == "monthly")
    subs = [r for r in rows if r["kind"] == "subscription"]
    return {"items": rows, "due_next_30_days": {"count": len(due), "amount": M(sum(int(r["amount"]) for r in due))},
            "monthly_commitments": M(monthly_out), "monthly_recurring_income": M(monthly_in),
            "subscriptions": {"count": len(subs), "monthly": M(sum(int(r["amount"]) for r in subs)),
                              "annual": M(12 * sum(int(r["amount"]) for r in subs))},
            "explain": {"formula": "Monthly commitments = Σ monthly bills/EMIs/rent/subscriptions/SIPs + (annual items ÷ 12)",
                        "inputs": [inp("Monthly commitments", monthly_out), inp("Recurring income per month", monthly_in),
                                   inp("Due in next 30 days", sum(int(r["amount"]) for r in due)),
                                   inp("Subscriptions per year", 12 * sum(int(r["amount"]) for r in subs))],
                        "meaning": "Payments that repeat on a schedule, so you can plan for them and spot forgotten subscriptions.",
                        "reading": "Review subscriptions yearly: the annual cost is often a surprise.", "caveat": None}}


# ------------------------------------------------------------------------------------------------ goals
def goals_view(c: Ctx) -> dict:
    b = balances(c, c.as_of_ts)
    rows = []
    for g in c.goals.itertuples():
        if g.kind == "emergency" and pd.notna(g.linked_account_id):
            saved = float(b[b.account_id == g.linked_account_id].balance.sum())
        else:
            saved = float(g.saved_minor or 0)
        saved_c = min(saved, float(g.target_minor))
        dl = datetime.strptime(g.deadline, "%Y-%m-%d").replace(tzinfo=IST)
        asof = datetime.fromtimestamp(c.as_of_ts, IST)
        months_left = max(0, (dl.year - asof.year) * 12 + dl.month - asof.month)
        remaining = max(0.0, float(g.target_minor) - saved)
        need_pm = remaining / months_left if months_left > 0 else remaining
        prog = pct(saved_c, g.target_minor)
        rows.append({"goal_id": int(g.goal_id), "name": g.name, "kind": g.kind, "target": M(g.target_minor), "saved": M(saved_c),
                     "remaining": M(remaining), "deadline": g.deadline, "months_left": months_left, "monthly_needed": M(need_pm),
                     "progress_pct": prog, "linked": g.kind == "emergency",
                     "explain": {"formula": "Progress = saved ÷ target × 100;  Monthly needed = (target − saved) ÷ months left until the deadline",
                                 "inputs": [inp("Target", g.target_minor), inp("Saved so far", saved_c), inp("Remaining", remaining),
                                            inp("Deadline", g.deadline, "text"), inp("Months left", months_left, "count"),
                                            inp("Save per month to finish on time", need_pm), inp("Progress", prog, "pct")],
                                 "meaning": "How close you are to this goal and what monthly saving would get you there by the deadline.",
                                 "reading": ("The emergency fund is linked to your savings account balance, so it updates automatically."
                                             if g.kind == "emergency" else "Add contributions to move the progress bar."),
                                 "caveat": None}})
    return {"goals": rows}


# ------------------------------------------------------------------------------------------------ insights
def insights_view(s, c: Ctx, m: str) -> dict:
    mt = month_table(c.led)
    # anomalies: unusual expenses in the last 90 days vs the customer's own history in that category
    s_ts, e_ts = month_bounds(m)
    recent = c.led[(c.led.posted_ts >= e_ts - 90 * DAY) & (c.led.posted_ts < e_ts) & (c.led.purpose == "purchase") & c.led.category.notna()]
    hist = c.led[(c.led.purpose == "purchase") & c.led.category.notna() & (c.led.posted_ts < e_ts)]
    stats = hist.groupby("category").amount_minor.agg(["median", lambda x: float(np.median(np.abs(x - np.median(x))))])
    stats.columns = ["median", "mad"]
    anomalies = []
    for r in recent.itertuples():
        if r.category not in stats.index:
            continue
        med, mad = stats.at[r.category, "median"], max(stats.at[r.category, "mad"], 0.2 * stats.at[r.category, "median"])
        z = (r.amount_minor - med) / (1.4826 * mad) if mad else 0
        if z >= 6 and r.amount_minor >= 200000:
            anomalies.append({"id": int(r.id), "when": datetime.fromtimestamp(r.posted_ts, IST).strftime("%Y-%m-%d"),
                              "category": lbl_cat(r.category), "merchant": r.merchant_name, "amount": M(r.amount_minor),
                              "typical": M(med), "times_typical": round(r.amount_minor / med, 1) if med else None, "score": round(float(z), 1)})
    anomalies = sorted(anomalies, key=lambda a: -a["score"])[:10]
    # forecast next month = fixed commitments + average variable spending (3 months)
    fx = c.led[(c.led.fixed_variable == "fixed") & c.led.purpose.isin(GROSS | CREDITS)]
    vr = c.led[(c.led.fixed_variable != "fixed") & c.led.purpose.isin(GROSS | CREDITS)]
    months3 = [shift_month(m, -i) for i in range(3) if shift_month(m, -i) in mt.index]
    fixed_avg = float(fx[fx.month.isin(months3)].sx.sum()) / max(1, len(months3))
    var_avg = float(vr[vr.month.isin(months3)].sx.sum()) / max(1, len(months3))
    forecast = fixed_avg + var_avg
    next_m = shift_month(m, 1)
    # budget overshoot prediction: pace this month vs budget
    bud = budget_status(c, m)
    dayn = datetime.fromtimestamp(c.as_of_ts - 1, IST).day if m == mkey(c.as_of_ts - 1) else days_in(m)
    pred = []
    for r in bud["rows"]:
        proj = float(r["spent"]) / max(1, dayn) * days_in(m)
        pred.append({"category": r["category"], "label": r["label"], "budget": r["budget"], "spent": r["spent"],
                     "projected": M(proj), "will_overshoot": proj > float(r["budget"]) * 1.0})
    cat_trend = category_table(c, m)[:6]
    return {
        "anomalies": {"items": anomalies, "explain": {
            "formula": "Robust z-score = (amount − category median) ÷ (1.4826 × MAD);  flagged when z ≥ 6 and amount ≥ ₹2,000",
            "inputs": [inp("Purchases checked (last 90 days)", len(recent), "count"), inp("Flagged", len(anomalies), "count")],
            "meaning": "Purchases that are far larger than your usual spend in that category.",
            "reading": "A flag is only a prompt to double-check; large one-off purchases are often legitimate.",
            "caveat": "This compares you with your own history. The fraud models on the staff pages work differently (they score digital payments)."}},
        "forecast": {"month": next_m, "label": month_label(next_m), "amount": M(forecast), "fixed": M(fixed_avg), "variable": M(var_avg),
                     "explain": {"formula": "Forecast next month = average fixed commitments (3 months) + average variable spending (3 months)",
                                 "inputs": [inp("Fixed commitments (rent, EMI interest, bills, subscriptions)", fixed_avg),
                                            inp("+ Variable spending (food, shopping, travel …)", var_avg), inp("= Forecast net spending", forecast)],
                                 "meaning": f"A simple projection of your net spending for {month_label(next_m)}.",
                                 "reading": "It is a trend projection, not a guarantee; one-off costs such as annual premiums are not predicted.",
                                 "caveat": "Simple moving-average method."}},
        "budget_overshoot": {"items": pred, "explain": {
            "formula": "Projected month-end = spent so far ÷ days elapsed × days in the month;  overshoot if projected > budget",
            "inputs": [inp("Days elapsed", dayn, "count"), inp("Days in month", days_in(m), "count")],
            "meaning": "Which budgets you are on pace to exceed.", "reading": "Slow down in the flagged categories to stay inside budget.",
            "caveat": "Uses a straight-line pace, so lumpy bills can look worse than they are."}},
        "category_trends": cat_trend,
        "savings_series": [{"month": x, "label": month_label(x), "rate": pct(float(mt.at[x, "income_net"] - mt.at[x, "net_spend"]), float(mt.at[x, "income_net"]))}
                           for x in mt.index],
    }


# ------------------------------------------------------------------------------------------------ tax
def _old_regime_tax(taxable: float) -> float:
    slabs = [(250000, 0.0), (500000, 0.05), (1000000, 0.20), (10 ** 12, 0.30)]
    tax, lo = 0.0, 0.0
    for hi, rate in slabs:
        if taxable > lo:
            tax += (min(taxable, hi) - lo) * rate
        lo = hi
    if taxable <= 500000:
        tax = 0.0  # section 87A rebate
    return tax * 1.04  # 4% cess


def tax_view(c: Ctx, fy: str | None = None) -> dict:
    led = c.led
    asof_m = mkey(c.as_of_ts - 1)
    y, mo = map(int, asof_m.split("-"))
    fy_start = y if mo >= 4 else y - 1
    if fy:
        fy_start = int(fy.split("-")[0])
    months = [f"{fy_start + (1 if k >= 9 else 0):04d}-{(k + 3) % 12 + 1:02d}" for k in range(12)]
    have = [x for x in months if x in set(led.month)]
    inc = led[led.purpose.isin(INCOME) & led.month.isin(months)]
    gross = float(inc.gross_minor.fillna(inc.amount_minor).sum())
    net = float(inc.amount_minor.sum())
    tds, pf = float(inc.tds_minor.fillna(0).sum()), float(inc.pf_minor.fillna(0).sum())
    oth = float(inc.other_ded_minor.fillna(0).sum())
    sip = led[led.month.isin(months) & (led.purpose == "investment_contribution")]
    elss_share = (c.holdings[c.holdings.tax_80c.astype(bool)].sip_minor.sum() / max(1, c.holdings[c.holdings.kind == "sip_mf"].sip_minor.sum())) if len(c.holdings) else 0
    elss = float(sip.amount_minor.sum()) * float(elss_share)
    ins = led[led.month.isin(months) & (led.category == "insurance")]
    term = float(ins[ins.subcategory == "term_life"].amount_minor.sum())
    health = float(ins[ins.subcategory == "health_insurance"].amount_minor.sum())
    rent = float(led[led.month.isin(months) & (led.category == "rent") & (led.subcategory == "rent") & (led.purpose == "purchase")].amount_minor.sum())
    d80c = min(15000000.0, pf + elss + term)
    d80d = min(2500000.0, health)
    n_m = max(1, len(have))
    ann = 12.0 / n_m
    std_ded = 5000000.0
    taxable_ann = max(0.0, gross * ann - std_ded - d80c * ann - d80d * ann)
    est_tax = _old_regime_tax(taxable_ann / 100) * 100
    est_tax_period = est_tax / ann
    metrics = [
        E("gross_income", "Gross income", gross, "money", "Gross income = Σ gross pay before deductions in the financial year",
          [inp("Gross income", gross), inp("Months of data in this year", n_m, "count")],
          f"Your pre-tax income for FY {fy_start}-{str(fy_start + 1)[2:]} so far.", "This is the base for tax. Net pay is lower.",
          caveat="Partial year: only months in the data are included." if n_m < 12 else None, tone="blue"),
        E("tds_pf", "Tax already deducted (TDS) + PF", tds + pf, "money", "TDS + provident fund deducted from your pay",
          [inp("TDS (income tax deducted)", tds), inp("Provident fund", pf), inp("Other deductions (e.g. professional tax)", oth)],
          "Tax and PF your employer has already taken before paying you.", "TDS is credited against your final tax; PF counts toward 80C."),
        E("sec80c", "Section 80C deduction", d80c, "money", "80C = min(₹1,50,000, PF + ELSS SIP contributions + term-life premium)",
          [inp("Provident fund", pf), inp("+ ELSS tax-saver SIP", elss), inp("+ Term-life premium", term), inp("= Eligible", pf + elss + term),
           inp("Limit", 15000000)], "Investments and premiums that reduce your taxable income (old regime).",
          "If eligible is below the limit, you can still invest more (PPF, ELSS) to use it fully."),
        E("sec80d", "Section 80D (health insurance)", d80d, "money", "80D = min(₹25,000, health-insurance premium paid)",
          [inp("Health-insurance premium", health), inp("Limit", 2500000)], "Deduction for health-insurance premiums.", "Parents' cover has a separate, higher limit."),
        E("est_tax", "Estimated income tax (old regime)", est_tax_period, "money",
          "Taxable income = gross − ₹50,000 standard deduction − 80C − 80D (annualised);  tax from slabs 0/5/20/30% + 4% cess",
          [inp("Annualised gross income", gross * ann), inp("− Standard deduction", std_ded), inp("− 80C + 80D", (d80c + d80d) * ann),
           inp("= Annualised taxable income", taxable_ann), inp("Estimated annual tax", est_tax),
           inp("Estimated tax for the months shown", est_tax_period), inp("TDS already deducted", tds)],
          "A rough estimate of the tax on your income, to compare with TDS already deducted.",
          "If estimated tax is higher than TDS you may owe more at filing; if lower, you may get a refund.",
          caveat="Illustrative only. It ignores HRA, other income and the new tax regime; it is not tax advice."),
    ]
    return {"fy": f"{fy_start}-{str(fy_start + 1)[2:]}", "months_with_data": n_m, "metrics": metrics,
            "rent_paid": M(rent), "tds": M(tds), "pf": M(pf), "gross": M(gross), "net": M(net),
            "note": "Estimates for learning; verify with a tax professional."}
