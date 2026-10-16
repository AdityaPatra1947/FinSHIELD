"use client";
import Link from "next/link";
import HeroArt from "@/components/HeroArt";
import Logo from "@/components/Logo";
import { homeFor, useAuth } from "@/lib/auth";

const MODELS = [
  { name: "Logistic Regression", ap: 0.773, p: 0.815, r: 0.652, note: "Linear baseline" },
  { name: "Random Forest", ap: 0.83, p: 0.785, r: 0.755, note: "Bagged trees" },
  { name: "Hist. Gradient Boosting", ap: 0.828, p: 0.887, r: 0.71, note: "Champion · boosted trees", win: true },
];

const ROLES = [
  { href: "/login/customer", title: "Customer", text: "Your spending, refunds, cash wallet and transactions — and add entries of your own." },
  { href: "/login/analyst", title: "Analyst", text: "Fraud review queue, three-model comparison, calibration curves and customer segments." },
  { arrow: true, href: "/login/admin", title: "Administrator", text: "Everything above plus retraining jobs, model promotion and rollback, users and the audit log." },
];

function Arrow() {
  return <i aria-hidden="true">→</i>;
}

export default function Landing() {
  const { me } = useAuth();
  return (
    <div className="lp" id="top">
      <div className="lp-wrap">
        <header className="lp-nav">
          <Logo />
          <ul>
            <li><a href="#top" aria-current="page">Home</a></li>
            <li><a href="#platform">Platform</a></li>
            <li><a href="#models">Models</a></li>
            <li><a href="#security">Security</a></li>
            <li><a href="#access">Access</a></li>
          </ul>
          {me ? (
            <Link className="btn" href={homeFor(me.role)}>Open workspace <Arrow /></Link>
          ) : (
            <details className="menu">
              <summary>Sign in</summary>
              <div className="lp-menu">
                {ROLES.map((r) => (
                  <Link key={r.href} href={r.href}>{r.title}<small>{r.title === "Customer" ? "Personal spending" : r.title === "Analyst" ? "Fraud & ML insights" : "Operations & audit"}</small></Link>
                ))}
              </div>
            </details>
          )}
        </header>

        <section className="hero">
          <div className="hero-copy">
            <div className="eyebrow"><span>01 — Banking analytics<br />on synthetic data</span></div>
            <h1 className="mega" aria-label="Spend. Score. Shield.">
              <span>Spend.</span>
              <span className="outline">Score.</span>
              <span>Shield.</span>
            </h1>
            <p className="hero-sub">
              Exact spending reports from a posted ledger, three fraud models compared on one locked test, and customer
              segments by behaviour. A score is a signal for review, never proof.
            </p>
            <div className="hero-cta">
              {me ? (
                <Link className="btn" href={homeFor(me.role)}>Open your workspace <Arrow /></Link>
              ) : (
                <Link className="btn" href="/login">Sign in <Arrow /></Link>
              )}
              <a className="btn ghost" href="#models">Model results</a>
            </div>
            <dl className="hero-meta">
              <div><dt>Models</dt><dd>3</dd></div>
              <div><dt>Label maturity</dt><dd>7 days</dd></div>
              <div><dt>Fraud prevalence</dt><dd>0.79%</dd></div>
            </dl>
          </div>
          <div className="mascot">
            <HeroArt />
            <div className="bubble" role="note">
              <b>Finn · fraud guard</b>
              <span>I never block payments. I flag the unusual ones for a human to review.</span>
            </div>
          </div>
        </section>
      </div>

      <section className="strip" aria-label="Project at a glance">
        <div className="lp-wrap">
          <div className="cell"><b>600</b><span>Synthetic customers</span></div>
          <div className="cell"><b>196,814</b><span>Ledger transactions</span></div>
          <div className="cell"><b>3</b><span>Fraud model families</span></div>
          <div className="cell"><b>7 days</b><span>Label maturity gap</span></div>
        </div>
      </section>

      <div className="lp-wrap">
        <section className="sec" id="platform">
          <div className="kicker">The platform</div>
          <h2 className="title">Three views of<br />one ledger</h2>
          <p className="lead">Every number is computed once, on the server, from the same posted ledger — so a total on the dashboard always matches the transaction list behind it.</p>
          <div className="feat">
            <article>
              <span className="no">01</span>
              <h3>Spending clarity</h3>
              <p>Gross spending, refunds and net spending side by side. Transfers, cash withdrawals and card repayments never count as spending twice.</p>
            </article>
            <article>
              <span className="no">02</span>
              <h3>Fraud review</h3>
              <p>A calibrated score with plain-language signals — new payee, new device, amount above the usual — and an analyst workflow with an audit trail.</p>
            </article>
            <article>
              <span className="no">03</span>
              <h3>Customer segments</h3>
              <p>KMeans groups customers by behaviour, never by risk. Segments are described in rupees and shares, with stability reported.</p>
            </article>
          </div>
        </section>

        <section className="sec" id="models">
          <div className="kicker">Model comparison</div>
          <h2 className="title">Three models.<br />One honest test.</h2>
          <p className="lead">Logistic Regression, Random Forest and Histogram Gradient Boosting are trained on the same time-ordered splits, calibrated, and scored once on a locked final period.</p>
          <div className="models">
            {MODELS.map((m) => (
              <div key={m.name} className={`mcard${m.win ? " win" : ""}`}>
                <h3>{m.name}</h3>
                <div className="ap">{m.ap.toFixed(3)}</div>
                <div className="small" style={{ opacity: 0.8 }}>Average precision · {m.note}</div>
                <div className="bar" aria-hidden="true"><i style={{ width: `${m.ap * 100}%` }} /></div>
                <dl><dt>Precision</dt><dd>{m.p.toFixed(3)}</dd><dt>Recall</dt><dd>{m.r.toFixed(3)}</dd></dl>
              </div>
            ))}
          </div>
          <p className="fine">Measured on synthetic data (155 fraud cases in the locked test period, existing customers). Good results here do not establish effectiveness on real bank traffic. Sign in as an analyst for curves, calibration and confidence intervals.</p>
        </section>

        <section className="sec" id="security">
          <div className="sec-split">
            <div>
              <div className="kicker">Built carefully</div>
              <h2 className="title">Trust is a<br />feature</h2>
              <p className="lead">A fraud score is an estimate for human review. FinShield never blocks a payment, never moves money, and says so on every screen.</p>
            </div>
            <ul className="checks">
              <li><b>Role-based access.</b> Customers only ever see their own records; other IDs return “not found”.</li>
              <li><b>Hardened sessions.</b> Argon2id passwords, opaque HttpOnly sessions, CSRF checks on every change.</li>
              <li><b>No time travel.</b> Features use only what was known at decision time; labels mature for seven days.</li>
              <li><b>Everything audited.</b> Sign-ins, transactions, alert triage and model promotion are logged.</li>
              <li><b>Failures stay visible.</b> A broken query is an error message, never a reassuring zero.</li>
            </ul>
          </div>
        </section>

        <section className="sec" id="access">
          <div className="kicker">Access</div>
          <h2 className="title">Choose your door</h2>
          <p className="lead">Each role has its own sign-in page. After signing in you land in the workspace that fits your permissions.</p>
          <div className="roles">
            {ROLES.map((r) => (
              <Link key={r.href} href={r.href} className="role">
                <h3>{r.title}</h3>
                <p>{r.text}</p>
                <span className="go">Sign in <i>→</i></span>
              </Link>
            ))}
          </div>
        </section>
      </div>

      <footer className="lp-foot" id="contact">
        <div className="lp-wrap">
          <div>
            <Logo />
            <small>An educational banking and fraud-analytics project. All customers, transactions and fraud labels are synthetic; nothing here connects to a real bank or moves money.</small>
          </div>
          <div>
            <h4>Explore</h4>
            <a href="#platform">Platform</a><a href="#models">Models</a><a href="#security">Security</a>
          </div>
          <div>
            <h4>Sign in</h4>
            <Link href="/login/customer">Customer</Link><Link href="/login/analyst">Analyst</Link><Link href="/login/admin">Administrator</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
