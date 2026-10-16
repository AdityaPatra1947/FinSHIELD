/** Minor-unit strings -> INR display. Display only; totals are computed by the backend. */
export function inr(minor: string | null | undefined): string {
  if (minor == null) return "Not available";
  const neg = minor.startsWith("-");
  const digits = minor.replace("-", "").padStart(3, "0");
  const whole = BigInt(digits.slice(0, -2)).toLocaleString("en-IN");
  return `${neg ? "-" : ""}₹${whole}.${digits.slice(-2)}`;
}
export const pct = (v: number | null | undefined, d = 1) => (v == null ? "Not available" : `${v.toFixed(d)}%`);
export const num = (v: number | null | undefined, d = 3) => (v == null ? "n/a" : v.toFixed(d));

export const MODEL_NAMES: Record<string, string> = { logistic_regression: "Logistic Regression", random_forest: "Random Forest", hist_gradient_boosting: "Hist. Gradient Boosting" };
export const modelName = (f: string | null | undefined) => (f ? MODEL_NAMES[f] ?? f : "None");
