"""Personal-finance API. All routes require a session; customers can only reach their own data (others -> 404)."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.v1.routes import active_family
from app.db import get_engine, now
from app.deps import CurrentUser, admin_only, audit, authorize_customer, current_user, err
from app.finance import taxonomy as T
from app.ml.generator import DAY, ORIGIN_TS
from app.services import finance as F
from app.services.spending import effective
from app.store import Store, get_store

router = APIRouter(prefix="/finance")
_lock = threading.Lock()
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_MINOR = 1_000_000_000 * 100
PAYMENT_METHODS = ["UPI", "Debit card", "Credit card", "Cash", "Net banking", "Auto-debit", "Bank transfer", "Cheque"]
TYPE_LABEL = {"purchase": "Purchase", "fee": "Fee", "interest_expense": "Loan interest", "refund": "Refund",
              "salary": "Salary", "other_earned_income": "Income", "interest_income": "Interest",
              "own_transfer": "Own transfer", "cash_withdrawal": "Cash withdrawal", "cash_deposit": "Cash deposit",
              "card_repayment": "Card bill payment", "external_transfer": "Transfer to others",
              "investment_contribution": "Investment / SIP", "loan_principal": "Loan principal (EMI)"}


def fstore() -> Store:
    s = get_store()
    if not s.ready:
        raise err(503, "not_built", "Dataset not built yet.")
    if s.fin is None:
        raise err(503, "finance_not_built", "Finance layer not built. Run `python -m app.finance.enrich`.")
    return s


def ctx_for(user: CurrentUser, s: Store, cid: int, month: str | None = None) -> F.Ctx:
    authorize_customer(user, cid)
    if cid not in s.by_cust:
        raise err(404, "not_found", "Resource unavailable")
    if month is not None and not MONTH_RE.match(month):
        raise err(422, "invalid_month", "month must be YYYY-MM")
    return F.build_ctx(s, cid, month)


def own_or_staff_customer(user: CurrentUser, customer_id: int | None) -> int:
    if user.role == "customer":
        if user.customer_id is None:
            raise err(403, "forbidden", "No customer record linked to this login")
        return user.customer_id
    if customer_id is None:
        raise err(422, "customer_required", "customer_id is required")
    return customer_id


# ------------------------------------------------------------------ reports
@router.get("/overview")
def overview(customer_id: int, month: str | None = None, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    return F.overview(s, ctx_for(user, s, customer_id, month))


@router.get("/category")
def category(customer_id: int, category: str, month: str | None = None, user: CurrentUser = Depends(current_user),
             s: Store = Depends(fstore)):
    c = ctx_for(user, s, customer_id, month)
    return F.category_detail(c, c.month, category)


@router.get("/accounts")
def accounts(customer_id: int, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    return F.accounts_view(ctx_for(user, s, customer_id))


@router.get("/debts")
def debts(customer_id: int, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    return F.debts_view(ctx_for(user, s, customer_id))


@router.get("/loans/{loan_id}/schedule")
def loan_schedule(loan_id: int, customer_id: int, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    out = F.loan_schedule(ctx_for(user, s, customer_id), loan_id)
    if not out:
        raise err(404, "not_found", "Resource unavailable")
    return out


@router.get("/investments")
def investments(customer_id: int, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    return F.investments_view(ctx_for(user, s, customer_id))


@router.get("/income")
def income(customer_id: int, month: str | None = None, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    c = ctx_for(user, s, customer_id, month)
    return F.income_view(c, c.month)


@router.get("/recurring")
def recurring(customer_id: int, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    return F.recurring_view(ctx_for(user, s, customer_id))


@router.get("/insights")
def insights(customer_id: int, month: str | None = None, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    c = ctx_for(user, s, customer_id, month)
    return F.insights_view(s, c, c.month)


@router.get("/tax")
def tax(customer_id: int, fy: str | None = None, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    return F.tax_view(ctx_for(user, s, customer_id), fy)


@router.get("/taxonomy")
def taxonomy(user: CurrentUser = Depends(current_user)):
    return {"categories": [{"code": k, "label": v["label"], "group": v["group"], "need_want": v["nw"],
                            "subcategories": [{"code": sc, "label": sl, "fixed": sc in v["fixed"]} for sc, sl in v["subs"].items()]}
                           for k, v in T.CATEGORIES.items()],
            "income_types": [{"code": k, "label": v[0], "class": v[1]} for k, v in T.INCOME_TYPES.items()],
            "payment_methods": PAYMENT_METHODS, "tags": T.TAGS}


# ------------------------------------------------------------------ transactions
def _accounts_map(c: F.Ctx) -> dict:
    return {int(a.account_id): a for a in c.accounts.itertuples()}


def _tx_item(r, amap, fam, scores) -> dict:
    cat = r.category if isinstance(r.category, str) else None
    sub = r.subcategory if isinstance(r.subcategory, str) else None
    acc = amap.get(int(r.account_id)) if pd.notna(r.account_id) else None
    ttype = r.txn_type if isinstance(r.txn_type, str) else "expense"
    classified = isinstance(r.class_category, str)
    ecat = r.class_category if classified else cat
    esub = r.class_subcategory if classified else sub
    if r.purpose == "income" or ttype == "income":
        label = T.INCOME_TYPES.get(r.income_type, (TYPE_LABEL.get(r.purpose, "Income"),))[0] if isinstance(r.income_type, str) else TYPE_LABEL.get(r.purpose, "Income")
    else:
        label = TYPE_LABEL.get(r.purpose, r.purpose)
    p = float(scores.at[r.id, fam]) if fam and scores is not None and r.id in scores.index else None
    return {"id": int(r.id), "ts": int(r.ts), "date": datetime.fromtimestamp(int(r.ts), F.IST).strftime("%Y-%m-%d"),
            "time": datetime.fromtimestamp(int(r.ts), F.IST).strftime("%H:%M"), "amount": str(int(r.amount_minor)),
            "direction": r.direction, "status": r.status, "type": ttype, "kind_label": label, "purpose": r.purpose,
            "category": ecat, "category_label": F.lbl_cat(ecat) if ecat else None, "subcategory": esub,
            "subcategory_label": F.lbl_sub(ecat, esub) if ecat else None,
            "merchant": r.merchant_name if isinstance(r.merchant_name, str) else None,
            "payment_method": r.payment_method if isinstance(r.payment_method, str) else None,
            "account": acc.name if acc is not None else None, "account_id": int(r.account_id) if pd.notna(r.account_id) else None,
            "tags": r.tags if isinstance(r.tags, str) else None, "notes": r.notes if isinstance(r.notes, str) else None,
            "recurring": bool(r.is_recurring) if pd.notna(r.is_recurring) else False,
            "fixed_variable": r.fixed_variable if isinstance(r.fixed_variable, str) else None,
            "need_want": F.nw_of(ecat) if ttype == "expense" or classified else None,
            "income_type": r.income_type if isinstance(r.income_type, str) else None,
            "gross": str(int(r.gross_minor)) if pd.notna(r.gross_minor) else None,
            "tds": str(int(r.tds_minor)) if pd.notna(r.tds_minor) else None,
            "pf": str(int(r.pf_minor)) if pd.notna(r.pf_minor) else None,
            "needs_classification": bool(r.purpose == "external_transfer" and r.direction == "debit" and not classified and r.status == "posted"),
            "classified": classified, "editable": True, "voidable": r.source == "manual" if isinstance(r.source, str) else False,
            "fraud_probability": p}


@router.get("/transactions")
def transactions(customer_id: int, month: str | None = None, type: str | None = None, category: str | None = None,
                 account_id: int | None = None, q: str | None = None, status: str | None = None, recurring: bool | None = None,
                 need_want: str | None = None, tag: str | None = None, cursor: str | None = None,
                 limit: int = Query(50, le=200), user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    c = ctx_for(user, s, customer_id, month)
    t = c.tx
    if month:
        a, b = F.month_bounds(month)
        t = t[(t.ts >= a) & (t.ts < b)]
    if type:
        t = t[t.txn_type == type]
    if status:
        t = t[t.status == status]
    if account_id is not None:
        t = t[t.account_id == account_id]
    if recurring is not None:
        t = t[t.is_recurring == recurring]
    if tag:
        t = t[t.tags.fillna("").str.contains(tag, case=False)]
    if q:
        ql = q.lower()
        t = t[t.merchant_name.fillna("").str.lower().str.contains(ql) | t.notes.fillna("").str.lower().str.contains(ql)
              | t.subcategory.fillna("").str.lower().str.contains(ql)]
    if category:
        cc = t.class_category.where(t.class_category.notna(), t.category)
        t = t[cc == category]
    if need_want:
        cc = t.class_category.where(t.class_category.notna(), t.category)
        t = t[(cc.map(F.nw_of) == need_want) & (t.txn_type == "expense")]
    t = t.sort_values(["ts", "id"], ascending=False)
    total = int(len(t))
    if cursor:
        try:
            ts0, id0 = map(int, cursor.split(":"))
        except ValueError:
            raise err(422, "invalid_cursor", "bad cursor")
        t = t[(t.ts < ts0) | ((t.ts == ts0) & (t.id < id0))]
    page = t.head(limit)
    amap, fam = _accounts_map(c), active_family()
    scores = s.scores.set_index("txn_id") if fam else None
    items = [_tx_item(r, amap, fam, scores) for r in page.itertuples()]
    nxt = f"{int(page.ts.iloc[-1])}:{int(page.id.iloc[-1])}" if len(t) > limit else None
    sums = page.assign(sgn=np.where(page.direction == "credit", 1, -1) * page.amount_minor)
    return {"items": items, "next_cursor": nxt, "total": total}


class NewTx(BaseModel):
    type: Literal["expense", "income", "transfer", "investment"]
    amount: str = Field(max_length=20)
    occurred_at: datetime
    account_id: int
    to_account_id: int | None = None
    category: str | None = None
    subcategory: str | None = None
    merchant: str | None = Field(default=None, max_length=80)
    payment_method: str | None = Field(default=None, max_length=30)
    income_type: str | None = None
    gross: str | None = Field(default=None, max_length=20)
    tags: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=200)
    recurring: bool = False
    fixed_variable: Literal["fixed", "variable"] | None = None


def _minor(v: str, field: str) -> int:
    try:
        d = Decimal(v)
    except InvalidOperation:
        raise err(422, "invalid_amount", "Amount must be a number", **{field: "invalid"})
    if d <= 0 or d.as_tuple().exponent < -2 or not d.is_finite():
        raise err(422, "invalid_amount", "Amount must be positive with at most two decimal places", **{field: "invalid"})
    m = int(d * 100)
    if m > MAX_MINOR:
        raise err(422, "amount_too_large", "Amount exceeds the per-transaction limit")
    return m


def _insert(c, row: dict) -> None:
    c.execute(text("INSERT INTO transactions(" + ",".join(row) + ") VALUES(" + ",".join(f":{k}" for k in row) + ")"), row)


@router.post("/transactions", status_code=201)
def create_transaction(body: NewTx, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore),
                       idempotency_key: str | None = Header(default=None, max_length=80)):
    if user.role != "customer" or user.customer_id is None:
        raise err(403, "forbidden", "Only customers can enter their own transactions")
    cid = user.customer_id
    c = F.build_ctx(s, cid)
    amap = _accounts_map(c)
    minor = _minor(body.amount, "amount")
    if body.occurred_at.tzinfo is None:
        raise err(422, "timezone_required", "occurred_at must include a UTC offset", occurred_at="offset required")
    ts = int(body.occurred_at.timestamp())
    if ts > now() + 300 or ts < ORIGIN_TS:
        raise err(422, "invalid_date", "Date must be within the data range and not in the future")
    acc = amap.get(body.account_id)
    if acc is None:
        raise err(404, "not_found", "Account not found")
    if body.tags and not re.match(r"^[\w ,\-]{1,80}$", body.tags):
        raise err(422, "invalid_tags", "Tags may contain letters, numbers, spaces, commas and dashes", tags="invalid")
    row = dict(customer_id=cid, status="posted", ts=ts, day=int((ts - ORIGIN_TS) // DAY + 1), posted_ts=float(ts), channel="manual",
               eligible=False, fraud=0, is_derived=False, voided=False, source="manual", merchant_name=body.merchant,
               payment_method=body.payment_method or "Manual entry", tags=body.tags, notes=body.notes,
               is_recurring=body.recurring, account_id=body.account_id, account_kind=acc.kind)
    rows: list[dict] = []
    if body.type == "expense":
        cat = F.T.CATEGORIES.get(body.category or "")
        if not cat or (body.subcategory and body.subcategory not in cat["subs"]):
            raise err(422, "invalid_category", "Pick a valid category and subcategory", category="invalid")
        fixed = body.fixed_variable or ("fixed" if body.subcategory in cat["fixed"] else "variable")
        rows.append({**row, "amount_minor": minor, "direction": "debit", "purpose": "purchase", "txn_type": "expense",
                     "category": body.category, "subcategory": body.subcategory, "need_want": cat["nw"], "fixed_variable": fixed})
    elif body.type == "income":
        if acc.kind not in F.ASSET_KINDS:
            raise err(422, "invalid_account", "Income must go to a bank, savings or cash account")
        it = body.income_type or "salary"
        if it not in T.INCOME_TYPES:
            raise err(422, "invalid_income_type", "Unknown income type", income_type="invalid")
        gross = _minor(body.gross, "gross") if body.gross else minor
        if gross < minor:
            raise err(422, "gross_less_than_net", "Gross income cannot be less than the net amount received", gross="too small")
        rows.append({**row, "amount_minor": minor, "direction": "credit", "txn_type": "income", "income_type": it,
                     "purpose": "salary" if it == "salary" else "other_earned_income", "gross_minor": float(gross),
                     "tds_minor": float(gross - minor), "pf_minor": 0.0, "other_ded_minor": 0.0})
    elif body.type == "investment":
        if acc.kind not in F.ASSET_KINDS:
            raise err(422, "invalid_account", "Investments must be paid from a bank, savings or cash account")
        rows.append({**row, "amount_minor": minor, "direction": "debit", "purpose": "investment_contribution", "txn_type": "investment"})
    else:  # own transfer / card bill payment
        dst = amap.get(body.to_account_id) if body.to_account_id else None
        if dst is None or dst.account_id == acc.account_id:
            raise err(422, "invalid_account", "Choose a different account of yours to transfer to", to_account_id="invalid")
        if acc.kind == "credit_card":
            raise err(422, "invalid_account", "Pay card bills from a bank, savings or cash account")
        purpose = "card_repayment" if dst.kind == "credit_card" else "own_transfer"
        rows.append({**row, "amount_minor": minor, "direction": "debit", "purpose": purpose, "txn_type": "transfer"})
        rows.append({**row, "amount_minor": minor, "direction": "credit", "purpose": purpose, "txn_type": "transfer",
                     "account_id": int(dst.account_id), "account_kind": dst.kind})
    body_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    eng = get_engine()
    if idempotency_key:
        with eng.connect() as cn:
            hit = cn.execute(text("SELECT body_hash,response_body FROM idempotency_keys WHERE user_id=:u AND route='POST /finance/transactions' AND key=:k"),
                             {"u": user.id, "k": idempotency_key}).fetchone()
        if hit:
            if hit[0] != body_hash:
                raise err(409, "idempotency_conflict", "Idempotency key reused with a different body")
            return json.loads(hit[1])
    with _lock, eng.begin() as cn:
        nid = int(cn.execute(text("SELECT COALESCE(MAX(id),0)+1 FROM transactions")).scalar())
        for i, r in enumerate(rows):
            r["id"] = nid + i
        if len(rows) == 2:
            rows[0]["linked_id"], rows[1]["linked_id"] = float(rows[1]["id"]), float(rows[0]["id"])
        for r in rows:
            _insert(cn, r)
        resp = {"ids": [r["id"] for r in rows], "type": body.type, "amount": str(minor), "status": "posted"}
        if idempotency_key:
            cn.execute(text("INSERT INTO idempotency_keys(user_id,route,key,body_hash,response_status,response_body,created_at) VALUES(:u,'POST /finance/transactions',:k,:h,201,:b,:t)"),
                       {"u": user.id, "k": idempotency_key, "h": body_hash, "b": json.dumps(resp), "t": now()})
    for r in rows:
        s.add_transaction(r)
    audit(user, "transaction_created", "transaction", str(rows[0]["id"]), {"type": body.type, "amount_minor": minor})
    return resp


class Classify(BaseModel):
    category: str | None = None
    subcategory: str | None = None
    tags: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=200)


def _own_tx(user: CurrentUser, s: Store, txn_id: int):
    row = s.tx[s.tx.id == txn_id]
    if row.empty:
        raise err(404, "not_found", "Resource unavailable")
    r = row.iloc[0]
    authorize_customer(user, int(r.customer_id))
    return r


@router.patch("/transactions/{txn_id}/classification")
def classify(txn_id: int, body: Classify, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    r = _own_tx(user, s, txn_id)
    sets: dict = {}
    if body.category is not None:
        cat = T.CATEGORIES.get(body.category)
        if not cat or (body.subcategory and body.subcategory not in cat["subs"]):
            raise err(422, "invalid_category", "Pick a valid category and subcategory", category="invalid")
        if r.txn_type not in ("expense",) and r.purpose != "external_transfer":
            raise err(409, "not_classifiable", "Only expenses and transfers to other people can be categorised")
        sets["class_category"], sets["class_subcategory"] = body.category, body.subcategory
    if body.tags is not None:
        if body.tags and not re.match(r"^[\w ,\-]{1,80}$", body.tags):
            raise err(422, "invalid_tags", "Tags may contain letters, numbers, spaces, commas and dashes", tags="invalid")
        sets["tags"] = body.tags or None
    if body.notes is not None:
        sets["notes"] = body.notes or None
    if not sets:
        raise err(422, "nothing_to_change", "Nothing to update")
    before = {k: (None if pd.isna(r.get(k)) else r.get(k)) for k in sets}
    with get_engine().begin() as cn:
        cn.execute(text("UPDATE transactions SET " + ",".join(f"{k}=:{k}" for k in sets) + " WHERE id=:id"), {**sets, "id": txn_id})
    s.update_transaction(txn_id, **sets)
    audit(user, "transaction_classified", "transaction", str(txn_id), {"before": before, "after": sets})
    return {"id": txn_id, "updated": list(sets)}


@router.delete("/transactions/{txn_id}")
def void_transaction(txn_id: int, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    r = _own_tx(user, s, txn_id)
    if r.source != "manual":
        raise err(409, "ledger_immutable", "Bank and imported entries are evidence and cannot be deleted. Reclassify them instead.")
    ids = [int(r.id)] + ([int(r.linked_id)] if pd.notna(r.linked_id) else [])
    with get_engine().begin() as cn:
        for i in ids:
            cn.execute(text("UPDATE transactions SET voided=:v WHERE id=:i"), {"v": True, "i": i})
    for i in ids:
        s.update_transaction(i, voided=True)
    audit(user, "transaction_voided", "transaction", str(txn_id), {"ids": ids})
    return {"voided": ids}


@router.get("/review-queue")
def review_queue(customer_id: int, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    c = ctx_for(user, s, customer_id)
    t = c.tx[(c.tx.purpose == "external_transfer") & (c.tx.direction == "debit") & (c.tx.status == "posted") & c.tx.class_category.isna()]
    t = t.sort_values("ts", ascending=False)
    amap = _accounts_map(c)
    return {"total": int(len(t)), "amount": str(int(t.amount_minor.sum())),
            "items": [_tx_item(r, amap, None, None) for r in t.head(100).itertuples()],
            "explain": {"formula": "Unclassified transfers = payments to other people not yet marked as gifts, family support, rent etc.",
                        "inputs": [{"label": "Payments waiting for a category", "value": int(len(t)), "kind": "count"},
                                   {"label": "Total amount", "value": str(int(t.amount_minor.sum())), "kind": "money"}],
                        "meaning": "FinShield cannot tell whether a payment to a person was a gift, rent, a loan repayment or a move between your own accounts, so it asks you.",
                        "reading": "Until you classify them they are not counted as spending, which makes your savings look higher than they are.", "caveat": None}}


# ------------------------------------------------------------------ budgets
class BudgetPut(BaseModel):
    customer_id: int | None = None
    month: str
    category: str
    amount: str = Field(max_length=20)


@router.get("/budgets")
def budgets(customer_id: int, month: str | None = None, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    c = ctx_for(user, s, customer_id, month)
    b = F.budget_status(c, c.month)
    return {"month": c.month, "label": F.month_label(c.month), "rows": b["rows"], "summary": {
        "total_budget": F.M(b["total_budget"]), "total_spent": F.M(b["total_spent"]), "used_pct": b["used_pct"],
        "n_over": b["n_over"], "n_near": b["n_near"], "n_ok": b["n_ok"]},
        "unbudgeted": [x for x in F.category_table(c, c.month) if x["category"] not in {r["category"] for r in b["rows"]}][:8],
        "explain": {"formula": "Alert levels: amber at 80% of a category budget, red at 100%.  Used % = net category spending ÷ budget × 100",
                    "inputs": [{"label": "Total budget", "value": F.M(b["total_budget"]), "kind": "money"},
                               {"label": "Spent in budgeted categories", "value": F.M(b["total_spent"]), "kind": "money"},
                               {"label": "Over budget", "value": b["n_over"], "kind": "count"}, {"label": "Near limit", "value": b["n_near"], "kind": "count"}],
                    "meaning": "A monthly limit for each category you want to control.",
                    "reading": "Set budgets slightly below your recent average to nudge spending down.", "caveat": None}}


@router.put("/budgets")
def put_budget(body: BudgetPut, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    cid = own_or_staff_customer(user, body.customer_id)
    authorize_customer(user, cid)
    if not MONTH_RE.match(body.month) or body.category not in T.CATEGORIES:
        raise err(422, "invalid_budget", "Invalid month or category")
    amt = _minor(body.amount, "amount")
    with _lock, get_engine().begin() as cn:
        cn.execute(text("DELETE FROM budgets WHERE customer_id=:c AND month=:m AND category=:k"), {"c": cid, "m": body.month, "k": body.category})
        cn.execute(text("INSERT INTO budgets(customer_id,month,category,amount_minor) VALUES(:c,:m,:k,:a)"),
                   {"c": cid, "m": body.month, "k": body.category, "a": amt})
    df = s.fin["_frames"]["budgets"]
    df = df[~((df.customer_id == cid) & (df.month == body.month) & (df.category == body.category))]
    df = pd.concat([df, pd.DataFrame([{"customer_id": cid, "month": body.month, "category": body.category, "amount_minor": amt}])], ignore_index=True)
    s.refresh_fin_group("budgets", df)
    audit(user, "budget_set", "budget", f"{cid}:{body.month}:{body.category}", {"amount_minor": amt})
    return {"ok": True}


# ------------------------------------------------------------------ goals
class GoalNew(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: str = Field(default="custom", max_length=20)
    target: str = Field(max_length=20)
    saved: str = Field(default="0", max_length=20)
    deadline: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class Contribute(BaseModel):
    amount: str = Field(max_length=20)


@router.get("/goals")
def goals(customer_id: int, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    return F.goals_view(ctx_for(user, s, customer_id))


@router.post("/goals", status_code=201)
def create_goal(body: GoalNew, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    cid = own_or_staff_customer(user, None) if user.role == "customer" else None
    if cid is None:
        raise err(403, "forbidden", "Only customers manage their own goals")
    target, saved = _minor(body.target, "target"), (_minor(body.saved, "saved") if Decimal(body.saved or "0") > 0 else 0)
    try:
        datetime.strptime(body.deadline, "%Y-%m-%d")
    except ValueError:
        raise err(422, "invalid_date", "Deadline must be a valid date")
    with _lock, get_engine().begin() as cn:
        gid = int(cn.execute(text("SELECT COALESCE(MAX(goal_id),0)+1 FROM goals")).scalar())
        cn.execute(text("INSERT INTO goals(goal_id,customer_id,name,kind,target_minor,saved_minor,deadline,linked_account_id) VALUES(:g,:c,:n,:k,:t,:s,:d,NULL)"),
                   {"g": gid, "c": cid, "n": body.name, "k": body.kind, "t": target, "s": saved, "d": body.deadline})
    df = pd.concat([s.fin["_frames"]["goals"], pd.DataFrame([{"goal_id": gid, "customer_id": cid, "name": body.name, "kind": body.kind,
                    "target_minor": target, "saved_minor": saved, "deadline": body.deadline, "linked_account_id": None}])], ignore_index=True)
    s.refresh_fin_group("goals", df)
    audit(user, "goal_created", "goal", str(gid), {"target_minor": target})
    return {"goal_id": gid}


@router.post("/goals/{goal_id}/contribute")
def contribute(goal_id: int, body: Contribute, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    df = s.fin["_frames"]["goals"]
    g = df[df.goal_id == goal_id]
    if g.empty:
        raise err(404, "not_found", "Resource unavailable")
    g = g.iloc[0]
    authorize_customer(user, int(g.customer_id))
    if g.kind == "emergency":
        raise err(409, "linked_goal", "The emergency fund follows your savings account balance. Transfer money to savings instead.")
    amt = _minor(body.amount, "amount")
    new_saved = int(g.saved_minor or 0) + amt
    with get_engine().begin() as cn:
        cn.execute(text("UPDATE goals SET saved_minor=:s WHERE goal_id=:g"), {"s": new_saved, "g": goal_id})
    df = df.copy()
    df.loc[df.goal_id == goal_id, "saved_minor"] = new_saved
    s.refresh_fin_group("goals", df)
    audit(user, "goal_contribution", "goal", str(goal_id), {"amount_minor": amt})
    return {"goal_id": goal_id, "saved": str(new_saved)}


# ------------------------------------------------------------------ profile / brackets
class ProfilePut(BaseModel):
    preferred_mode: Literal["simple", "advanced"]


@router.get("/profile")
def profile(customer_id: int, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    c = ctx_for(user, s, customer_id)
    months = [m for m in F.month_table(c.led).index]
    return {"profile": c.profile, "bracket": F.bracket_for(s, c), "currency": "INR", "months": months,
            "as_of_month": F.mkey(c.as_of_ts - 1), "brackets": s.fin["brackets"].to_dict("records")}


@router.put("/profile")
def put_profile(body: ProfilePut, customer_id: int | None = None, user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    cid = own_or_staff_customer(user, customer_id)
    authorize_customer(user, cid)
    with get_engine().begin() as cn:
        cn.execute(text("UPDATE customer_profile SET preferred_mode=:m WHERE customer_id=:c"), {"m": body.preferred_mode, "c": cid})
    s.fin["profile"][cid] = {**s.fin["profile"][cid], "preferred_mode": body.preferred_mode}
    return {"preferred_mode": body.preferred_mode}


class BracketPut(BaseModel):
    label: str = Field(max_length=40)
    min_inr: int = Field(ge=0)
    max_inr: int = Field(gt=0)
    default_mode: Literal["simple", "advanced"]
    situation: str = Field(max_length=200)
    emphasis: list[str] = Field(max_length=8)


@router.put("/brackets/{code}")
def put_bracket(code: str, body: BracketPut, user: CurrentUser = Depends(admin_only), s: Store = Depends(fstore)):
    if body.max_inr <= body.min_inr:
        raise err(422, "invalid_range", "max must be greater than min")
    br = s.fin["brackets"]
    if code not in set(br.code):
        raise err(404, "not_found", "Resource unavailable")
    emph = "|".join(x.replace("|", "/") for x in body.emphasis)
    with get_engine().begin() as cn:
        cn.execute(text("UPDATE income_brackets SET label=:l,min_inr=:a,max_inr=:b,default_mode=:m,situation=:s,emphasis=:e WHERE code=:c"),
                   {"l": body.label, "a": body.min_inr, "b": body.max_inr, "m": body.default_mode, "s": body.situation, "e": emph, "c": code})
    br = br.copy()
    br.loc[br.code == code, ["label", "min_inr", "max_inr", "default_mode", "situation", "emphasis"]] = [body.label, body.min_inr, body.max_inr, body.default_mode, body.situation, emph]
    s.fin["brackets"] = br
    audit(user, "bracket_updated", "income_bracket", code, body.model_dump())
    return {"ok": True}


@router.get("/brackets")
def brackets(user: CurrentUser = Depends(current_user), s: Store = Depends(fstore)):
    return {"items": s.fin["brackets"].assign(emphasis=lambda d: d.emphasis.str.split("|")).to_dict("records")}
