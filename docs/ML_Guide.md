# FinShield — The Beginner's Guide to the Data, the Database and the Machine Learning

*Written for someone who has never worked with machine learning (ML) or databases (DB). No prior knowledge needed. Every new word is explained the first time it appears, and there is a glossary at the end.*

> **Important:** every customer, transaction and fraud case in this project is **made up by a computer program** (this is called *synthetic data*). Nothing here comes from a real bank or real people.

---

## How to read this guide

| If you have… | Read… |
|---|---|
| 2 minutes | Section 1 only |
| 10 minutes | Sections 1, 2 and 10 (the story, the basic ideas, and the results) |
| An hour | Everything, in order |
| A viva / presentation coming | Sections 6–11, then Section 15 (questions people ask) |

---

## 1. The project in plain words

Imagine you work at a bank. Every day thousands of payments happen. A few of them are **fraud** — someone stole a card or tricked a customer. Checking every payment by hand is impossible, so you want a helper that says:

> *"These 100 payments look unusual — please look at them first."*

**FinShield is that helper.** It does three things:

1. **Shows spending clearly** – how much each customer earned, spent, and got refunded (simple maths, no ML).
2. **Flags suspicious payments** – three different ML "detectives" each give a payment a risk score.
3. **Groups customers by how they spend** – so the bank can understand its customers (a different kind of ML).

**What FinShield will never do:** block a payment, move money, or say "this is definitely fraud". A score is only a *hint for a human to double-check*.

The picture of how everything fits together:

```
   You (browser)  ──►  Website (Next.js)  ──►  Server (FastAPI, Python)  ──►  Database (Neon / PostgreSQL)
                                                     │                              ▲
                                                     ▼                              │
                                          ML models (saved files) ──── training jobs write results back
```

---

## 2. Basic ideas you need (the 10 words that explain everything)

### 2.1 Data, rows and columns
Think of a spreadsheet. Each **row** is one thing (one payment). Each **column** is one fact about it (amount, date, channel).

| id | customer | amount (₹) | channel | time |
|---|---|---|---|---|
| 178883 | 439 | 8,039.90 | netbanking | 01:10 am |

### 2.2 What is a database (DB)?
A database is **a very organised, shared set of spreadsheets** that a program can read and change safely and quickly. Compared with one Excel file:

| Excel file | Database |
|---|---|
| One person edits at a time | Many users and programs at once, safely |
| Slows down at ~100,000 rows | Handles millions of rows quickly |
| Anyone with the file sees everything | Access rules, logins, and a history of changes |
| Easy to break by accident | Rules prevent bad data (e.g. an amount can't be negative) |

- Each "spreadsheet" inside a database is called a **table**. A row is a **record**.
- **PostgreSQL** is a popular database program. **Neon** is a company that runs PostgreSQL *in the cloud* for you, so you don't have to install it. FinShield uses **Neon** (and falls back to a simple file database called **SQLite** if no cloud address is set).
- The program connects using a **connection string** (an address + username + password). It is kept secret in the file `backend/.env` and never shown in the website.
- To find rows quickly, tables have **indexes** — like the index at the back of a textbook.

### 2.3 What is machine learning (ML)?
Normally you write rules by hand: *"if amount > ₹50,000 then flag it."* The problem: fraudsters change tricks, and good rules are hard to write.

**Machine learning means letting the computer find the rules itself by studying many past examples.**
You show it thousands of payments that you already know are fraud or not fraud. It learns patterns such as *"a brand-new payee + a new device + a late-night hour is often fraud."*

### 2.4 Model
The "thing that learned" is called a **model**. After learning, you give it a new payment and it gives back a **probability** (a number from 0 to 1) — "how likely does this look like fraud?" We have **three models** (three different kinds of detective), described in Section 7.

### 2.5 Features ("clues")
The model can't "look" at a payment like a person. We turn each payment into a list of numbers called **features** — clues such as *amount compared with the customer's normal, number of payments in the last hour, is the payee new?*

### 2.6 Labels and "supervised" learning
A **label** is the correct answer for a past example: `1 = fraud`, `0 = not fraud`. Learning from examples that come with correct answers is called **supervised learning**. Our three fraud detectives are supervised.

If there are **no answers** and the computer simply finds natural groups, that is **unsupervised learning**. Our customer grouping (KMeans) is unsupervised.

### 2.7 Training and testing — the exam analogy
- **Training** = studying with past exam papers.
- **Testing** = the real exam with questions the student has **never seen**.

If a student memorises the old papers and sees the same questions in the exam, a high mark proves nothing. In ML this cheating-by-accident is called **overfitting** (memorising instead of understanding). So we always test on data the model never studied.

### 2.8 Imbalanced data — a needle in a haystack
Only **about 8 in every 1,000 payments** (0.79 %) are fraud. A lazy model that says *"never fraud"* would be **99.2 % correct** and completely useless. So we can't judge with plain "percent correct"; we use smarter scores (Section 9).

### 2.9 Leakage — peeking at the answer
**Leakage** means the model accidentally gets information it wouldn't have in real life (for example, tomorrow's news). It makes results look great and then fail for real. Much of this project's design (time-ordered splits, "only use what was known then") exists to **prevent leakage**.

### 2.10 Overall recipe
```
Collect data → create clues (features) → split by time → train 3 models → tune settings
→ calibrate probabilities → choose alert level → test once on untouched data → use it
```

---

## 3. The database in this project — what is stored and why

Everything the app needs lives in Neon (about **64 MB** in total). Here is every table in plain words.

### 3.1 The data tables (the "business" data)

| Table | What it holds | Rows |
|---|---|---|
| **customers** | The 600 made-up customers (name, income, habits) | 600 |
| **transactions** | **The ledger** — every payment, salary, refund, transfer for 365 days | 196,814 |
| **fraud_labels** | For each fraud-eligible payment: was it fraud (1) or not (0), and *when we would have known* | 110,970 |
| **fraud_scores** | The risk score each of the 3 models gave to each test-period payment, plus the reason notes | 21,890 |

Money is stored in **paise** (₹1 = 100 paise) as whole numbers, because computers make tiny rounding errors with decimals and money must be exact. (₹123.45 is stored as `12345`.)

**Example of what a transaction row contains:** customer, amount (paise), direction (money out = debit / in = credit), status (posted / failed / cancelled), purpose (purchase, salary, refund…), category (groceries, rent…), channel (UPI, card, ATM…), time, device and payee (anonymous tokens).

### 3.2 The "running the app" tables

| Table | Purpose |
|---|---|
| **users** | Login accounts. Passwords are **never stored** — only a scrambled version (a *hash*) that can't be turned back into the password. |
| **sessions** | "Who is currently logged in". Each login gets a random secret token; only a scrambled copy is stored. Sessions expire after 30 idle minutes (12 hours max). |
| **audit_events** | A diary of important actions (logins, new transactions, alert changes, model promotions). It is only ever added to, never edited. |
| **jobs** | Background tasks like "retrain the models" and their progress. |
| **results** | Saved outputs of ML runs (metrics, cluster results) as text. |
| **model_promotions** | Which of the 3 models is currently "live" and who chose it and why. |
| **alert_state** | An analyst's notes/status on each flagged payment (open / in review / resolved). |
| **idempotency_keys** | Prevents a double-click from creating the same transaction twice. |

### 3.3 How the app uses the database (one customer action, step by step)
1. A customer fills in "Add transaction" and presses **Add**.
2. The website sends it to the server (with a secret check token so nobody can fake the request).
3. The server checks: *Are you logged in? Is this your account? Is the amount valid?*
4. The server **inserts a new row** into `transactions` and a line into `audit_events`.
5. The next time the customer opens "Spending", the server **reads** their rows from `transactions`, does the maths, and the website draws the charts.

A customer can only ever see **their own** rows. Asking for someone else's data returns "not found".

---

## 4. Where the data comes from (the generator)

We have no real bank data (it is private), so a program called the **generator** (`backend/app/ml/generator.py`) invents it. It uses a fixed "seed" number (42), so running it again gives **exactly the same data**.

### 4.1 Size

| Item | Value |
|---|---|
| Customers | 600 |
| Days covered | 365 (1 Oct 2025 – 30 Sep 2026) |
| Total ledger rows | **196,814** |
| Payments the fraud models judge ("decisions") | **110,970** |
| Of those, fraud | **880** (0.79 %) |
| Payments scored in the test period | 21,890 |

Rows by type: purchases 126,577 · external transfers 16,543 · own transfers 13,396 · card repayments 11,684 · cash withdrawals 9,198 · investments 6,722 · salary 6,694 · fees 3,168 · refunds 2,832.

### 4.2 How a fake customer is created
Each customer gets random traits: how much they earn, how often they pay online, how much they use cash, whether they use a credit card, how many regular people they pay, whether they own a second phone, and when they opened their account (15 % open late — these are "new customers with little history").

### 4.3 Normal behaviour (not fraud)
Each customer makes random payments over the year: mostly purchases (82 %), some transfers to people (14 %), a few ATM withdrawals (4 %). Amounts depend on the category (rent and travel are bigger than snacks). To make the problem **realistic and hard**, normal life includes odd-looking-but-harmless things: 3 % unusually large payments, occasional new payees, an occasional new phone.

### 4.4 Fraud behaviour
Fraud happens in short **bursts** (1 to 6 payments within minutes, half at night). Three styles:

| Style | What it looks like |
|---|---|
| **A** | Money sent to a **brand-new person**, usually 3–10× the customer's normal transfer |
| **B** | Odd **card purchases** at unfamiliar shops |
| **C** | Large round-number **ATM cash-outs** |

30 % of fraud is **stealthy**: same phone, known payee, only slightly bigger amounts. These look almost normal, so even the best model will miss some. That is deliberate — a perfect score would be unbelievable.

### 4.4b Other ledger rows
Monthly salary, rent (28 % of income), investments, transfers between a person's own accounts, cash purchases, credit-card repayments, refunds (about 3 % of purchases) and small transfer fees.

### 4.5 Labels and the 7-day delay
In real life a bank does not know a payment was fraud instantly — the customer complains days later. We copy that: each label becomes "known" **7 days after** the payment. When training, a label is only used if it would **already have been known** at that point in time. This stops the model from learning from information it couldn't have had.

### 4.6 What the fake data does not include
Duplicate bank statements, pending→posted changes, balances before each payment, and real device information. These are listed as limitations.

---

## 5. Splitting the data: the exam analogy in detail

### 5.1 Why we split by *time*, not randomly
Real fraud systems always predict the **future** from the **past**. If we shuffled all payments randomly, the model could "study" a Tuesday payment and be "tested" on the Monday just before it — unfair peeking. So we split along the **calendar**, with small waiting gaps so labels have time to become known.

```
Day:  1 ─────────── 180 │ 188 ── 217 │ 225 ── 254 │ 262 ── 291 │ 299 ─────────── 365
      STUDY (train)       PRACTICE     ADJUST        CHOOSE        REAL EXAM
                          TEST (tune)  (calibrate)   ALERT LEVEL   (final test)
      (gaps of 7 days between blocks let fraud labels become known)
```

### 5.2 How many rows go in each block

| Block | Days | Payments | Fraud cases | What it is for (exam analogy) |
|---|---|---|---|---|
| **Training** | 1 – 180 | 47,193 | 353 | Studying past papers |
| **Tuning** | 188 – 217 | 8,328 | 72 | Practice tests to pick the best study method |
| **Final training** | 1 – 217 | 57,453 | 437 | Re-study using the practice material too |
| **Calibration** | 225 – 254 | 8,431 | 75 | Teaching the student to judge their own confidence honestly |
| **Alert-level selection** | 262 – 291 | 8,784 | 59 | Deciding how strict the examiner should be |
| **Final test** | 299 – 365 | 19,842 | 155 | The real exam — taken **once** |

Two extra groups inside the final-test period:
- **Brand-new customers:** 10 % of customers are completely hidden from training. 2,048 payments, 28 fraud cases. This checks the models work on *people they've never met*.
- **Customers with very little history ("cold start"):** 379 payments but only **2** fraud cases — too few to conclude anything.

### 5.3 The golden rules
1. **The final test is looked at once.** Settings and the "winner" are fixed *before* seeing it.
2. **Validation and test keep the natural 0.79 % fraud rate.** We don't artificially add fraud there.
3. **Minimum evidence:** each important block must contain at least 50 fraud cases, or the run is rejected.
4. **A second exam on a fresh paper:** after training we also generated a **brand-new dataset** (seed 123, 110,774 payments, 882 fraud) and tested the finished models on it (Section 10).

---

## 6. Features — the clues the models use

For every payment we compute these clues **using only what the bank knew at that moment**. (`app/ml/features.py`)

### 6.1 The numeric clues (24)

| Clue group | Name | In simple words |
|---|---|---|
| **How big?** | `log_amount` | The amount, squashed with a log so ₹5 lakh doesn't dwarf everything |
| | `amount_vs_median30` | Amount ÷ this customer's usual (median) amount over 30 days. "3" = three times normal |
| | `amount_dev_mad` | How far from normal, measured in "typical wobbles" |
| | `prior_median30_log` | The customer's usual amount (log) |
| **When?** | `hour_sin`, `hour_cos` | Hour of the day written on a circle, so 11 pm and 1 am count as close |
| | `wday_sin`, `wday_cos`, `is_weekend` | Same idea for day of the week |
| **How fast?** | `n_ok_1h`, `n_ok_24h`, `n_ok_7d` | Successful payments in the last hour / day / week |
| | `sum_ok_24h_log`, `sum_ok_7d_log` | Total money moved in the last day / week |
| | `n_fail_1h`, `n_fail_24h`, `n_fail_7d` | Failed attempts recently (thieves often try repeatedly) |
| | `secs_since_prev_log` | Time since the previous payment (bursts = tiny gaps) |
| **Is it familiar?** | `payee_new` | Never paid this person/shop before? |
| | `device_new` | Never used this phone/device before? |
| | `device_missing` | No device information at all |
| **Account facts** | `account_age_days` | How old the account is |
| | `n_prior_30d` | How much history we have (little history = "cold start") |
| | `no_history` | First-ever payment? |

### 6.2 The category clues (4)
`channel` (UPI / card / netbanking / ATM), `purpose` (purchase / transfer / ATM), `category_known` (groceries, dining… or "unknown"), `account_kind` (bank / credit card).

### 6.3 Clues we deliberately **do not** give the models
The answer (label), later outcomes, review decisions, exact customer/payee/device IDs, balances after the payment, customer cluster, and anything from the future. (This is the anti-leakage rule.)

### 6.4 Getting the data ready
- **Missing numbers** are filled with the usual (median) value, and a "was missing" flag is added so the model knows.
- **Scaling:** for Logistic Regression only, numbers are rescaled to a similar range (like converting everything to "marks out of 100").
- **Categories** (like "UPI") become on/off columns (one-hot). New unseen categories are ignored safely.
- After this, each payment is **48 numbers**.
- All these "usual values" are learned from the *training* data only.

---

## 7. The three detectives (algorithms), explained with analogies

All three receive the same 48 numbers and return a fraud probability. They differ in *how they think*.

### 7.1 Logistic Regression — "the checklist with points"
**Analogy:** a scoring sheet. Each clue earns or loses points: *new payee +3, amount 5× normal +4, daytime −2…* Add them up, then convert the total into a probability (0 to 1) with an S-shaped curve.

- ✔ Very fast, tiny file (8 KB), easy to read which clues matter.
- ✘ It can only add clues independently. It struggles with *"large amount is only suspicious when combined with a new payee at night."*
- **Dial tried (`C`):** how freely the sheet may chase details. Smaller = simpler and safer. Tried 0.1, 1, 10 → **picked 0.1**.

### 7.2 Random Forest — "a committee of 200 voters"
**Analogy:** first meet a **decision tree**: a flow-chart of yes/no questions ("Is the amount > 3× normal? → yes → Is the payee new? → yes → probably fraud"). One tree can be wrong, so we grow **200 different trees**, each looking at a random slice of the data, and **let them vote**. Mistakes cancel out.

- ✔ Handles combinations of clues naturally; little tuning needed.
- ✘ Big file (8.3 MB) and the slowest (≈ 22 ms per payment).
- **Dials tried:** tree depth (10, 20, unlimited) and minimum examples per leaf (2, 10) → **picked depth 20, leaf 2**.

### 7.3 Histogram Gradient Boosting — "a team where each member fixes the last one's mistakes"
**Analogy:** the first small tree makes a rough guess. The second tree studies **only the mistakes** of the first and learns to fix them. The third fixes what's left… 200 rounds. The "histogram" part just makes it faster by grouping number values into buckets.

- ✔ Usually the most accurate on table-like data; small file (0.7 MB), fast.
- ✘ More dials; can over-learn if careless.
- **Dials tried:** learning rate (how big each correction is: 0.05, 0.1) and leaves per tree (15, 31, 63) → **picked rate 0.1, 31 leaves**.

### 7.4 The "balanced" trick
Because fraud is so rare, each fraud example is counted as **heavier** (roughly 125×) while studying, so the models don't just learn to say "never fraud".

### 7.5 How the best settings were chosen ("tuning")
For each detective we trained every setting combo on days 1–180, scored them on days 188–217, and kept the best. Then we re-trained that best one on days 1–217.

| Detective | Combos tried | Best practice score (AP) | Time to tune |
|---|---|---|---|
| Logistic Regression | 3 | 0.846 | 1.5 s |
| Random Forest | 6 | 0.848 | 12 s |
| Hist. Gradient Boosting | 6 | 0.855 | 25 s |

*(AP = "Average Precision", explained in Section 9.)*

---

## 8. Honest probabilities, the alert level, and the winner

### 8.1 Calibration — "teaching the model to be honest about its confidence"
Because of the heavy fraud weighting, a model might say "90 % fraud" when only 30 % of such cases are really fraud — like a thermometer reading 5 degrees too hot. **Calibration** fits a small correction curve (called *sigmoid* or *Platt* scaling) on days 225–254 so that **"0.30" really means "about 30 % of cases like this are fraud."** The detective itself is frozen; only the dial reading is corrected.

### 8.2 The alert level (threshold) — "how sensitive should the alarm be?"
A **threshold** is the score above which we raise an alert. A low threshold catches more fraud but annoys analysts with false alarms; a high threshold is quiet but misses fraud. We pick it on days 262–291 with this rule:

> **Catch as much fraud as possible, but keep at least 80 % of alerts correct, and flag no more than 5 % of payments.**

| Detective | Threshold chosen | Alerts that were correct | Fraud caught (practice) |
|---|---|---|---|
| Logistic Regression | 0.323 | 80 % | 69 % |
| Random Forest | 0.114 | 80 % | 76 % |
| Hist. Gradient Boosting | 0.324 | 90 % | 80 % |

(If no threshold can meet the rule, the model is marked **"constraints unmet"** and is not allowed to go live.)

### 8.3 Picking the champion
Among models that met the rule, the champion has the best **policy-period AP** (then recall, then speed). This was decided **before** the final exam. Winner: **Histogram Gradient Boosting** (AP 0.842 vs 0.820 for Random Forest vs 0.788 for Logistic Regression).

"Promoting" a model to go live is a separate, recorded action by an admin — training never switches anything on by itself.

---

## 9. The scoring factors (metrics) — explained with one worked example

### 9.1 The four boxes (confusion matrix)
Take the champion model on the final test: **19,842 payments, of which 155 were truly fraud.** At its alert level it raised **124 alerts**:

|  | Model said "ALERT" | Model said "fine" | Total |
|---|---|---|---|
| **Really fraud** | **110** (caught — *true positive*) | **45** (missed — *false negative*) | 155 |
| **Really normal** | **14** (false alarm — *false positive*) | **19,673** (correctly quiet — *true negative*) | 19,687 |

Everything below is computed from these four boxes.

### 9.2 Each score in simple words (using the example)

| Score | Plain meaning | Calculation (example) | Result | Why we care |
|---|---|---|---|---|
| **Precision** | "When it shouts *fraud*, how often is it right?" | 110 ÷ (110 + 14) | **0.887** (89 %) | False alarms waste analysts' time |
| **Recall** | "Of all real fraud, how much did it catch?" | 110 ÷ (110 + 45) | **0.710** (71 %) | Missed fraud costs money |
| **F1** | One number balancing precision and recall | 2·P·R ÷ (P + R) | **0.789** | Quick overall balance |
| **False-positive rate** | "Of the normal payments, how many did it wrongly flag?" | 14 ÷ 19,687 | **0.07 %** | How much it bothers honest customers |
| **Alert rate** | "What share of all payments got flagged?" | 124 ÷ 19,842 | **0.62 %** | Analyst workload (limit 5 %) |
| **Accuracy** | "Percent of all answers right" | (110 + 19,673) ÷ 19,842 | 99.7 % | **Misleading!** "Always say fine" already scores 99.22 %, so we never judge by accuracy |
| **MCC** | A fair correlation between prediction and truth, good for rare events (−1 to +1) | from all four boxes | **0.792** | Honest single score |

### 9.3 Scores that don't need a threshold (they judge the *ranking*)
Imagine sorting all payments from "most suspicious" to "least suspicious". A good model puts the real fraud at the top.

| Score | Plain meaning | Good value |
|---|---|---|
| **Average Precision (AP)** | How well real fraud is packed toward the top of the list (area under the precision-recall curve). **Our main score.** A random shuffle scores ≈ 0.008 (the fraud rate). | Closer to **1** |
| **ROC-AUC** | If you pick one fraud and one normal payment at random, how often does the fraud get the higher score? | 0.5 = coin flip, **1** = perfect |
| **Recall @ 1 % alerts** | If analysts can review only the top 1 % of payments, how much fraud is caught? | Higher |
| **Precision @ 100** | Of the 100 highest-scored payments, how many are real fraud? | Higher |

### 9.4 Scores about honest probabilities
| Score | Plain meaning | Good value |
|---|---|---|
| **Brier score** | Average squared gap between the predicted probability and what happened (0 or 1) | Closer to **0** |
| **Log-loss** | Like Brier but punishes confident wrong answers harshly | Closer to **0** |
| **Calibration curve** | Chart: "when it says 30 %, did 30 % happen?" Should follow the diagonal line | On the diagonal |

### 9.5 Scores about uncertainty and cost
| Score | Plain meaning |
|---|---|
| **95 % confidence interval (bootstrap)** | We re-draw the test set 200 times (keeping each customer's payments together) and recompute the score. The spread shows how *shaky* the number is. With only 155 fraud cases, AP is uncertain by about ±0.07. |
| **Latency** | Time to score one payment: Logistic Regression 3.9 ms, Gradient Boosting 10 ms, Random Forest 22 ms. |
| **Feature importance** | "Shuffle one clue and see how much the score drops" → shows which clues the model relies on. |

### 9.6 Which scores are used for what

| Used to **make decisions** | Used only to **report** |
|---|---|
| AP (choose settings, choose champion) | ROC-AUC, F1, MCC, FPR |
| Precision ≥ 0.80 and alert rate ≤ 5 % (pick threshold) | Brier, log-loss, recall@1 %, precision@100 |
| Recall (maximised at the threshold) | Latency, confidence intervals, accuracy (for contrast) |

---

## 10. The results — what they mean

### 10.1 The final exam (locked test: 19,842 payments, 155 fraud)

| Detective | AP | ROC-AUC | Precision | Recall | F1 | False alarms (FPR) | Alert rate |
|---|---|---|---|---|---|---|---|
| Logistic Regression | 0.773 | 0.988 | 0.815 | 0.652 | 0.724 | 0.12 % | 0.62 % |
| Random Forest | **0.830** | 0.985 | 0.785 | **0.755** | 0.770 | 0.16 % | 0.75 % |
| **Hist. Gradient Boosting** | 0.828 | 0.987 | **0.887** | 0.710 | **0.789** | **0.07 %** | 0.62 % |

**In plain words:**
- All three are far better than guessing (AP ≈ 0.77–0.83 vs 0.008 for random).
- **Random Forest and Gradient Boosting are essentially tied** (their confidence ranges overlap heavily). Gradient Boosting gives the fewest false alarms.
- Logistic Regression is a bit weaker, but it is the simplest and fastest.

### 10.2 A second exam on a brand-new dataset (882 fraud cases)

| Detective | AP | Precision | Recall |
|---|---|---|---|
| Logistic Regression | 0.830 | 0.868 | 0.714 |
| Random Forest | 0.869 | 0.803 | 0.821 |
| Hist. Gradient Boosting | **0.880** | 0.878 | 0.801 |

The models still work on completely new customers. (It comes from the same generator, so real life would be tougher.)

### 10.3 Other things we found
- **Customers the models never met:** AP 0.93–0.96 — they didn't just memorise people.
- **Easiest:** ATM fraud. **Harder:** mid-sized amounts, because stealthy fraud looks normal there.
- **18 % of test fraud (28 of 155) was missed by all three** — mostly small, sneaky cases.
- **Repeat check:** reloading the saved model files and testing again reproduced every score exactly, and file checksums matched.
- **Ignore the 1.000 scores** some models show on the training/tuning blocks — they are being tested on what they already studied.
- **Which clues mattered most:** the payment amount, how recently the previous payment was (bursts), whether the device was new, and the spending category.

The full tables are in `artifacts/results/model_test_report.md`.

---

## 11. Customer grouping (KMeans) — sorting people into groups

### 11.1 The idea
**Analogy:** at a party you ask people to stand in groups of similar spenders. You don't tell them the groups in advance. KMeans does this for numbers: it places *k* "meeting points", sends each customer to the nearest, moves each meeting point to the middle of its group, and repeats until nothing changes.

### 11.2 What describes a customer
Their last 90 days: total spending, refunds, typical purchase size, income, cash share, how bumpy their weekly spending is, the share spent on each category, rent share, and spending-to-income ratio. (All 600 qualified: at least 30 days of history and 10 purchases.)

### 11.3 Choosing how many groups (k)
We tried 2 to 6 groups and scored each with the **silhouette** (−1 to 1: how clearly separated the groups are). Groups must each have at least 12 customers.

| Groups (k) | Silhouette | Sizes |
|---|---|---|
| **2 ✓** | **0.160** | 319 / 281 |
| 3 | 0.132 | 172 / 225 / 203 |
| 4 | 0.080 | 132 / 189 / 130 / 149 |
| 5 | 0.080 | 126 / 129 / 149 / 121 / 75 |
| 6 | 0.082 | 75 / 88 / 110 / 90 / 71 / 166 |

### 11.4 The result
1. **"Typical balanced spending"** — 319 customers, about ₹1.03 lakh spent per 90 days, rent about 29 % of spending.
2. **"Higher recurring-bill share, more variable weekly spend"** — 281 customers, about ₹0.72 lakh, rent about 57 %.

A score of 0.16 is low: the groups **overlap a lot** — customers are more of a smooth spread than distinct types. Re-running with 5 other random starts gave nearly identical groups (agreement 0.99–1.00, measured by *Adjusted Rand Index*), so the result is stable.

The scatter plot uses **PCA**, which squashes many numbers into two for drawing. It is only for viewing; the real grouping uses all the numbers. Segments describe *spending style* — they never label anyone as "fraudster" or "risky".

---

## 12. Spending maths (no ML, just careful accounting)

The server calculates these from **posted** payments only:

- **Gross spending** = purchases + fees
- **Expense credits** = refunds
- **Net spending** = gross − credits
- **Income** = salary and other earnings
- **Budget surplus** = income − net spending (and surplus % of income)

Things that are **not** spending (so nothing is counted twice): moving money between your own accounts, withdrawing cash (the *later* cash purchase is the spending), paying off a credit card (the original card purchase was the spending), and investing.
A test in the project checks the textbook example: gross ₹6,900, refunds ₹700, net ₹6,200, income ₹50,000, surplus ₹43,800 (87.6 %).

---

## 13. One payment's whole journey (putting it all together)

1. **Generator** invents the payment and stores it in **`transactions`** (Neon database).
2. If it's a digital debit, it also gets a label in **`fraud_labels`** (known 7 days later).
3. **Feature builder** reads the customer's earlier payments and computes the 48 clue numbers.
4. The three **models** each turn those clues into a calibrated probability.
5. The probabilities and plain-language reasons ("new payee", "amount above usual") are saved in **`fraud_scores`**.
6. If the **promoted model's** probability is above its threshold, the payment appears in the **Fraud review** page.
7. An analyst opens it, changes its state to *in review* or *resolved*; that goes to **`alert_state`** and **`audit_events`**.
8. The score is a hint; the money in the **`transactions`** ledger and the spending totals do not change because of it.

---

## 14. Limitations — please read before quoting numbers

1. **It's a simulation.** The results show the *method* works, not that it would catch real fraud.
2. **The generator has habits models can learn.** (For example, simulated card fraud only uses a few categories.) Real data is messier, so real scores would likely be lower.
3. **Few fraud cases.** 155 in the test period means the scores are fuzzy; a 0.002 difference between two models is just noise.
4. **Some fraud always slips through** (about 18 % in the test), mainly the sneaky kind.
5. **Thresholds depend on one period** (59 fraud cases) and would need re-tuning on new data.
6. **Missing realism:** balances, real device data, duplicate statements.
7. **Never "proof".** A high score only means "worth a human look".

---

## 15. Questions people usually ask

**Why three models instead of one?** To compare different ways of thinking (a checklist, a committee, a team of fixers) fairly on the same data, and to see whether the extra complexity pays off.

**Why not just use accuracy?** Because "never fraud" is 99.2 % accurate. We use AP, precision and recall, which focus on the rare fraud.

**Why is the test used only once?** Looking repeatedly and adjusting would slowly teach the models the test answers, making the final score too optimistic.

**What does 0.83 AP mean?** Roughly: when fraud cases are ranked by score, real fraud sits close to the top most of the time. 1.0 would be perfect; random would be 0.008.

**Is higher recall always better?** Not by itself — you can catch all fraud by flagging everything. That's why we require precision ≥ 0.80 and alert rate ≤ 5 % at the same time.

**What is the difference between the database and the models?** The database *stores facts* (payments, users, scores). The models are *saved files* (`artifacts/models/*.joblib`) that turn clues into probabilities. The database also remembers which model is live.

**Is the clustering related to fraud?** No. It is a separate, unlabeled analysis, and it is never used as a fraud clue.

---

## 16. Try it yourself

**In the app (http://localhost:3000):** sign in as `analyst@gmail.com` / `analyst123` (or the admin account), then open:
- **Model comparison** – all scores, curves, confusion matrix.
- **Fraud review** – flagged payments with their reasons.
- **Customer segments** – the groups.
- **Organization** – charts across all customers.

**Commands** (run in the `backend` folder with the virtual environment active):

| Do this | Command |
|---|---|
| Rebuild everything (data → train → cluster) | `python -m app.ml.pipeline all` |
| Train the three models only | `python -m app.cli train` |
| Re-run the customer grouping | `python -m app.cli cluster` |
| Independently test the saved models | `python -m app.ml.evaluate_models --fresh-seed 123` |

**Where the code lives**

| What | File |
|---|---|
| Invents the data | `backend/app/ml/generator.py` |
| Builds the clues | `backend/app/ml/features.py` |
| Trains, calibrates, scores | `backend/app/ml/train.py` |
| Customer grouping | `backend/app/ml/clustering.py` |
| Independent test | `backend/app/ml/evaluate_models.py` |
| Spending maths | `backend/app/services/spending.py` |
| Database tables & connection | `backend/app/db.py` |
| Saved results | `artifacts/results/` |
| Saved models | `artifacts/models/` |

---

## 17. Glossary (A–Z)

- **Alert / alert rate** – a payment flagged for review / the share of payments flagged.
- **API** – the "waiter" that carries requests between the website and the server.
- **AP (Average Precision)** – our main score: how well real fraud is ranked toward the top.
- **Audit log** – a diary of important actions that is never edited.
- **Bootstrap (statistics)** – re-drawing the test data many times to measure how shaky a score is.
- **Brier score** – accuracy of probabilities; lower is better.
- **Calibration** – correcting probabilities so "30 %" really means 30 %.
- **Class imbalance** – one outcome (fraud) is far rarer than the other.
- **Cluster** – a group of similar customers.
- **Cold start** – a customer with little or no history.
- **Confusion matrix** – the four-box table of caught / missed / false alarms / correct quiet.
- **Database (DB)** – an organised, shared, safe set of tables.
- **Decision tree** – a flow-chart of yes/no questions that ends in a prediction.
- **Ensemble** – many small models combined (committee voting or step-by-step fixing).
- **Feature** – a clue (number) describing a payment.
- **Hash** – a one-way scramble of a password so the real one is never stored.
- **Hyper-parameter ("dial")** – a setting chosen by the builder, not learned.
- **Index** – a lookup structure that makes finding rows fast.
- **KMeans** – a method that sorts items into *k* groups of similar items.
- **Label** – the known correct answer (fraud = 1, not fraud = 0).
- **Leakage** – accidentally peeking at the answer or the future.
- **Logistic Regression** – a points-based model that outputs a probability.
- **Machine learning** – computers learning patterns from examples instead of hand-written rules.
- **Model** – the saved result of learning, used to make predictions.
- **Neon** – a cloud service that hosts PostgreSQL databases.
- **Overfitting** – memorising the practice material instead of learning the pattern.
- **PCA** – a way to squash many numbers into two for plotting.
- **PostgreSQL** – a popular database program (SQLite is a tiny file-based one).
- **Precision** – when it says "fraud", how often it's right.
- **Probability** – a 0-to-1 number for "how likely".
- **Random Forest** – a committee of many decision trees that vote.
- **Recall** – of all real fraud, the share that was caught.
- **ROC-AUC** – chance a random fraud scores higher than a random normal payment.
- **Seed** – a starting number that makes random generation repeatable.
- **Silhouette** – how well separated clusters are (−1 to 1).
- **Supervised / unsupervised** – learning with answers / learning without answers.
- **Synthetic data** – data invented by a program, not collected from real people.
- **Table / row / record** – a "spreadsheet" in a database / one line / the same thing as a row.
- **Threshold** – the score above which an alert is raised.
- **Training / validation / test** – studying / practice exams / the final exam.
- **Tuning** – trying different settings and keeping the best.
