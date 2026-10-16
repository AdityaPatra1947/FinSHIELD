import pandas as pd

from app.services.spending import cash_reconciliation, spending_totals

T = 1_000_000


def row(purpose, amt, direction, status="posted", kind="bank", cat="groceries"):
    return dict(amount_minor=amt * 100, purpose=purpose, direction=direction, status=status,
                account_kind=kind, category=cat, posted_ts=T)


def test_worked_ledger_fixture():
    rows = [
        row("salary", 50000, "credit"), row("purchase", 2000, "debit"), row("purchase", 1000, "debit", cat="dining"),
        row("refund", 200, "credit", cat="dining"),
        row("own_transfer", 10000, "debit"), row("own_transfer", 10000, "credit", kind="savings"),
        row("cash_withdrawal", 5000, "debit"), row("cash_withdrawal", 5000, "credit", kind="cash"),
        row("purchase", 800, "debit", kind="cash"), row("purchase", 3000, "debit", kind="credit_card"),
        row("card_repayment", 3000, "debit"), row("card_repayment", 3000, "credit", kind="credit_card"),
        row("investment_contribution", 4000, "debit"), row("fee", 100, "debit"),
        row("purchase", 700, "debit", status="failed"), row("purchase", 900, "debit", status="pending"),
        row("refund", 500, "credit"),  # refund of a prior-month purchase, posts this month
    ]
    t = spending_totals(pd.DataFrame(rows), T - 1, T + 1)
    assert t["gross_spending_minor"] == "690000"
    assert t["expense_credits_minor"] == "70000"
    assert t["net_spending_minor"] == "620000"
    assert t["recognized_income_minor"] == "5000000"
    assert t["budget_surplus_minor"] == "4380000"
    assert round(t["budget_surplus_rate"], 6) == 87.6


def test_zero_income_rate_is_null_with_reason():
    t = spending_totals(pd.DataFrame([row("purchase", 10, "debit")]), T - 1, T + 1)
    assert t["budget_surplus_rate"] is None and t["budget_surplus_rate_reason"]


def test_cash_fixture():
    cash = pd.DataFrame([row("cash_withdrawal", 5000, "credit", kind="cash"), row("purchase", 800, "debit", kind="cash"),
                         row("cash_deposit", 2000, "debit", kind="cash")])
    r = cash_reconciliation(cash, opening_minor=100000, observed_minor=300000)
    assert r["expected_closing_minor"] == "320000" and r["difference_minor"] == "20000"
