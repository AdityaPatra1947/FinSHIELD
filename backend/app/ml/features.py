"""Point-in-time fraud feature builder (feature version fv1).

History for a decision at time t uses only prior digital debit attempts of the same
customer with ts strictly < t (equal-time rows excluded), never the row itself, never
labels, later statuses, balances (not simulated) or cluster IDs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_VERSION = "fv1"
IST_OFFSET = 19800
HOUR, DAYS_S = 3600, 86400

NUMERIC = [
    "log_amount", "amount_vs_median30", "amount_dev_mad", "no_history",
    "hour_sin", "hour_cos", "wday_sin", "wday_cos", "is_weekend",
    "n_ok_1h", "n_ok_24h", "n_ok_7d", "sum_ok_24h_log", "sum_ok_7d_log",
    "n_fail_1h", "n_fail_24h", "n_fail_7d",
    "payee_new", "device_new", "device_missing", "secs_since_prev_log",
    "prior_median30_log", "account_age_days", "n_prior_30d",
]
CATEGORICAL = ["channel", "purpose", "category_known", "account_kind"]
ALLOWLIST = NUMERIC + CATEGORICAL


def build_features(tx: pd.DataFrame, open_day: dict[int, int] | None = None) -> pd.DataFrame:
    """tx: ledger rows. Returns one feature row per eligible *posted* decision (index = id).

    Failed/cancelled digital attempts contribute to history features only.
    """
    att = tx[tx.eligible].sort_values(["customer_id", "ts", "id"], kind="stable").reset_index(drop=True)
    out_cols: dict[str, np.ndarray] = {k: np.full(len(att), np.nan) for k in NUMERIC}
    pos = 0
    for cid, g in att.groupby("customer_id", sort=False):
        n = len(g)
        ts = g.ts.values.astype(np.int64)
        amt = g.amount_minor.values.astype(np.int64)
        ok = (g.status.values == "posted")
        fail = ~ok
        c_ok = np.concatenate([[0], np.cumsum(ok)])
        c_fail = np.concatenate([[0], np.cumsum(fail)])
        c_amt = np.concatenate([[0], np.cumsum(np.where(ok, amt, 0))])
        hi = np.searchsorted(ts, ts, "left")  # all rows with ts < t (excludes equal-time and self)
        res = {k: np.full(n, np.nan) for k in NUMERIC}
        lo = {w: np.searchsorted(ts, ts - s, "left") for w, s in
              (("1h", HOUR), ("24h", DAYS_S), ("7d", 7 * DAYS_S), ("30d", 30 * DAYS_S))}
        for w in ("1h", "24h", "7d"):
            res[f"n_ok_{w}"] = (c_ok[hi] - c_ok[lo[w]]).astype(float)
            res[f"n_fail_{w}"] = (c_fail[hi] - c_fail[lo[w]]).astype(float)
        res["sum_ok_24h_log"] = np.log1p((c_amt[hi] - c_amt[lo["24h"]]) / 100.0)
        res["sum_ok_7d_log"] = np.log1p((c_amt[hi] - c_amt[lo["7d"]]) / 100.0)
        res["n_prior_30d"] = (hi - lo["30d"]).astype(float)
        med = np.full(n, np.nan)
        mad = np.full(n, np.nan)
        okamt = np.where(ok, amt, -1)
        for i in range(n):
            a, b = lo["30d"][i], hi[i]
            if b > a:
                w = okamt[a:b]
                w = w[w >= 0]
                if len(w):
                    m = np.median(w)
                    med[i] = m / 100.0
                    mad[i] = np.median(np.abs(w - m)) / 100.0
        a_inr = amt / 100.0
        res["amount_vs_median30"] = a_inr / np.maximum(med, 1.0)
        res["amount_dev_mad"] = (a_inr - med) / np.maximum(mad, 1.0)
        res["prior_median30_log"] = np.log1p(med)
        res["no_history"] = (hi == 0).astype(float)
        prev = np.where(hi > 0, ts - ts[np.maximum(hi - 1, 0)], np.nan)
        res["secs_since_prev_log"] = np.log1p(prev)
        res["log_amount"] = np.log1p(a_inr)
        local = ts + IST_OFFSET
        hr = (local % DAYS_S) / HOUR
        wd = ((local // DAYS_S) + 3) % 7  # 1970-01-01 was Thursday(3)
        res["hour_sin"], res["hour_cos"] = np.sin(2 * np.pi * hr / 24), np.cos(2 * np.pi * hr / 24)
        res["wday_sin"], res["wday_cos"] = np.sin(2 * np.pi * wd / 7), np.cos(2 * np.pi * wd / 7)
        res["is_weekend"] = (wd >= 5).astype(float)
        payee = g.payee_token.values
        dev = g.device_token.values
        seen_p: set = set()
        seen_d: set = set()
        pn = np.zeros(n)
        dn = np.full(n, np.nan)
        # familiarity: token not seen in any strictly earlier attempt
        i = 0
        while i < n:
            j = i
            while j < n and ts[j] == ts[i]:
                j += 1
            for k in range(i, j):
                pn[k] = float(payee[k] not in seen_p)
                if dev[k] is not None and dev[k] == dev[k]:
                    dn[k] = float(dev[k] not in seen_d)
            for k in range(i, j):
                seen_p.add(payee[k])
                if dev[k] is not None and dev[k] == dev[k]:
                    seen_d.add(dev[k])
            i = j
        res["payee_new"] = pn
        res["device_new"] = dn  # NaN = device missing (distinct from new)
        res["device_missing"] = np.array([float(d is None or d != d) for d in dev])
        first_ts = ts[0]
        od = (open_day or {}).get(int(cid))
        res["account_age_days"] = (ts - (od if od is not None else first_ts)) / DAYS_S
        for k in NUMERIC:
            out_cols[k][pos:pos + n] = res[k]
        pos += n
    feats = pd.DataFrame(out_cols)
    feats["id"] = att.id.values
    feats["customer_id"] = att.customer_id.values
    feats["ts"] = att.ts.values
    feats["day"] = att.day.values
    feats["status"] = att.status.values
    feats["channel"] = att.channel.values
    feats["purpose"] = att.purpose.values
    feats["account_kind"] = att.account_kind.values
    feats["category_known"] = att.category.fillna("unknown").values
    feats = feats[feats.status == "posted"].drop(columns="status").set_index("id")
    return feats
