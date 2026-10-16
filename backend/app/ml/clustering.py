"""KMeans customer segmentation (spec section 11). Separate from fraud; never a fraud label."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from app.ml.generator import DAY
from app.services.spending import CREDITS, GROSS, INCOME

FEATURE_VERSION = "cf1"
CATS = ["groceries", "dining", "transport", "shopping", "entertainment", "health", "utilities", "travel", "education", "rent", "fees"]
LOG_FEATS = ["gross_inr", "credits_inr", "median_purchase_inr", "income_inr", "weekly_cv"]


def customer_features(tx: pd.DataFrame, as_of_ts: int, window_days: int = 90) -> pd.DataFrame:
    start = as_of_ts - window_days * DAY
    d = tx[(tx.status == "posted") & (tx.posted_ts >= start) & (tx.posted_ts < as_of_ts)]
    rows = []
    first_seen = tx[tx.status == "posted"].groupby("customer_id").posted_ts.min()
    for cid, g in d.groupby("customer_id"):
        gross = g[g.purpose.isin(GROSS)]
        pur = g[(g.purpose == "purchase") & (g.direction == "debit")]
        tg = gross.amount_minor.sum()
        weekly = gross.groupby(((gross.posted_ts - start) // (7 * DAY))).amount_minor.sum()
        weekly = weekly.reindex(range(int(window_days // 7)), fill_value=0)
        cats = gross.groupby(gross.category).amount_minor.sum()
        r = {"customer_id": cid, "purchases": len(pur),
             "coverage_days": (as_of_ts - first_seen.get(cid, as_of_ts)) / DAY,
             "gross_inr": tg / 100, "credits_inr": g[g.purpose.isin(CREDITS)].amount_minor.sum() / 100,
             "median_purchase_inr": (pur.amount_minor.median() / 100) if len(pur) else np.nan,
             "income_inr": g[g.purpose.isin(INCOME)].amount_minor.sum() / 100,
             "cash_share": (gross[gross.account_kind == "cash"].amount_minor.sum() / tg) if tg else np.nan,
             "weekly_cv": (weekly.std() / weekly.mean()) if weekly.mean() > 0 else np.nan}
        for c in CATS:
            r[f"share_{c}"] = (cats.get(c, 0) / tg) if tg else np.nan
        # recurring: fixed monthly rent purchases (rule-based; full recurring-pattern detection is not built yet)
        rec = pur[pur.category == "rent"]
        r["recurring_share"] = (rec.amount_minor.sum() / pur.amount_minor.sum()) if len(pur) else np.nan
        rows.append(r)
    f = pd.DataFrame(rows).set_index("customer_id")
    all_c = tx.customer_id.unique()
    f = f.reindex(all_c)
    f["purchases"] = f.purchases.fillna(0)
    f["coverage_days"] = f.coverage_days.fillna(0)
    f["eligible"] = (f.coverage_days >= 30) & (f.purchases >= 10)
    return f


def run_clustering(tx: pd.DataFrame, as_of_ts: int, seed: int = 42) -> dict:
    f = customer_features(tx, as_of_ts)
    elig = f[f.eligible].copy()
    n = len(elig)
    status = pd.Series("insufficient_history", index=f.index)
    base = {"as_of_ts": as_of_ts, "feature_version": FEATURE_VERSION, "seed": seed, "customers_total": int(len(f)),
            "eligible": int(n)}
    feat_cols = [c for c in f.columns if c not in ("purchases", "coverage_days", "eligible")]
    if n < 20:
        return {**base, "status": "insufficient_segmentation_evidence", "clusters": [], "assignments": []}
    X = elig[feat_cols].copy()
    X["income_ratio"] = np.where(X.income_inr > 0, X.gross_inr / X.income_inr.replace(0, np.nan), np.nan)
    X["income_missing"] = (~(X.income_inr > 0)).astype(float)
    for c in LOG_FEATS + ["income_ratio"]:
        X[c] = np.log1p(X[c].clip(lower=0))
    cols = list(X.columns)
    Z = StandardScaler().fit_transform(SimpleImputer(strategy="median").fit_transform(X))
    min_size = max(10, math.ceil(0.02 * n))
    cands = []
    for k in range(2, min(6, n - 1) + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(Z)
        sizes = np.bincount(km.labels_, minlength=k)
        sil = float(silhouette_score(Z, km.labels_)) if n <= 10000 else float(
            silhouette_score(Z, km.labels_, sample_size=10000, random_state=seed))
        cands.append({"k": k, "silhouette": sil, "inertia": float(km.inertia_), "sizes": sizes.tolist(),
                      "passes_support": bool(sizes.min() >= min_size), "model": km})
    ok = [c for c in cands if c["passes_support"]]
    if not ok:
        return {**base, "status": "insufficient_segmentation_evidence",
                "candidates": [{k: v for k, v in c.items() if k != "model"} for c in cands],
                "clusters": [], "assignments": []}
    best_sil = max(c["silhouette"] for c in ok)
    chosen = min((c for c in ok if c["silhouette"] >= best_sil - 0.01), key=lambda c: c["k"])
    km = chosen["model"]
    labels = km.labels_
    # stability across 5 seeds (ARI vs chosen seed)
    aris = [float(adjusted_rand_score(labels, KMeans(n_clusters=chosen["k"], n_init=10, random_state=s).fit_predict(Z)))
            for s in (1, 2, 3, 4, 5)]
    pca = PCA(n_components=2, random_state=seed).fit(Z)
    xy = pca.transform(Z)
    dist = np.linalg.norm(Z - km.cluster_centers_[labels], axis=1)
    elig = elig.assign(cluster=labels, x=xy[:, 0], y=xy[:, 1], distance=dist)
    overall = elig[["gross_inr", "median_purchase_inr", "cash_share", "recurring_share", "weekly_cv", "income_inr"]].median()
    clusters = []
    for k in range(chosen["k"]):
        m = elig[elig.cluster == k]
        med = m[["gross_inr", "credits_inr", "median_purchase_inr", "income_inr", "cash_share",
                 "recurring_share", "weekly_cv", "purchases"] + [f"share_{c}" for c in CATS]].median()
        top = sorted(CATS, key=lambda c: -med[f"share_{c}"])[:3]
        traits = []
        if med.gross_inr > 1.2 * overall.gross_inr:
            traits.append("higher spending")
        elif med.gross_inr < 0.8 * overall.gross_inr:
            traits.append("lower spending")
        if med.purchases > 1.2 * elig.purchases.median():
            traits.append("frequent smaller purchases" if med.median_purchase_inr < overall.median_purchase_inr
                          else "frequent purchases")
        if med.recurring_share > 1.2 * overall.recurring_share:
            traits.append("higher recurring-bill share")
        if med.cash_share > 1.3 * max(overall.cash_share, 1e-9):
            traits.append("more cash use")
        if med.weekly_cv > 1.2 * overall.weekly_cv:
            traits.append("more variable weekly spend")
        name = ", ".join(traits[:2]) if traits else "typical balanced spending"
        clusters.append({"cluster_id": k, "name": name[0].upper() + name[1:], "size": int(len(m)),
                         "median_gross_spending_inr": float(med.gross_inr), "median_net_spending_inr":
                         float(med.gross_inr - med.credits_inr), "median_income_inr": float(med.income_inr),
                         "median_purchase_inr": float(med.median_purchase_inr), "median_purchases": float(med.purchases),
                         "cash_share": float(med.cash_share) if med.cash_share == med.cash_share else None,
                         "recurring_share": float(med.recurring_share), "weekly_cv": float(med.weekly_cv),
                         "top_categories": [{"category": c, "share": float(med[f"share_{c}"])} for c in top]})
    assignments = [{"customer_id": int(i), "cluster_id": int(r.cluster), "x": float(r.x), "y": float(r.y),
                    "distance": float(r.distance), "gross_inr": float(r.gross_inr)} for i, r in elig.iterrows()]
    status.loc[elig.index] = "assigned"
    return {**base, "status": "completed", "k": chosen["k"], "silhouette": chosen["silhouette"],
            "inertia": chosen["inertia"], "min_cluster_size_required": min_size,
            "k_rationale": "max silhouette among k=2..6 with min cluster size >= max(10, 2%); ties within 0.01 pick smaller k",
            "candidates": [{k: v for k, v in c.items() if k != "model"} for c in cands],
            "stability_ari": {"values": aris, "min": min(aris), "max": max(aris), "mean": float(np.mean(aris))},
            "pca_variance": [float(v) for v in pca.explained_variance_ratio_],
            "pca_note": "PCA is a visualisation only; KMeans ran on the full standardised feature set.",
            "features_used": cols,
            "counts": {"assigned": int(len(elig)), "insufficient_history": int((~f.eligible).sum()),
                       "eligible_but_unassigned": 0},
            "clusters": clusters, "assignments": assignments,
            "statuses": {int(i): s for i, s in status.items()}}
