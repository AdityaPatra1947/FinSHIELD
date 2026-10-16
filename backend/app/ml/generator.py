"""Seeded synthetic banking ledger generator (SYNTHETIC DATA ONLY).

Produces one canonical `transactions` table (money in integer paise), fraud labels with
a 7-day maturity delay, and a manifest. Ledger truth only; the evidence/duplicate layer
from the spec is not generated in this local build.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

IST = timezone(timedelta(hours=5, minutes=30))
ORIGIN = datetime(2025, 10, 1, tzinfo=IST)
ORIGIN_TS = int(ORIGIN.timestamp())
DAY = 86400
LABEL_DELAY_S = 7 * DAY
GENERATOR_VERSION = "gen-v1"

CATS = {  # code: (log-mean INR, budget bucket)
    "groceries": (6.0, "needs"), "dining": (5.7, "spends"), "transport": (5.3, "needs"),
    "shopping": (7.0, "spends"), "entertainment": (6.0, "spends"), "health": (6.5, "essentials"),
    "utilities": (7.0, "bills"), "travel": (7.8, "spends"), "education": (7.5, "essentials"),
}
CAT_LIST = list(CATS)
HOUR_W = np.array([1, 1, 1, 1, 1, 2, 3, 5, 6, 7, 7, 7, 8, 7, 6, 6, 7, 8, 9, 9, 8, 6, 4, 2], float)
HOUR_P = HOUR_W / HOUR_W.sum()


def _paise(inr: np.ndarray) -> np.ndarray:
    return np.maximum(1000, np.round(inr * 100)).astype(np.int64)


def generate(n_customers: int = 600, days: int = 365, seed: int = 42,
             fraud_rate: float = 0.008):
    rng = np.random.default_rng(seed)
    cust = pd.DataFrame({
        "customer_id": np.arange(1, n_customers + 1),
        "display_name": [f"Synthetic Customer {i:04d}" for i in range(1, n_customers + 1)],
        "scale": rng.lognormal(0, 0.4, n_customers),
        "income_inr": rng.lognormal(10.6, 0.45, n_customers).round(-2),
        "rate": rng.gamma(4.0, 0.14, n_customers).clip(0.15, 1.6),   # digital attempts / day
        "cash_rate": rng.gamma(2.0, 0.06, n_customers).clip(0.02, 0.5),
        "card_share": rng.uniform(0, 0.7, n_customers),
        "open_day": np.where(rng.random(n_customers) < 0.15, rng.integers(20, 300, n_customers), 1),
        "n_contacts": rng.integers(4, 12, n_customers),
        "has_second_device": rng.random(n_customers) < 0.15,
        "is_synthetic": 1,
    })
    prefs = rng.dirichlet(np.ones(len(CAT_LIST)) * 0.8, n_customers)
    rows: list[pd.DataFrame] = []

    def ts_for(day, rng_=rng):
        hour = rng_.choice(24, size=len(day), p=HOUR_P)
        return ORIGIN_TS + (day - 1) * DAY + hour * 3600 + rng_.integers(0, 3600, len(day))

    # ---------- legitimate digital attempts ----------
    for c in cust.itertuples(index=False):
        span = days - c.open_day + 1
        n = rng.poisson(c.rate * span)
        if n == 0:
            continue
        day = rng.integers(c.open_day, days + 1, n)
        kind = rng.choice(3, size=n, p=[0.82, 0.14, 0.04])  # purchase / transfer / atm
        cat_idx = rng.choice(len(CAT_LIST), size=n, p=prefs[c.customer_id - 1])
        base = np.array([CATS[CAT_LIST[i]][0] for i in cat_idx])
        amt = np.where(kind == 0, np.exp(base + rng.normal(0, 0.6, n)) * c.scale,
                       np.where(kind == 1, np.exp(7.2 + rng.normal(0, 0.8, n)) * c.scale,
                                rng.choice([500, 1000, 2000, 3000, 5000], n) * 1.0))
        # benign lookalikes: occasional large amounts, new payees, new devices
        big = rng.random(n) < 0.03
        amt = np.where(big, amt * rng.uniform(2, 6, n), amt)
        card = (kind == 0) & (rng.random(n) < c.card_share)
        channel = np.where(kind == 2, "atm", np.where(card, "card",
                           np.where(kind == 1, rng.choice(["upi", "netbanking"], n), "upi")))
        purpose = np.array(["purchase", "external_transfer", "cash_withdrawal"])[kind]
        new_payee = rng.random(n) < np.where(kind == 1, 0.12, 0.05)
        merch = rng.integers(0, 6, n) + 6 * cat_idx
        payee = np.where(kind == 0, [f"m{m}" for m in merch],
                         np.where(kind == 2, "atm",
                                  [f"p{c.customer_id}_{k}" for k in rng.integers(0, c.n_contacts, n)]))
        payee = np.where(new_payee & (kind != 2), [f"np{c.customer_id}_{i}" for i in range(n)], payee)
        dev = np.where(rng.random(n) < 0.03, "d1", "d0")
        if not c.has_second_device:
            dev = np.where(dev == "d1", "d0", dev)
        dev = np.array([f"{d}_{c.customer_id}" for d in dev], dtype=object)
        dev[rng.random(n) < 0.05] = None
        new_dev = rng.random(n) < 0.02
        dev = np.where(new_dev, [f"nd{c.customer_id}_{i}" for i in range(n)], dev)
        status = rng.choice(["posted", "failed", "cancelled"], n, p=[0.96, 0.03, 0.01])
        rows.append(pd.DataFrame({
            "customer_id": c.customer_id, "account_kind": np.where(card, "credit_card", "bank"),
            "amount_minor": _paise(amt), "direction": "debit", "status": status, "purpose": purpose,
            "category": np.where(kind == 0, [CAT_LIST[i] for i in cat_idx], None),
            "merchant_key": np.where(kind == 0, [f"m{m}" for m in merch], None),
            "channel": channel, "ts": ts_for(day), "device_token": dev, "payee_token": payee,
            "eligible": True, "fraud": 0}))

    legit = pd.concat(rows, ignore_index=True)
    n_fraud = int(fraud_rate * (legit.status == "posted").sum())

    # ---------- fraud episodes ----------
    frows = []
    made = 0
    ep = 0
    while made < n_fraud:
        ci = int(rng.integers(0, n_customers))
        c = cust.iloc[ci]
        day0 = int(rng.integers(int(c.open_day) + 5, days + 1))
        scen = rng.choice(["A", "B", "C"], p=[0.45, 0.35, 0.20])
        stealth = rng.random() < 0.30
        k = int(rng.integers(1, 7))
        night = rng.random() < 0.5
        h0 = int(rng.integers(0, 5)) if night else int(rng.choice(24, p=HOUR_P))
        t0 = ORIGIN_TS + (day0 - 1) * DAY + h0 * 3600 + int(rng.integers(0, 3600))
        t = t0 + np.cumsum(rng.integers(60, 1800, k))
        mult = rng.uniform(1.0, 2.5, k) if stealth else rng.uniform(3, 10, k)
        if scen == "A":
            typ, purpose, channel = 7.2, "external_transfer", rng.choice(["upi", "netbanking"])
        elif scen == "B":
            typ, purpose, channel = 6.3, "purchase", "card"
        else:
            typ, purpose, channel = 7.6, "cash_withdrawal", "atm"
        amt = np.exp(typ) * c.scale * mult
        if scen == "C":
            amt = np.round(amt / 500) * 500 + 500
        newdev = (rng.random(k) < 0.75) & (not stealth)
        dev = [f"fd{ep}_{i}" if nd else f"d0_{int(c.customer_id)}" for i, nd in enumerate(newdev)]
        payee = ([f"fp{ep}_{i}" for i in range(k)] if (scen == "A" and not stealth)
                 else [f"p{int(c.customer_id)}_{int(rng.integers(0, int(c.n_contacts)))}"] * k
                 if scen == "A" else [f"m{int(rng.integers(0, 54))}"] * k)
        if scen == "C":
            payee = ["atm"] * k
        frows.append(pd.DataFrame({
            "customer_id": int(c.customer_id), "account_kind": "credit_card" if scen == "B" else "bank",
            "amount_minor": _paise(amt), "direction": "debit",
            "status": rng.choice(["posted", "failed"], k, p=[0.9, 0.1]), "purpose": purpose,
            "category": rng.choice(CAT_LIST[:5]) if scen == "B" else None,
            "merchant_key": payee[0] if scen == "B" else None,
            "channel": channel, "ts": t, "device_token": dev, "payee_token": payee,
            "eligible": True, "fraud": 1}))
        made += int((frows[-1].status == "posted").sum())
        ep += 1
    fraud = pd.concat(frows, ignore_index=True)
    fraud = fraud[fraud.ts < ORIGIN_TS + days * DAY]

    # ---------- non-fraud ledger events ----------
    other = []
    month_days = pd.date_range(ORIGIN, periods=days, freq="D", tz=IST)
    firsts = {m: i + 1 for i, m in enumerate(month_days) if m.day in (1, 3, 5, 10, 28)}
    dom = {m.day: [] for m in month_days}
    for m, d in firsts.items():
        dom[m.day].append(d)

    def fixed(c, d, purpose, amt, direction, kind, category=None, channel="bank", sec=36000):
        return dict(customer_id=c.customer_id, account_kind=kind, amount_minor=int(amt * 100),
                    direction=direction, status="posted", purpose=purpose, category=category,
                    merchant_key=None, channel=channel,
                    ts=ORIGIN_TS + (d - 1) * DAY + sec, device_token=None, payee_token=None,
                    eligible=False, fraud=0)

    for c in cust.itertuples(index=False):
        for d in dom[1]:
            if d >= c.open_day:
                other.append(fixed(c, d, "salary", c.income_inr, "credit", "bank", channel="bank", sec=32400))
        for d in dom[5]:
            if d >= c.open_day:
                other.append(fixed(c, d, "purchase", round(c.income_inr * 0.28, -2), "debit", "bank",
                                   "rent", "netbanking"))
        for d in dom[10]:
            if d >= c.open_day:
                other.append(fixed(c, d, "investment_contribution", round(c.income_inr * 0.08, -2),
                                   "debit", "bank"))
        for d in dom[3]:
            if d >= c.open_day:
                amt = round(c.income_inr * 0.1, -2)
                other.append(fixed(c, d, "own_transfer", amt, "debit", "bank"))
                other.append(fixed(c, d, "own_transfer", amt, "credit", "savings"))
    other = pd.DataFrame(other)

    # cash purchases (manual entry, wallet account), not fraud-eligible
    cr = []
    for c in cust.itertuples(index=False):
        n = rng.poisson(c.cash_rate * (days - c.open_day + 1))
        if n == 0:
            continue
        day = rng.integers(c.open_day, days + 1, n)
        ci = rng.choice(len(CAT_LIST), size=n, p=prefs[c.customer_id - 1])
        amt = np.exp(np.array([CATS[CAT_LIST[i]][0] for i in ci]) - 0.5 + rng.normal(0, .5, n)) * c.scale
        cr.append(pd.DataFrame({
            "customer_id": c.customer_id, "account_kind": "cash", "amount_minor": _paise(amt),
            "direction": "debit", "status": "posted", "purpose": "purchase",
            "category": [CAT_LIST[i] for i in ci], "merchant_key": None, "channel": "manual",
            "ts": ts_for(day), "device_token": None, "payee_token": None, "eligible": False, "fraud": 0}))
    cash = pd.concat(cr, ignore_index=True)

    tx = pd.concat([legit, fraud, other, cash], ignore_index=True)

    # derived cash-wallet legs of ATM withdrawals + card repayments + refunds + fees
    atm = tx[(tx.purpose == "cash_withdrawal") & (tx.status == "posted") & (tx.fraud == 0)]
    wallet = atm.assign(direction="credit", account_kind="cash", eligible=False, fraud=0, channel="derived",
                        device_token=None, payee_token=None)
    posted_card = tx[(tx.account_kind == "credit_card") & (tx.status == "posted") & (tx.purpose == "purchase")]
    mon = ((posted_card.ts - ORIGIN_TS) // (30 * DAY))
    rep = posted_card.groupby(["customer_id", mon.rename("m")]).amount_minor.sum().reset_index()
    rep["ts"] = ORIGIN_TS + (rep.m + 1) * 30 * DAY + 3600 * 10
    rep = rep[rep.ts < ORIGIN_TS + days * DAY]
    repay_bank = pd.DataFrame({"customer_id": rep.customer_id, "account_kind": "bank", "amount_minor": rep.amount_minor,
                               "direction": "debit", "status": "posted", "purpose": "card_repayment", "category": None,
                               "merchant_key": None, "channel": "bank", "ts": rep.ts, "device_token": None,
                               "payee_token": None, "eligible": False, "fraud": 0})
    repay_card = repay_bank.assign(account_kind="credit_card", direction="credit")
    tx = pd.concat([tx, wallet, repay_bank, repay_card], ignore_index=True)

    tx = tx.sort_values(["ts", "customer_id"], kind="stable").reset_index(drop=True)
    tx["id"] = np.arange(1, len(tx) + 1)

    # refunds: ~3% of posted non-fraud purchases, partial or full, 3-25 days later
    cand = tx[(tx.purpose == "purchase") & (tx.status == "posted") & (tx.fraud == 0) & tx.category.notna()
              & (tx.account_kind != "cash")]
    ref = cand[rng.random(len(cand)) < 0.03]
    frac = rng.choice([1.0, 0.5, 0.25], len(ref), p=[0.5, 0.3, 0.2])
    rt = ref.ts.values + rng.integers(3, 26, len(ref)) * DAY
    refunds = pd.DataFrame({
        "customer_id": ref.customer_id.values, "account_kind": ref.account_kind.values,
        "amount_minor": np.maximum(100, (ref.amount_minor.values * frac).astype(np.int64)),
        "direction": "credit", "status": "posted", "purpose": "refund", "category": ref.category.values,
        "merchant_key": ref.merchant_key.values, "channel": "bank", "ts": rt, "device_token": None,
        "payee_token": None, "eligible": False, "fraud": 0, "linked_id": ref.id.values})
    refunds = refunds[refunds.ts < ORIGIN_TS + days * DAY]
    # bank fees on ~1% of transfers
    tr = tx[(tx.purpose == "external_transfer") & (tx.status == "posted")]
    fe = tr[rng.random(len(tr)) < 0.2]
    fees = pd.DataFrame({"customer_id": fe.customer_id.values, "account_kind": "bank", "amount_minor": 1000,
                         "direction": "debit", "status": "posted", "purpose": "fee", "category": "fees",
                         "merchant_key": None, "channel": "bank", "ts": fe.ts.values + 1, "device_token": None,
                         "payee_token": None, "eligible": False, "fraud": 0})
    tx = pd.concat([tx, refunds, fees], ignore_index=True)
    tx = tx.sort_values(["ts", "customer_id"], kind="stable").reset_index(drop=True)
    # re-number after refunds/fees are merged in; linked_id still holds the pre-merge ids
    old_ids = tx["id"]
    tx["id"] = np.arange(1, len(tx) + 1)
    id_map = pd.Series(tx.id.values, index=old_ids.values)
    id_map = id_map[~old_ids.isna().values]
    tx["linked_id"] = tx["linked_id"].map(id_map)

    tx["day"] = ((tx.ts - ORIGIN_TS) // DAY + 1).astype(int)
    tx["posted_ts"] = np.where(tx.status == "posted", tx.ts + 60, np.nan)
    tx["is_derived"] = tx.channel.eq("derived")
    tx["customer_id"] = tx.customer_id.astype(int)
    labels = tx[tx.eligible & (tx.status == "posted")][["id", "fraud", "ts"]].rename(
        columns={"fraud": "label"})
    labels["available_ts"] = labels.ts + LABEL_DELAY_S
    labels["source"] = "synthetic"
    labels = labels.drop(columns="ts")

    h = hashlib.sha256(pd.util.hash_pandas_object(
        tx[["customer_id", "amount_minor", "ts", "purpose", "status"]], index=False).values.tobytes()).hexdigest()
    elig = labels
    manifest = {
        "name": "finshield-synthetic", "generator_version": GENERATOR_VERSION, "seed": seed,
        "schema_version": "ledger-v1", "synthetic": True,
        "customers": int(n_customers), "event_days": days, "transactions": int(len(tx)),
        "eligible_labeled_decisions": int(len(elig)),
        "fraud_positives": int(elig.label.sum()),
        "fraud_prevalence": float(elig.label.mean()),
        "label_delay_days": 7, "origin": ORIGIN.isoformat(), "sha256": h,
        "limitations": ["Synthetic data: performance does not establish effectiveness on real traffic.",
                        "Duplicate-evidence layer, pending-to-posted updates and late-arriving records are not generated.",
                        "Pre-decision balance is not simulated (recorded as missing)."],
    }
    return cust, tx, labels, manifest
