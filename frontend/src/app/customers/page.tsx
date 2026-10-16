"use client";
import { RoleGate } from "@/lib/auth";
import { useState } from "react";
import { useApi } from "@/lib/api";
import { inr } from "@/lib/format";
import { Scatter } from "@/components/Charts";
import { Card, PageHead, State } from "@/components/ui";

type Cluster = { cluster_id: number; name: string; size: number; median_gross_spending_inr: number; median_net_spending_inr: number;
  median_income_inr: number; median_purchase_inr: number; median_purchases: number; cash_share: number | null; recurring_share: number;
  top_categories: { category: string; share: number }[] };
type Res = { status: string; k?: number; silhouette?: number; inertia?: number; eligible: number; customers_total: number;
  min_cluster_size_required?: number; k_rationale?: string; candidates?: { k: number; silhouette: number; sizes: number[]; passes_support: boolean }[];
  stability_ari?: { min: number; max: number; mean: number }; pca_variance?: number[]; pca_note?: string;
  counts?: { assigned: number; insufficient_history: number; eligible_but_unassigned: number };
  clusters: Cluster[]; assignments: { customer_id: number; cluster_id: number; x: number; y: number; gross_inr: number }[]; as_of_ts: number };
type Cust = { total: number; items: { customer_id: number; masked: string; cluster_id: number | null; cluster_name: string | null }[] };

const PAL = ["#226192", "#EF8557", "#3f8f7a", "#8a5a9e", "#b8860b", "#5d7183"];
const money = (v: number) => inr(String(Math.round(v * 100)));

function SegmentsInner() {
  const r = useApi<Res>("/clusters/latest");
  const [page, setPage] = useState(1);
  const c = useApi<Cust>(`/customers?page=${page}&size=15`);
  return (
    <>
      <PageHead eyebrow="Insights" title="Customer segments">KMeans groups customers by how they spend, never by risk. Profiles are in rupees and shares of spend.</PageHead>
      <State loading={r.loading} error={r.error}>
        {r.data && r.data.status !== "completed" && <Card title="Insufficient segmentation evidence"><p>No candidate k met the minimum cluster-size support, so eligible customers stay unassigned and no labels are forced.</p></Card>}
        {r.data && r.data.status === "completed" && (
          <>
            <p className="small">KMeans k={r.data.k} · silhouette {r.data.silhouette?.toFixed(3)} · inertia {r.data.inertia?.toFixed(0)} · eligible {r.data.eligible} of {r.data.customers_total} customers
              (assigned {r.data.counts?.assigned} + insufficient history {r.data.counts?.insufficient_history} + unassigned {r.data.counts?.eligible_but_unassigned}) ·
              window: 90 days before the cutoff · stability ARI over 5 seeds {r.data.stability_ari?.min.toFixed(2)}–{r.data.stability_ari?.max.toFixed(2)}.
              Segments describe spending behavior only — they are not fraud or credit-risk labels. Cluster IDs are meaningful only within this run.</p>
            <div className="grid">
              {r.data.clusters.map((k) => (
                <Card key={k.cluster_id} title={`Cluster ${k.cluster_id}: ${k.name}`}>
                  <p className="small">{k.size} customers · <span style={{ color: PAL[k.cluster_id % 6] }}>■</span> {["●", "■", "▲"][k.cluster_id % 3]} on the plot</p>
                  <table><tbody>
                    <tr><th>Median gross spend / 90d</th><td className="n">{money(k.median_gross_spending_inr)}</td></tr>
                    <tr><th>Median net spend / 90d</th><td className="n">{money(k.median_net_spending_inr)}</td></tr>
                    <tr><th>Median income / 90d</th><td className="n">{money(k.median_income_inr)}</td></tr>
                    <tr><th>Median purchase</th><td className="n">{money(k.median_purchase_inr)}</td></tr>
                    <tr><th>Purchases / 90d</th><td className="n">{k.median_purchases.toFixed(0)}</td></tr>
                    <tr><th>Cash share</th><td className="n">{k.cash_share == null ? "Not available" : `${(k.cash_share * 100).toFixed(1)}%`}</td></tr>
                    <tr><th>Recurring-bill share</th><td className="n">{(k.recurring_share * 100).toFixed(1)}%</td></tr>
                    <tr><th>Top categories</th><td className="n">{k.top_categories.map((t) => `${t.category} ${(t.share * 100).toFixed(0)}%`).join(", ")}</td></tr>
                  </tbody></table>
                </Card>))}
            </div>
            <div className="grid">
              <Card title="PCA view (visualization only)" note={`${r.data.pca_note} Variance shown: ${(r.data.pca_variance ?? []).map((v) => (v * 100).toFixed(0) + "%").join(" + ")}.`}>
                <Scatter colors={PAL} pts={r.data.assignments.map((a) => ({ x: a.x, y: a.y, c: a.cluster_id, t: `CUST-${String(a.customer_id).padStart(4, "0")} · cluster ${a.cluster_id}` }))} />
              </Card>
              <Card title="Choice of k" note={r.data.k_rationale}>
                <table><thead><tr><th>k</th><th className="n">Silhouette</th><th>Sizes</th><th>Support ok</th></tr></thead><tbody>
                  {r.data.candidates?.map((x) => <tr key={x.k}><td>{x.k}{x.k === r.data!.k ? " ✓" : ""}</td><td className="n">{x.silhouette.toFixed(3)}</td><td>{x.sizes.join("/")}</td><td>{x.passes_support ? "yes" : "no"}</td></tr>)}
                </tbody></table>
              </Card>
            </div>
          </>
        )}
      </State>
      <Card title="Customers (masked, synthetic)">
        <State loading={c.loading} error={c.error}>
          {c.data && (<>
            <table><thead><tr><th>Customer</th><th>Segment</th></tr></thead><tbody>
              {c.data.items.map((x) => <tr key={x.customer_id}><td>{x.masked}</td><td>{x.cluster_name ? `${x.cluster_id}: ${x.cluster_name}` : "insufficient history"}</td></tr>)}
            </tbody></table>
            <p><button disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button>{" "}
              <button disabled={page * 15 >= c.data.total} onClick={() => setPage(page + 1)}>Next</button> <span className="muted small">{c.data.total} customers</span></p>
          </>)}
        </State>
      </Card>
    </>
  );
}

export default function Segments() {
  return <RoleGate allow={["analyst", "admin"]}><SegmentsInner /></RoleGate>;
}
