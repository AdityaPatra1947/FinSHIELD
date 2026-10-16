"""Hand-checked fixture for the personal-finance formulas (all amounts in rupees x100 = paise)."""
import numpy as np
import pandas as pd
import pytest

from app.finance.layer import amortize, balance_after, salary_breakup, ts_of
from app.services import finance as F
from app.services.spending import CREDITS, GROSS

R = 100  # rupees -> paise
M = "2026-09"


def tx_rows():
    t = lambda d, h=10: ts_of(2026, 9, d, h)
    base = dict(customer_id=1, status="posted", eligible=False, fraud=0, tds_minor=np.nan, pf_minor=np.nan, gross_minor=np.nan,
                income_type=None, fixed_variable=None, merchant_name=None, subcategory=None, class_category=None, voided=False)
    rows = [
        dict(account_id=11, direction="credit", amount_minor=50000 * R, purpose="salary", category=None, ts=t(1), income_type="salary",
             gross_minor=60000 * R, pf_minor=2880 * R, tds_minor=7120 * R, txn_type="income"),
        dict(account_id=11, direction="debit", amount_minor=8000 * R, purpose="purchase", category="groceries", ts=t(3), txn_type="expense"),
        dict(account_id=11, direction="debit", amount_minor=6000 * R, purpose="purchase", category="dining", ts=t(4), txn_type="expense"),
        dict(account_id=11, direction="credit", amount_minor=1000 * R, purpose="refund", category="dining", ts=t(8), txn_type="expense"),
        dict(account_id=11, direction="debit", amount_minor=15000 * R, purpose="purchase", category="rent", ts=t(5), txn_type="expense",
             subcategory="rent", fixed_variable="fixed"),
        dict(account_id=11, direction="debit", amount_minor=2000 * R, purpose="interest_expense", category="debt_emi", ts=t(6), txn_type="expense",
             fixed_variable="fixed"),
        dict(account_id=11, direction="debit", amount_minor=3000 * R, purpose="loan_principal", category="debt_emi", ts=t(6), txn_type="debt"),
        dict(account_id=11, direction="debit", amount_minor=5000 * R, purpose="investment_contribution", category=None, ts=t(10), txn_type="investment"),
        dict(account_id=11, direction="debit", amount_minor=4000 * R, purpose="external_transfer", category=None, ts=t(12), txn_type="transfer"),
        dict(account_id=11, direction="debit", amount_minor=10000 * R, purpose="own_transfer", category=None, ts=t(14), txn_type="transfer"),
        dict(account_id=12, direction="credit", amount_minor=10000 * R, purpose="own_transfer", category=None, ts=t(14), txn_type="transfer"),
    ]
    df = pd.DataFrame([{**base, **r} for r in rows])
    df["posted_ts"] = df.ts + 60.0
    df["id"] = range(1, len(df) + 1)
    return df


def make_ctx():
    raw = tx_rows()
    led = raw.copy()
    led["month"] = M
    led["nw"] = led.category.map(F.nw_of)
    led["sx"] = np.where(led.purpose.isin(GROSS), led.amount_minor, np.where(led.purpose.isin(CREDITS), -led.amount_minor, 0))
    accounts = pd.DataFrame([
        dict(account_id=11, customer_id=1, kind="bank", name="Primary bank account", institution="X", masked_ref="XXXX1", opening_minor=100000 * R,
             opening_ts=0, credit_limit_minor=None, apr_pct=None, purpose="Day-to-day"),
        dict(account_id=12, customer_id=1, kind="savings", name="Savings account", institution="X", masked_ref="XXXX2", opening_minor=300000 * R,
             opening_ts=0, credit_limit_minor=None, apr_pct=None, purpose="Savings")])
    P, r = amortize(10000 * R, 10.0, 60)
    loans = pd.DataFrame([dict(loan_id=1, customer_id=1, kind="personal_loan", name="Personal loan", lender="X", principal_minor=int(round(P)),
                               rate_pct=10.0, tenure_months=60, emi_minor=10000 * R, first_emi_date="2025-10-05", pay_day=5,
                               recurring_id=1, account_id=11)])
    empty = lambda cols: pd.DataFrame({c: [] for c in cols})
    return F.Ctx(1, raw, led, accounts, loans, empty(["holding_id", "customer_id", "name", "kind", "asset_class", "sip_minor",
                 "opening_value_minor", "invested_minor", "current_value_minor", "tax_80c"]),
                 empty(["holding_id", "customer_id", "month", "contributed_minor", "invested_cum_minor", "value_minor"]),
                 empty(["recurring_id"]), empty(["customer_id", "month", "category", "amount_minor"]), empty(["goal_id"]),
                 {}, ts_of(2026, 10, 1, 0), M)


def metric(ov, key):
    return next(m for m in ov["metrics"] if m["key"] == key)


@pytest.fixture(scope="module")
def ov():
    class S:  # minimal store: only the bracket table is needed
        fin = {"brackets": pd.DataFrame([dict(code="B3", label="x", min_inr=0, max_inr=10**9, default_mode="advanced", situation="s", emphasis="a|b")])}
    return F.overview(S, make_ctx())


def test_net_spending_and_savings_rate(ov):
    assert int(metric(ov, "gross_spending")["value"]) == 31000 * R      # groceries+dining+rent+loan interest
    assert int(metric(ov, "refunds")["value"]) == 1000 * R
    assert int(metric(ov, "net_spending")["value"]) == 30000 * R
    assert int(metric(ov, "income")["value"]) == 50000 * R
    assert metric(ov, "savings_rate")["value"] == pytest.approx(40.0)    # (50k-30k)/50k


def test_gross_vs_net_income_is_explained(ov):
    ex = metric(ov, "income")["explain"]["inputs"]
    vals = {i["label"]: int(i["value"]) for i in ex}
    assert vals["Before deductions (gross)"] == 60000 * R
    assert vals["Tax / PF / other deductions"] == 10000 * R


def test_50_30_20_split(ov):
    sp = ov["split"]
    assert int(sp["needs"]["amount"]) == 28000 * R      # 8k groceries + 15k rent + 2k interest + 3k loan principal
    assert sp["needs"]["pct"] == pytest.approx(56.0)
    assert int(sp["wants"]["amount"]) == 5000 * R       # dining 6k - refund 1k
    assert int(sp["savings"]["amount"]) == 17000 * R    # remainder, includes SIP and the 4k unclassified transfer


def test_burn_runway_cover_dti(ov):
    assert int(metric(ov, "burn_rate")["value"]) == 33000 * R           # net spend 30k + principal 3k
    # bank 100k+50k-53k+1k = 98k ; savings 310k ; liquid 408k
    assert metric(ov, "runway")["value"] == pytest.approx(408000 / 33000, abs=0.05)
    assert metric(ov, "emergency_cover")["value"] == pytest.approx(310000 / 28000, abs=0.05)
    assert metric(ov, "dti")["value"] == pytest.approx(100 * 5000 / 60000, abs=0.01)   # EMI 5k / gross 60k


def test_net_worth_assets_minus_liabilities(ov):
    nw = metric(ov, "net_worth")
    loan_out = F.loan_state(make_ctx().loans.iloc[0], ts_of(2026, 10, 1, 0) - 1)["outstanding"]
    assert int(nw["value"]) == pytest.approx(408000 * R - loan_out, abs=2)


def test_loan_amortisation_closes_to_zero_and_matches_formula():
    P, r = amortize(10000 * R, 10.0, 60)
    bal = P
    for _ in range(60):
        bal = bal - (10000 * R - bal * r)
    assert abs(bal) < 5                                    # fully paid
    assert balance_after(P, r, 10000 * R, 12) == pytest.approx(
        next(b for b in [P] for _ in range(1)) and _iterate(P, r, 10000 * R, 12), rel=1e-9)
    l = make_ctx().loans.iloc[0]
    st = F.loan_state(l, ts_of(2026, 9, 30))
    assert st["paid"] == 12 and st["left"] == 48


def _iterate(P, r, emi, n):
    b = P
    for _ in range(n):
        b = b * (1 + r) - emi
    return b


def test_salary_breakup_net_plus_deductions_equals_gross():
    g, pf, tds, oth = salary_breakup(50000 * R, "salary")
    assert g == 50000 * R + pf + tds + oth and g > 50000 * R and tds >= 0


def test_unclassified_transfers_not_counted_as_spending(ov):
    assert int(ov["to_classify"]["amount"]) == 4000 * R and ov["to_classify"]["count"] == 1
    assert int(metric(ov, "net_spending")["value"]) == 30000 * R   # unchanged by the 4k transfer


def test_every_metric_has_an_explanation(ov):
    for m in ov["metrics"]:
        ex = m["explain"]
        assert ex["formula"] and ex["meaning"] and ex["reading"] and isinstance(ex["inputs"], list) and ex["inputs"]
