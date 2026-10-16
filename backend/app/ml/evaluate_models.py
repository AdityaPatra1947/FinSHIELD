"""Independent test of the saved model artifacts (no refitting).

Part A: reload artifacts from disk, verify checksums, rebuild features from the database and score every
        temporal partition and slice with the frozen thresholds.
Part B: generate a brand-new synthetic dataset (different seed => unseen customers) and score it.
Run: python -m app.ml.evaluate_models [--fresh-seed 123]
"""
from __future__ import annotations

import hashlib
import json
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (average_precision_score, brier_score_loss, log_loss, matthews_corrcoef,
                             roc_auc_score)

from app.db import ART, kv_get
from app.ml import features, generator
from app.ml.pipeline import _load
from app.ml.train import FAMILIES, FAMILY_LABEL, PHASES, day_start, heldout_customer

OUT = ART / "results"


def metrics(y: np.ndarray, p: np.ndarray, thr: float | None) -> dict:
    n, pos = len(y), int(y.sum())
    m = {"n": n, "fraud": pos}
    if n == 0 or pos == 0 or pos == n:
        m["note"] = "single class"
        return m
    m["AP"] = average_precision_score(y, p)
    m["ROC_AUC"] = roc_auc_score(y, p)
    m["Brier"] = brier_score_loss(y, p)
    m["LogLoss"] = log_loss(y, np.clip(p, 1e-6, 1 - 1e-6))
    order = np.argsort(-p)
    top1 = max(1, int(round(0.01 * n)))
    m["Recall@1%alerts"] = y[order[:top1]].sum() / pos
    m["Precision@1%alerts"] = y[order[:top1]].mean()
    k = min(100, n)
    m["Precision@100"] = y[order[:k]].mean()
    if thr is not None:
        pr = p >= thr
        tp = int((pr & (y == 1)).sum()); fp = int((pr & (y == 0)).sum()); fn = pos - tp; tn = n - pos - fp
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / pos
        m.update({"Precision": prec, "Recall": rec,
                  "F1": 2 * prec * rec / (prec + rec) if prec == prec and prec + rec else float("nan"),
                  "FPR": fp / (fp + tn), "AlertRate": pr.mean(), "MCC": matthews_corrcoef(y, pr),
                  "TP": tp, "FP": fp, "FN": fn, "TN": tn})
    return m


def part(df, name, cutoff):
    lo, hi = PHASES[name]
    return df[(df.day >= lo) & (df.day <= hi)]


def score(bundles, X):
    return {f: bundles[f]["model"].predict_proba(X)[:, 1] for f in FAMILIES}


def table(rows, cols):
    d = pd.DataFrame(rows)
    return d[[c for c in cols if c in d.columns]]


def main(fresh_seed: int = 123) -> None:
    run = kv_get("latest_run")
    bundles, integrity = {}, {}
    for f in FAMILIES:
        path = ART / "models" / f"{f}.joblib"
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        rec = next(m for m in run["models"] if m["family"] == f)["artifact"]["sha256"]
        bundles[f] = joblib.load(path)
        integrity[f] = {"sha256_matches_run_record": sha == rec, "threshold": bundles[f]["threshold"],
                        "feature_version": bundles[f]["feature_version"], "kb": round(path.stat().st_size / 1024)}
    thr = {f: bundles[f]["threshold"] for f in FAMILIES}

    # ---------------- Part A: stored dataset ----------------
    t0 = time.time()
    tx, cust, labels = _load()
    open_ts = {int(r.customer_id): generator.ORIGIN_TS + (int(r.open_day) - 1) * generator.DAY for r in cust.itertuples()}
    feats = features.build_features(tx, open_ts)
    df = feats.join(labels.set_index("id")[["label", "available_ts"]], how="inner")
    df["heldout"] = df.customer_id.map(heldout_customer)
    df["cold"] = df.n_prior_30d < 5
    X = df[features.ALLOWLIST]
    P = score(bundles, X)
    for f in FAMILIES:
        df[f] = P[f]
    print(f"A: scored {len(df):,} decisions in {time.time() - t0:.0f}s")

    sections: dict[str, pd.DataFrame] = {}
    cols = ["n", "fraud", "AP", "ROC_AUC", "Precision", "Recall", "F1", "FPR", "AlertRate", "MCC", "Brier", "LogLoss",
            "Recall@1%alerts", "Precision@100"]

    def run_slice(name, d):
        rows = []
        for f in FAMILIES:
            r = metrics(d.label.values, d[f].values, thr[f]); r["model"] = FAMILY_LABEL[f]; r["slice"] = name; rows.append(r)
        return rows

    # partitions (mirrors training protocol, existing customers unless noted)
    ex = df[~df.heldout]
    rows = []
    for nm, d in [("train d1-180", ex[(ex.day >= 1) & (ex.day <= 180)]), ("tuning d188-217", part(ex, "tuning", 0)),
                  ("calibration d225-254", part(ex, "calibration", 0)), ("policy d262-291", part(ex, "policy", 0)),
                  ("TEST d299-365 (existing)", part(ex, "test", 0)), ("TEST held-out customers", part(df[df.heldout], "test", 0)),
                  ("TEST cold-start (<5 prior/30d)", part(df, "test", 0)[lambda x: x.cold]),
                  ("TEST all customers", part(df, "test", 0))]:
        rows += run_slice(nm, d)
    sections["Partitions"] = pd.DataFrame(rows)

    test = part(ex, "test", 0)
    rows = []
    for ch, d in test.groupby("channel"):
        rows += run_slice(f"channel={ch}", d)
    for pu, d in test.groupby("purpose"):
        rows += run_slice(f"purpose={pu}", d)
    q = pd.qcut(test.log_amount, 4, labels=["Q1 low", "Q2", "Q3", "Q4 high"])
    for k, d in test.groupby(q, observed=True):
        rows += run_slice(f"amount {k}", d)
    for k, d in test.groupby(pd.cut(test.day, [298, 320, 343, 365], labels=["d299-320", "d321-343", "d344-365"])):
        rows += run_slice(f"time {k}", d)
    sections["Test slices"] = pd.DataFrame(rows)

    # threshold sweep on the locked test (for transparency; thresholds were frozen earlier)
    sweep = []
    for f in FAMILIES:
        y, p = test.label.values, test[f].values
        for t in (0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9):
            pr = p >= t
            tp = int((pr & (y == 1)).sum())
            sweep.append({"model": FAMILY_LABEL[f], "threshold": t, "precision": tp / pr.sum() if pr.sum() else float("nan"),
                          "recall": tp / y.sum(), "alert_rate": pr.mean()})
    sections["Threshold sweep (test)"] = pd.DataFrame(sweep)

    # agreement between models on test alerts
    al = {f: test[f].values >= thr[f] for f in FAMILIES}
    agree = {"all three alert": int(np.logical_and.reduce(list(al.values())).sum()),
             "any alert": int(np.logical_or.reduce(list(al.values())).sum()),
             "fraud caught by >=1 model": int((np.logical_or.reduce(list(al.values())) & (test.label.values == 1)).sum()),
             "fraud missed by all": int((~np.logical_or.reduce(list(al.values())) & (test.label.values == 1)).sum()),
             "test fraud total": int(test.label.sum())}

    # reproducibility vs. the stored training run
    repro = []
    for f in FAMILIES:
        stored = next(m for m in run["models"] if m["family"] == f)["test"]
        now = metrics(test.label.values, test[f].values, thr[f])
        repro.append({"model": FAMILY_LABEL[f], "stored_AP": stored["average_precision"], "retest_AP": now["AP"],
                      "abs_diff": abs(stored["average_precision"] - now["AP"])})
    sections["Reproducibility"] = pd.DataFrame(repro)

    # ---------------- Part B: fresh dataset ----------------
    t1 = time.time()
    c2, tx2, lab2, man2 = generator.generate(600, 365, fresh_seed)
    open2 = {int(r.customer_id): generator.ORIGIN_TS + (int(r.open_day) - 1) * generator.DAY for r in c2.itertuples()}
    f2 = features.build_features(tx2, open2).join(lab2.set_index("id")[["label"]], how="inner")
    P2 = score(bundles, f2[features.ALLOWLIST])
    for f in FAMILIES:
        f2[f] = P2[f]
    print(f"B: fresh dataset seed={fresh_seed}: {len(f2):,} decisions, {int(f2.label.sum())} fraud ({time.time() - t1:.0f}s)")
    rows = []
    for nm, d in [("fresh: all days", f2), ("fresh: d299-365", f2[f2.day >= 299]), ("fresh: d1-298", f2[f2.day < 299])]:
        rows += run_slice(nm, d)
    sections["Fresh unseen dataset"] = pd.DataFrame(rows)

    # ---------------- output ----------------
    fmt = lambda v: "" if v is None or (isinstance(v, float) and v != v) else (f"{v:.4f}" if isinstance(v, float) else str(v))
    md = ["# FinShield model test report (SYNTHETIC DATA)\n", f"Run `{run['run_id']}`; artifacts reloaded from disk; no refitting.\n",
          "## Artifact integrity\n", "| model | sha256 matches run record | threshold | feature version | size KB |", "|---|---|---|---|---|"]
    for f in FAMILIES:
        i = integrity[f]
        md.append(f"| {FAMILY_LABEL[f]} | {i['sha256_matches_run_record']} | {i['threshold']:.4f} | {i['feature_version']} | {i['kb']} |")
    md.append("\n## Alert agreement on locked test (existing customers)\n")
    md += [f"- {k}: {v}" for k, v in agree.items()]
    for title, d in sections.items():
        md.append(f"\n## {title}\n")
        c = ["slice", "model"] + [x for x in cols] if "slice" in d.columns else list(d.columns)
        c = [x for x in c if x in d.columns]
        md.append("| " + " | ".join(c) + " |")
        md.append("|" + "---|" * len(c))
        for _, r in d.iterrows():
            md.append("| " + " | ".join(fmt(r.get(x)) for x in c) + " |")
    (OUT / "model_test_report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    seed = int(sys.argv[sys.argv.index("--fresh-seed") + 1]) if "--fresh-seed" in sys.argv else 123
    main(seed)
