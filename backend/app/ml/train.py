"""Three-model fraud experiment: LR / RF / HGB only (spec section 10).

Temporal protocol, sigmoid calibration on a frozen estimator, policy-set threshold
selection, locked one-shot test evaluation. Writes results JSON, model cards, CSV and
trusted joblib artifacts under ARTIFACT_ROOT.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import platform
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                             precision_recall_curve, roc_auc_score, roc_curve)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.ml.features import ALLOWLIST, CATEGORICAL, FEATURE_VERSION, NUMERIC
from app.ml.generator import DAY, ORIGIN_TS

SEED = 42
FAMILIES = ["logistic_regression", "random_forest", "hist_gradient_boosting"]
FAMILY_LABEL = {"logistic_regression": "Logistic Regression", "random_forest": "Random Forest",
                "hist_gradient_boosting": "Histogram Gradient Boosting"}
PHASES = {  # inclusive event days
    "train": (1, 180), "tuning": (188, 217), "calibration": (225, 254),
    "policy": (262, 291), "test": (299, 365),
}
MIN_POS = 50
PRECISION_TARGET, ALERT_RATE_MAX = 0.80, 0.05


def day_start(d: int) -> int:
    return ORIGIN_TS + (d - 1) * DAY


def heldout_customer(cid: int) -> bool:
    return int(hashlib.md5(f"finshield-holdout-{cid}".encode()).hexdigest(), 16) % 10 == 0


def _pre(scale: bool) -> ColumnTransformer:
    num = [("imp", SimpleImputer(strategy="median", add_indicator=True))]
    if scale:
        num.append(("sc", StandardScaler()))
    return ColumnTransformer([
        ("num", Pipeline(num), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
    ])


def make_pipeline(family: str, p: dict) -> Pipeline:
    if family == "logistic_regression":
        return Pipeline([("pre", _pre(True)), ("clf", LogisticRegression(
            C=p["C"], class_weight="balanced", max_iter=2000, random_state=SEED))])
    if family == "random_forest":
        return Pipeline([("pre", _pre(False)), ("clf", RandomForestClassifier(
            n_estimators=200, max_depth=p["max_depth"], min_samples_leaf=p["min_samples_leaf"],
            class_weight="balanced", random_state=SEED, n_jobs=4))])
    return Pipeline([("pre", _pre(False)), ("clf", HistGradientBoostingClassifier(
        learning_rate=p["learning_rate"], max_leaf_nodes=p["max_leaf_nodes"], max_iter=200,
        early_stopping=False, class_weight="balanced", random_state=SEED))])


GRIDS = {
    "logistic_regression": [{"C": c} for c in (0.1, 1, 10)],
    "random_forest": [{"max_depth": d, "min_samples_leaf": l}
                      for d, l in itertools.product((10, 20, None), (2, 10))],
    "hist_gradient_boosting": [{"learning_rate": lr, "max_leaf_nodes": m}
                               for lr, m in itertools.product((0.05, 0.1), (15, 31, 63))],
}


def _slice_metrics(y, p, thr) -> dict:
    n = int(len(y))
    pos = int(np.sum(y))
    out = {"n": n, "positives": pos, "prevalence": (pos / n) if n else None}
    if n == 0 or pos == 0 or pos == n:
        out["unsupported_reason"] = "slice has a single class or is empty"
        return out
    out["average_precision"] = float(average_precision_score(y, p))
    out["roc_auc"] = float(roc_auc_score(y, p))
    out["brier"] = float(brier_score_loss(y, p))
    if thr is None:
        out["threshold_metrics"] = None
        out["threshold_reason"] = "no feasible threshold (constraints unmet)"
    else:
        pred = p >= thr
        tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn)
        out["threshold_metrics"] = {
            "precision": prec, "recall": float(rec),
            "f1": (2 * prec * rec / (prec + rec)) if prec and rec else None,
            "fpr": float(fp / (fp + tn)), "alert_rate": float(pred.mean()),
            "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}}
    return out


def choose_threshold(y, p) -> dict:
    """Max recall s.t. precision>=0.8 and alert rate<=0.05; ties: precision, then higher threshold."""
    order = np.argsort(-p, kind="stable")
    ps, ys = p[order], y[order]
    tp = np.cumsum(ys)
    k = np.arange(1, len(ys) + 1)
    last_of_tie = np.r_[ps[1:] != ps[:-1], True]  # only cut at distinct probability values
    prec = tp / k
    rate = k / len(ys)
    ok = last_of_tie & (prec >= PRECISION_TARGET) & (rate <= ALERT_RATE_MAX)
    if not ok.any():
        return {"status": "constraints_unmet", "threshold": None}
    rec = tp / max(ys.sum(), 1)
    cand = np.where(ok)[0]
    best = max(cand, key=lambda i: (rec[i], prec[i], ps[i]))
    return {"status": "feasible", "threshold": float(ps[best]), "policy_recall": float(rec[best]),
            "policy_precision": float(prec[best]), "policy_alert_rate": float(rate[best])}


def _curve_pts(x, y, n=120):
    idx = np.unique(np.linspace(0, len(x) - 1, min(n, len(x))).astype(int))
    return [[float(x[i]), float(y[i])] for i in idx]


def run_experiment(feats: pd.DataFrame, labels: pd.DataFrame, art_dir: Path, dataset_manifest: dict,
                   log=print) -> dict:
    t_all = time.time()
    df = feats.join(labels.set_index("id")[["label", "available_ts"]], how="inner")
    df["heldout"] = df.customer_id.map(heldout_customer)
    df["cold"] = df.n_prior_30d < 5

    def part(name, fit_cutoff_day, include_heldout=False):
        lo, hi = PHASES[name]
        m = (df.day >= lo) & (df.day <= hi) & (df.available_ts <= day_start(fit_cutoff_day))
        if not include_heldout:
            m &= ~df.heldout
        return df[m]

    train = part("train", 188)
    final_fit = df[(df.day >= 1) & (df.day <= 217) & (df.available_ts <= day_start(225)) & ~df.heldout]
    tuning = part("tuning", 225)
    calib = part("calibration", 262)
    policy = part("policy", 299)
    t_lo, t_hi = PHASES["test"]
    test = df[(df.day >= t_lo) & (df.day <= t_hi)]
    test_exist, test_held = test[~test.heldout], test[test.heldout]

    support = {n: {"rows": int(len(d)), "positives": int(d.label.sum())} for n, d in
               [("train", train), ("final_fit", final_fit), ("tuning", tuning), ("calibration", calib),
                ("policy", policy), ("test_existing", test_exist), ("test_heldout_customers", test_held),
                ("test_cold_start", test[test.cold])]}
    problems = [f"{n}: {support[n]['positives']} positives (<{MIN_POS})" for n in
                ("tuning", "calibration", "policy", "test_existing") if support[n]["positives"] < MIN_POS]
    if train.label.nunique() < 2:
        problems.append("train: single class")
    if problems:
        return {"status": "invalid", "problems": problems, "support": support}, None, None
    log("support:", support)

    X = lambda d: d[ALLOWLIST]
    results, artifacts = {}, {}
    for fam in FAMILIES:
        log(f"== {fam}")
        t0 = time.time()
        trials = []
        for p in GRIDS[fam]:
            t1 = time.time()
            pipe = make_pipeline(fam, p).fit(X(train), train.label)
            fit_s = time.time() - t1
            ap = average_precision_score(tuning.label, pipe.predict_proba(X(tuning))[:, 1])
            trials.append({"params": p, "tuning_ap": float(ap), "fit_seconds": fit_s})
            log("  ", p, f"AP={ap:.4f} fit={fit_s:.1f}s")
        best = min(trials, key=lambda r: (-round(r["tuning_ap"], 12), r["fit_seconds"]))
        tuning_s = time.time() - t0
        t1 = time.time()
        base = make_pipeline(fam, best["params"]).fit(X(final_fit), final_fit.label)
        train_s = time.time() - t1
        nonconv = fam == "logistic_regression" and base.named_steps["clf"].n_iter_[0] >= 2000
        cal = CalibratedClassifierCV(FrozenEstimator(base), method="sigmoid").fit(X(calib), calib.label)
        pol_p = cal.predict_proba(X(policy))[:, 1]
        pol = choose_threshold(policy.label.values, pol_p)
        thr = pol["threshold"]
        pol["policy_ap"] = float(average_precision_score(policy.label, pol_p))

        te_p = cal.predict_proba(X(test_exist))[:, 1]
        y = test_exist.label.values
        he_p = cal.predict_proba(X(test_held))[:, 1]
        co = test[test.cold]
        co_p = cal.predict_proba(X(co))[:, 1]
        main = _slice_metrics(y, te_p, thr)
        prec_c, rec_c, _ = precision_recall_curve(y, te_p)
        fpr, tpr, _ = roc_curve(y, te_p)
        bins = np.linspace(0, 1, 11)
        qs = np.quantile(te_p, np.linspace(0, 1, 11))
        rel = []
        for a, b in zip(qs[:-1], qs[1:]):
            m = (te_p >= a) & (te_p <= b) if b == qs[-1] else (te_p >= a) & (te_p < b)
            if m.sum():
                rel.append([float(te_p[m].mean()), float(y[m].mean()), int(m.sum())])
        # customer-block bootstrap (200 resamples)
        rng = np.random.default_rng(SEED)
        groups = pd.Series(np.arange(len(y))).groupby(test_exist.customer_id.values).apply(np.asarray)
        garr = list(groups.values)
        aps, recs, skipped = [], [], 0
        for _ in range(200):
            idx = np.concatenate([garr[i] for i in rng.integers(0, len(garr), len(garr))])
            yy, pp = y[idx], te_p[idx]
            if yy.min() == yy.max():
                skipped += 1
                continue
            aps.append(average_precision_score(yy, pp))
            if thr is not None:
                recs.append(((pp >= thr) & (yy == 1)).sum() / yy.sum())
        ci = lambda a: [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))] if a else None
        # latency (in-process, batch 1, warm)
        if fam == "random_forest":
            base.named_steps["clf"].set_params(n_jobs=1)
        sample = X(test_exist).iloc[:200]
        cal.predict_proba(sample.iloc[:5])
        lat = []
        for i in range(len(sample)):
            s = time.perf_counter()
            cal.predict_proba(sample.iloc[i:i + 1])
            lat.append((time.perf_counter() - s) * 1000)
        # permutation importance (validation/tuning set, base pipeline)
        sub = tuning.sample(min(6000, len(tuning)), random_state=SEED)
        pi = permutation_importance(base, X(sub), sub.label, scoring="average_precision",
                                    n_repeats=3, random_state=SEED, n_jobs=1)
        imp = sorted(({"feature": f, "importance": float(m)} for f, m in zip(ALLOWLIST, pi.importances_mean)),
                     key=lambda r: -r["importance"])[:15]
        n_enc = int(base.named_steps["pre"].transform(X(train).iloc[:5]).shape[1])
        art_path = art_dir / "models" / f"{fam}.joblib"
        art_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"family": fam, "feature_version": FEATURE_VERSION, "allowlist": ALLOWLIST,
                     "model": cal, "threshold": thr, "sklearn": sklearn.__version__}, art_path)
        sha = hashlib.sha256(art_path.read_bytes()).hexdigest()
        coef = None
        if fam == "logistic_regression":
            names = base.named_steps["pre"].get_feature_names_out()
            c = base.named_steps["clf"].coef_[0]
            top = np.argsort(-np.abs(c))[:12]
            coef = [{"feature": str(names[i]), "coef": float(c[i])} for i in top]
        results[fam] = {
            "family": fam, "label": FAMILY_LABEL[fam], "chosen_params": best["params"], "trials": trials,
            "threshold_policy": pol, "threshold": thr,
            "threshold_status": pol["status"],
            "test": main,
            "test_heldout_customers": _slice_metrics(test_held.label.values, he_p, thr),
            "test_cold_start": _slice_metrics(co.label.values, co_p, thr),
            "bootstrap_95ci": {"average_precision": ci(aps), "recall": ci(recs), "resamples": 200,
                               "skipped_single_class": skipped},
            "curves": {"pr": _curve_pts(rec_c[::-1], prec_c[::-1]), "roc": _curve_pts(fpr, tpr),
                       "reliability": rel},
            "baselines": {"ap_reference_prevalence": float(y.mean()),
                          "always_legitimate_accuracy": float(1 - y.mean()),
                          "always_legitimate_recall": 0.0},
            "accuracy": float(((te_p >= thr) == y).mean()) if thr is not None else None,
            "timing": {"tuning_seconds": tuning_s, "final_train_seconds": train_s,
                       "inference_p50_ms": float(np.percentile(lat, 50)),
                       "inference_p95_ms": float(np.percentile(lat, 95)),
                       "latency_setting": "in-process, batch size 1, warm, single thread, 200 rows"},
            "artifact": {"path": str(art_path.name), "sha256": sha, "bytes": art_path.stat().st_size},
            "encoded_columns": n_enc,
            "lr_not_converged": bool(nonconv),
            "permutation_importance": imp, "lr_top_coefficients": coef,
            "missing_rates": {c: float(test_exist[c].isna().mean()) for c in
                              ("amount_vs_median30", "device_new", "secs_since_prev_log")},
        }
        artifacts[fam] = (cal, X)
        log(f"   test AP={main.get('average_precision')} thr={thr} status={pol['status']}")

    feasible = [r for r in results.values() if r["threshold_status"] == "feasible"]
    champion = None
    if feasible:
        champion = max(feasible, key=lambda r: (r["threshold_policy"]["policy_ap"],
                                                r["threshold_policy"]["policy_recall"],
                                                -r["timing"]["inference_p50_ms"]))["family"]
    run = {
        "status": "completed", "run_id": time.strftime("%Y%m%d-%H%M%S"), "seed": SEED,
        "feature_version": FEATURE_VERSION, "dataset": dataset_manifest, "support": support,
        "phases": PHASES, "targets": {"precision_min": PRECISION_TARGET, "alert_rate_max": ALERT_RATE_MAX},
        "champion": champion,
        "champion_rationale": ("Highest policy-set AP among families with a feasible threshold; frozen before test."
                               if champion else
                               "No family met precision>=0.80 with alert rate<=0.05 on the policy set. "
                               "No operational threshold exists; promotion and automatic alerting stay disabled."),
        "models": [results[f] for f in FAMILIES],
        "environment": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                        "numpy": np.__version__, "pandas": pd.__version__, "platform": platform.platform()},
        "total_seconds": time.time() - t_all,
        "phase_notes": "Calendar-day phases with 7-day maturity gaps; label availability enforced via available_ts.",
    }
    return run, artifacts, {"test_exist": test_exist, "test": test}


def write_reports(run: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest_run.json").write_text(json.dumps(run, indent=2, default=float))
    rows = ["family,average_precision,roc_auc,precision,recall,f1,fpr,alert_rate,brier,threshold,threshold_status,"
            "p50_ms,p95_ms,artifact_bytes,test_n,test_positives"]
    for m in run["models"]:
        t, tm = m["test"], (m["test"].get("threshold_metrics") or {})
        rows.append(",".join(str(x) for x in [
            m["family"], t.get("average_precision"), t.get("roc_auc"), tm.get("precision"), tm.get("recall"),
            tm.get("f1"), tm.get("fpr"), tm.get("alert_rate"), t.get("brier"), m["threshold"],
            m["threshold_status"], m["timing"]["inference_p50_ms"], m["timing"]["inference_p95_ms"],
            m["artifact"]["bytes"], t["n"], t["positives"]]))
    (out / "metrics.csv").write_text("\n".join(rows) + "\n")
    md = ["# Model card - FinShield fraud classifiers (SYNTHETIC DATA)\n",
          f"Run `{run['run_id']}`, seed {run['seed']}, feature version `{run['feature_version']}`.\n",
          "Good scores here do not establish effectiveness on real bank traffic. A score is an estimate for review, "
          "not proof of fraud.\n", "## Dataset\n", "```json", json.dumps(run["dataset"], indent=2), "```\n",
          "## Feature allowlist\n", ", ".join(ALLOWLIST) + "\n",
          "Excluded: labels, identifiers, scenario flags, post-event balances, cluster IDs, free text.\n",
          "## Splits and support\n", "```json", json.dumps({"phases": run["phases"], "support": run["support"]}, indent=2),
          "```\n", "## Results (locked final test, existing customers)\n",
          "| Model | AP | ROC-AUC | Precision | Recall | Threshold | Status |", "|---|---|---|---|---|---|---|"]
    f = lambda v: "n/a" if v is None else f"{v:.4f}"
    for m in run["models"]:
        t, tm = m["test"], (m["test"].get("threshold_metrics") or {})
        md.append(f"| {m['label']} | {f(t.get('average_precision'))} | {f(t.get('roc_auc'))} | "
                  f"{f(tm.get('precision'))} | {f(tm.get('recall'))} | {f(m['threshold'])} | {m['threshold_status']} |")
    md += ["", f"**Champion:** {run['champion'] or 'none'} - {run['champion_rationale']}", "",
           "## Limitations\n", "- Synthetic generator; labels have simple structure.",
           "- No evidence-duplicate layer, balances, or real device telemetry.",
           "- Reason codes are contextual signals, not causal explanations.", "",
           "## Bootstrap (200 customer-block resamples)\n"]
    for m in run["models"]:
        md.append(f"- {m['label']}: {json.dumps(m['bootstrap_95ci'])}")
    (out / "model_card.md").write_text("\n".join(md))
