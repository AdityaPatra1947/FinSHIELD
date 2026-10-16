"""End-to-end checks for the finance API against a running server (default http://localhost:8000).

Run:  python tests/e2e_finance.py            (server must be running with the demo users seeded)
"""
import sys
import uuid

import httpx

B = "http://localhost:8000/api/v1"
PW = {"customer1@gmail.com": "customer123", "customer2@gmail.com": "customer123", "analyst@gmail.com": "analyst123",
      "admin@gmail.com": "admin123"}
ok_all = True


def login(email):
    c = httpx.Client(base_url=B, timeout=120, headers={"Origin": "http://localhost:3000"})
    t = c.get("/auth/csrf").json()["csrf_token"]
    r = c.post("/auth/login", json={"email": email, "password": PW[email]}, headers={"X-CSRF-Token": t})
    assert r.status_code == 200, r.text
    return c


def mut(c, method, path, **kw):
    return c.request(method, path, headers={"X-CSRF-Token": c.cookies.get("fs_csrf"), **kw.pop("headers", {})}, **kw)


def check(name, cond, extra=""):
    global ok_all
    ok_all &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name, extra)


c1, c2 = login("customer1@gmail.com"), login("customer2@gmail.com")
an, ad = login("analyst@gmail.com"), login("admin@gmail.com")

p = c1.get("/finance/profile", params={"customer_id": 1}).json()
month = p["as_of_month"]
check("profile has months + bracket", len(p["months"]) >= 12 and p["bracket"]["code"])
ov = c1.get("/finance/overview", params={"customer_id": 1, "month": month}).json()
keys = {m["key"] for m in ov["metrics"]}
check("overview has all core metrics", {"income", "net_spending", "savings_rate", "net_worth", "runway", "dti", "emergency_cover", "safe_to_spend"} <= keys)
check("every metric explained", all(m["explain"]["formula"] and m["explain"]["inputs"] for m in ov["metrics"]))
nets = next(m for m in ov["metrics"] if m["key"] == "net_spending")
gross = next(m for m in ov["metrics"] if m["key"] == "gross_spending")
refunds = next(m for m in ov["metrics"] if m["key"] == "refunds")
check("net = gross - refunds", int(nets["value"]) == int(gross["value"]) - int(refunds["value"]))
split = ov["split"]
check("needs+wants+savings = 100%", abs(split["needs"]["pct"] + split["wants"]["pct"] + split["savings"]["pct"] - 100) < 0.01)

check("other customer's overview -> 404", c1.get("/finance/overview", params={"customer_id": 2}).status_code == 404)
check("other customer's transactions -> 404", c1.get("/finance/transactions", params={"customer_id": 2}).status_code == 404)
check("other customer's loan schedule -> 404", c1.get("/finance/loans/1/schedule", params={"customer_id": 2}).status_code == 404)
check("unauthenticated -> 401", httpx.get(B + "/finance/overview", params={"customer_id": 1}).status_code == 401)
check("analyst can view any customer", an.get("/finance/overview", params={"customer_id": 7}).status_code == 200)
check("analyst cannot add transactions", mut(an, "POST", "/finance/transactions", json={"type": "expense"}).status_code in (403, 422))

for ep in ("accounts", "debts", "investments", "recurring", "goals"):
    check(f"/{ep}", c1.get(f"/finance/{ep}", params={"customer_id": 1}).status_code == 200)
for ep in ("income", "insights", "budgets"):
    check(f"/{ep}", c1.get(f"/finance/{ep}", params={"customer_id": 1, "month": month}).status_code == 200)
check("/tax", c1.get("/finance/tax", params={"customer_id": 1}).status_code == 200)
check("/review-queue", c1.get("/finance/review-queue", params={"customer_id": 1}).status_code == 200)

accs = c1.get("/finance/accounts", params={"customer_id": 1}).json()["accounts"]
bank = next(a for a in accs if a["kind"] == "bank")
sav = next(a for a in accs if a["kind"] == "savings")
before = int(bank["balance"])

body = {"type": "expense", "amount": "250.50", "occurred_at": "2026-10-02T10:00:00+05:30", "account_id": bank["account_id"], "category": "groceries",
        "subcategory": "supermarket", "merchant": "Test Mart", "payment_method": "UPI", "tags": "weekend", "notes": "e2e test"}
key = str(uuid.uuid4())
r = mut(c1, "POST", "/finance/transactions", json=body, headers={"Idempotency-Key": key})
check("add expense 201", r.status_code == 201, r.text[:80])
r2 = mut(c1, "POST", "/finance/transactions", json=body, headers={"Idempotency-Key": key})
check("idempotent replay", r2.json() == r.json())
tid = r.json()["ids"][0]
check("bad amount -> 422", mut(c1, "POST", "/finance/transactions", json={**body, "amount": "1.005"}).status_code == 422)
check("bad category -> 422", mut(c1, "POST", "/finance/transactions", json={**body, "category": "nope"}).status_code == 422)
check("other customer's account -> 404", mut(c2, "POST", "/finance/transactions", json=body).status_code == 404)
check("POST without CSRF -> 403", c1.post("/finance/transactions", json=body).status_code == 403)
after = int([a for a in c1.get("/finance/accounts", params={"customer_id": 1}).json()["accounts"] if a["account_id"] == bank["account_id"]][0]["balance"])
check("balance fell by exactly the amount", before - after == 25050, f"{before - after}")

r = mut(c1, "PATCH", f"/finance/transactions/{tid}/classification", json={"category": "dining", "subcategory": "restaurant", "tags": "birthday"})
check("reclassify expense", r.status_code == 200, r.text[:80])
lst = c1.get("/finance/transactions", params={"customer_id": 1, "q": "Test Mart"}).json()["items"]
check("listing shows new category", lst and lst[0]["category"] == "dining" and lst[0]["subcategory"] == "restaurant")

inc = mut(c1, "POST", "/finance/transactions", json={"type": "income", "amount": "1000", "gross": "1200", "income_type": "freelance",
          "occurred_at": "2026-10-02T11:00:00+05:30", "account_id": bank["account_id"], "merchant": "Client"})
check("add income with gross", inc.status_code == 201, inc.text[:80])
check("gross < net rejected", mut(c1, "POST", "/finance/transactions", json={"type": "income", "amount": "1000", "gross": "900",
      "occurred_at": "2026-10-02T11:00:00+05:30", "account_id": bank["account_id"]}).status_code == 422)
tr = mut(c1, "POST", "/finance/transactions", json={"type": "transfer", "amount": "500", "occurred_at": "2026-10-02T12:00:00+05:30",
         "account_id": bank["account_id"], "to_account_id": sav["account_id"]})
check("own transfer creates two legs", tr.status_code == 201 and len(tr.json()["ids"]) == 2)
ov2 = c1.get("/finance/overview", params={"customer_id": 1, "month": "2026-10"}).json()
n2 = next(m for m in ov2["metrics"] if m["key"] == "net_spending")
check("transfer is not spending (only the 250.50 expense counts)", int(n2["value"]) == 25050, n2["value"])

check("void manual entry", mut(c1, "DELETE", f"/finance/transactions/{tid}").status_code == 200)
ov3 = c1.get("/finance/overview", params={"customer_id": 1, "month": "2026-10"}).json()
check("voided entry no longer counted", int(next(m for m in ov3["metrics"] if m["key"] == "net_spending")["value"]) == 0)
for leg in tr.json()["ids"]:
    mut(c1, "DELETE", f"/finance/transactions/{leg}")
mut(c1, "DELETE", f"/finance/transactions/{inc.json()['ids'][0]}")
base = c1.get("/finance/transactions", params={"customer_id": 1, "limit": 1}).json()["items"][0]
check("bank entries cannot be deleted", mut(c1, "DELETE", f"/finance/transactions/{[i for i in c1.get('/finance/transactions', params={'customer_id': 1, 'limit': 50}).json()['items'] if not i['voidable']][0]['id']}").status_code == 409)

b = mut(c1, "PUT", "/finance/budgets", json={"month": month, "category": "dining", "amount": "9999"})
check("set budget", b.status_code == 200)
bud = c1.get("/finance/budgets", params={"customer_id": 1, "month": month}).json()
check("budget saved", any(r["category"] == "dining" and r["budget"] == "999900" for r in bud["rows"]))

g = mut(c1, "POST", "/finance/goals", json={"name": "e2e goal", "target": "50000", "saved": "1000", "deadline": "2027-06-30"})
check("create goal", g.status_code == 201)
gid = g.json()["goal_id"]
cc = mut(c1, "POST", f"/finance/goals/{gid}/contribute", json={"amount": "500"})
check("contribute", cc.status_code == 200 and cc.json()["saved"] == "150000")
check("other customer cannot contribute", mut(c2, "POST", f"/finance/goals/{gid}/contribute", json={"amount": "1"}).status_code == 404)

q = c1.get("/finance/review-queue", params={"customer_id": 1}).json()
if q["items"]:
    t = q["items"][0]
    cl = mut(c1, "PATCH", f"/finance/transactions/{t['id']}/classification", json={"category": "social", "subcategory": "gifts"})
    q2 = c1.get("/finance/review-queue", params={"customer_id": 1}).json()
    check("classifying removes it from the queue", cl.status_code == 200 and q2["total"] == q["total"] - 1)

check("admin can edit brackets", mut(ad, "PUT", "/finance/brackets/B3", json={"label": "₹40k – ₹1L", "min_inr": 40000, "max_inr": 100000,
      "default_mode": "advanced", "situation": "Stable salary, rent and EMIs begin.", "emphasis": ["Budgets", "EMI tracker"]}).status_code == 200)
check("customer cannot edit brackets", mut(c1, "PUT", "/finance/brackets/B3", json={"label": "x", "min_inr": 0, "max_inr": 1, "default_mode": "simple",
      "situation": "x", "emphasis": []}).status_code == 403)
print("\nALL PASSED" if ok_all else "\nSOME FAILED")
sys.exit(0 if ok_all else 1)
