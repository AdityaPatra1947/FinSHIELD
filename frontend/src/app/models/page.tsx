"use client";
import { RoleGate } from "@/lib/auth";
import { useState } from "react";
import { useApi } from "@/lib/api";
import { num } from "@/lib/format";
import { COLORS, HBars, LineChart } from "@/components/Charts";
import { Card, PageHead, State } from "@/components/ui";

type TM = { precision: number | null; recall: number; f1: number | null; fpr: number; alert_rate: number;
  confusion: { tn: number; fp: number; fn: number; tp: number } };
type Slice = { n: number; positives: number; prevalence: number | null; average_precision?: number; roc_auc?: number; brier?: number;
  threshold_metrics?: TM | null; threshold_reason?: string; unsupported_reason?: string };
type Model = {
  family: string; label: string; chosen_params: Record<string, unknown>; threshold: number | null; threshold_status: string;
  threshold_policy: { policy_ap: number; policy_recall?: number; policy_precision?: number; policy_alert_rate?: number };
  test: Slice; test_heldout_customers: Slice; test_cold_start: Slice;
  bootstrap_95ci: { average_precision: number[] | null; recall: number[] | null; skipped_single_class: number };
  curves: { pr: number[][]; roc: number[][]; reliability: number[][] };
  baselines: { ap_reference_prevalence: number; always_legitimate_accuracy: number };
  accuracy: number | null;
  timing: { tuning_seconds: number; final_train_seconds: number; inference_p50_ms: number; inference_p95_ms: number; latency_setting: string };
  artifact: { sha256: string; bytes: number }; permutation_importance: { feature: string; importance: number }[];
  lr_top_coefficients: { feature: string; coef: number }[] | null; lr_not_converged: boolean; trials: { params: unknown; tuning_ap: number }[];
};
type Run = { status: string; run_id: string; seed: number; champion: string | null; champion_rationale: string;
  dataset: { fraud_prevalence: number; transactions: number; customers: number; seed: number; sha256: string; eligible_labeled_decisions: number; fraud_positives: number };
  support: Record<string, { rows: number; positives: number }>; models: Model[]; targets: { precision_min: number; alert_rate_max: number };
  environment: Record<string, string>; total_seconds: number };

const ci = (c: number[] | null) => (c ? `${c[0].toFixed(3)}–${c[1].toFixed(3)}` : "n/a");

function ModelsInner() {
  const r = useApi<Run>("/ml/comparison");
  const [sel, setSel] = useState(0);
  return (
    <>
      <PageHead eyebrow="Insights" title="Model comparison">Logistic Regression, Random Forest and Histogram Gradient Boosting on identical time-ordered splits, calibrated and scored once on a locked test period.</PageHead>
      <State loading={r.loading} error={r.error}>
        {r.data && (() => {
          const run = r.data;
          const m = run.models[sel];
          return (
            <>
              <Card title="Dataset and protocol (synthetic data)">
                <p className="small">{run.dataset.customers} customers · {run.dataset.transactions.toLocaleString()} transactions · {run.dataset.eligible_labeled_decisions.toLocaleString()} labeled decisions ·
                  fraud prevalence {(run.dataset.fraud_prevalence * 100).toFixed(2)}% · seed {run.seed} · sha256 {run.dataset.sha256.slice(0, 12)}… · run {run.run_id} · trained in {run.total_seconds.toFixed(0)}s.</p>
                <p className="small muted">Temporal protocol: train d1–180 → tune d188–217 → refit d1–217 → sigmoid-calibrate d225–254 → thresholds d262–291 → locked test d299–365 (7-day maturity gaps, 10% customer holdout). Operating target: precision ≥ {run.targets.precision_min}, alert rate ≤ {run.targets.alert_rate_max}. Good scores here do not establish effectiveness on real bank traffic.</p>
                <p><a href="/api/v1/ml/metrics.csv">Download metrics CSV</a> · <a href="/api/v1/ml/model-card">Model card (Markdown)</a></p>
              </Card>
              <Card title="Locked final test — existing customers (exactly three models)">
                <div className="scroll"><table>
                  <thead><tr><th>Model</th><th className="n">AP (95% CI)</th><th className="n">ROC-AUC</th><th className="n">Precision</th><th className="n">Recall (95% CI)</th><th className="n">F1</th><th className="n">Alert rate</th><th className="n">Brier</th><th>Threshold</th><th className="n">p50 / p95 ms</th></tr></thead>
                  <tbody>{run.models.map((x, i) => {
                    const t = x.test.threshold_metrics;
                    return (
                      <tr key={x.family} style={{ background: i === sel ? "var(--track)" : undefined }}>
                        <td><button onClick={() => setSel(i)} aria-pressed={i === sel}>{x.label}</button>{run.champion === x.family && <span className="tag"> champion</span>}</td>
                        <td className="n">{num(x.test.average_precision)} <span className="muted small">({ci(x.bootstrap_95ci.average_precision)})</span></td>
                        <td className="n">{num(x.test.roc_auc)}</td><td className="n">{num(t?.precision)}</td>
                        <td className="n">{num(t?.recall)} <span className="muted small">({ci(x.bootstrap_95ci.recall)})</span></td>
                        <td className="n">{num(t?.f1)}</td><td className="n">{num(t?.alert_rate, 4)}</td><td className="n">{num(x.test.brier, 4)}</td>
                        <td>{x.threshold == null ? "constraints unmet" : x.threshold.toFixed(3)}</td>
                        <td className="n">{x.timing.inference_p50_ms.toFixed(1)} / {x.timing.inference_p95_ms.toFixed(1)}</td>
                      </tr>);
                  })}</tbody>
                </table></div>
                <p className="small muted">Test: {m.test.n.toLocaleString()} decisions, {m.test.positives} fraud (prevalence {(m.baselines.ap_reference_prevalence * 100).toFixed(2)}% = AP of a random ranker). Always-legitimate baseline: accuracy {(m.baselines.always_legitimate_accuracy * 100).toFixed(2)}%, recall 0 — accuracy is never used to pick a winner.</p>
                <p><strong>Champion:</strong> {run.champion ? run.models.find((x) => x.family === run.champion)?.label : "none"} — {run.champion_rationale} Selected on the policy set before test labels were opened; promotion remains an explicit administrator action (not available in this local build).</p>
              </Card>
              <div className="grid">
                <Card title={`Precision–recall · ${m.label}`}><LineChart xLabel="Recall" yLabel="Precision" series={run.models.map((x, i) => ({ name: x.label, color: COLORS[i], pts: x.curves.pr, dash: i === sel ? undefined : "4 3" }))} /></Card>
                <Card title="ROC"><LineChart diagonal xLabel="False-positive rate" yLabel="True-positive rate" series={run.models.map((x, i) => ({ name: x.label, color: COLORS[i], pts: x.curves.roc, dash: i === sel ? undefined : "4 3" }))} /></Card>
                <Card title="Calibration (reliability, test)" note="Decile bins by predicted probability; points on the diagonal mean calibrated.">
                  <LineChart diagonal xLabel="Mean predicted probability" yLabel="Observed fraud rate" series={run.models.map((x, i) => ({ name: x.label, color: COLORS[i], pts: x.curves.reliability.map(([a, b]) => [a, b]) }))} />
                </Card>
              </div>
              <div className="grid">
                <Card title={`Confusion matrix · ${m.label}`}>
                  {m.test.threshold_metrics ? (() => { const c = m.test.threshold_metrics.confusion; return (
                    <table><thead><tr><th></th><th className="n">Pred. legit</th><th className="n">Pred. alert</th></tr></thead>
                      <tbody><tr><th>Legitimate</th><td className="n">{c.tn}</td><td className="n">{c.fp}</td></tr><tr><th>Fraud</th><td className="n">{c.fn}</td><td className="n">{c.tp}</td></tr></tbody></table>); })()
                    : <p>Not available: no feasible threshold (constraints unmet). AP, ROC and calibration are still shown.</p>}
                  <p className="small muted">Chosen params: {JSON.stringify(m.chosen_params)}. FPR {num(m.test.threshold_metrics?.fpr, 4)}.</p>
                </Card>
                <Card title="Secondary slices" note="Lower support is shown, not hidden; cold-start rows have few positives so metrics are indicative only.">
                  <table><thead><tr><th>Slice</th><th className="n">n</th><th className="n">Fraud</th><th className="n">AP</th></tr></thead><tbody>
                    {([["Held-out customers", m.test_heldout_customers], ["Cold-start (&lt;5 prior in 30d)", m.test_cold_start]] as [string, Slice][]).map(([n, s]) => (
                      <tr key={n}><td dangerouslySetInnerHTML={{ __html: n }} /><td className="n">{s.n}</td><td className="n">{s.positives}</td>
                        <td className="n">{s.average_precision != null ? s.average_precision.toFixed(3) : <span className="muted small">{s.unsupported_reason}</span>}</td></tr>))}
                  </tbody></table>
                </Card>
                <Card title="Global permutation importance" note="Measured on the tuning set (AP drop). A global ranking does not explain any one transaction.">
                  <HBars items={m.permutation_importance.slice(0, 8).map((p) => ({ label: p.feature.slice(0, 16), value: p.importance, text: p.importance.toFixed(4) }))} />
                </Card>
              </div>
              <Card title="Training details">
                <p className="small">Tuning {m.timing.tuning_seconds.toFixed(1)}s · final fit {m.timing.final_train_seconds.toFixed(1)}s · artifact {(m.artifact.bytes / 1024).toFixed(0)} KB · sha256 {m.artifact.sha256.slice(0, 12)}… · latency: {m.timing.latency_setting}. In-process model latency, not end-to-end API latency.</p>
                <p className="small">Support (rows / positives): {Object.entries(run.support).map(([k, v]) => `${k} ${v.rows}/${v.positives}`).join(" · ")}</p>
                {m.lr_top_coefficients && <p className="small">LR largest standardized coefficients: {m.lr_top_coefficients.slice(0, 6).map((c) => `${c.feature} (${c.coef.toFixed(2)})`).join(", ")}</p>}
                <p className="small muted">Environment: {Object.entries(run.environment).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>
              </Card>
            </>
          );
        })()}
      </State>
    </>
  );
}

export default function Models() {
  return <RoleGate allow={["analyst", "admin"]}><ModelsInner /></RoleGate>;
}

