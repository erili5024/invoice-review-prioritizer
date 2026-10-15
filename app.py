"""streamlit run app.py : ranked invoice review queue with reasons, history comparison, decisions and export."""
import io, pandas as pd, streamlit as st, core
st.set_page_config(page_title="Invoice Review Prioritizer", layout="wide")
st.title("Invoice Review Prioritizer")
st.info("Retail sales data has no verified error labels. Review notes last only for this session unless exported.")
st.caption("Ranks invoices by how unusual they look against earlier history. A high rank means 'look here first', not 'fraud'. A bulk order or repeat purchase can be legitimate.")

@st.cache_data(show_spinner="Scoring invoices...")
def prepare(raw, name, queue_frac):
    lines = core.load_invoices(io.BytesIO(raw), name) if raw else core.make_synthetic(6000)
    inv, L, _ = core.queue_setup(lines, queue_frac)
    return lines, inv, L

up = st.sidebar.file_uploader("Invoice lines (CSV or XLSX)", type=["csv", "xlsx"], help="One row per line: Invoice, StockCode, Quantity, InvoiceDate, Price, Customer ID")
if not up: st.sidebar.info("No file uploaded: showing synthetic demo data.")
frac = st.sidebar.slider("Latest share of the timeline to review", .10, .50, .25, .05)
names = {"Transparent rules": "rules", "Isolation Forest": "iforest", "Largest invoices": "largest", "Historical z-score (invoice total)": "hist_z"}
method = names[st.sidebar.radio("Ranking method", list(names))]
budget = st.sidebar.slider("Review budget (% of invoices)", 1, 20, 5)
try:
    lines, inv, L = prepare(up.getvalue() if up else None, up.name if up else None, frac)
except (ValueError,KeyError,TypeError) as e:
    st.error("Could not score this file: "+str(e)); st.stop()

k = max(1, int(round(len(inv) * budget / 100)))
q = inv.assign(score=inv[method]).sort_values("score", ascending=False).head(k).copy()
q["why"] = q.apply(core.reasons, axis=1) if method in ("rules", "iforest") else ""
st.subheader(f"Review queue: top {k} of {len(inv)} invoices ({budget}%)")
if method == "iforest": st.caption("Isolation Forest scores how unusual an invoice's combination of features is. The score is not a probability of fraud. Reasons shown are the rule checks, not the model's own explanation.")
st.dataframe(q[["date", "customer", "n_lines", "total", "score", "why"]].round(2), width="stretch", height=300)

sel = st.selectbox("Open an invoice", q.index)
r = inv.loc[sel]; st.markdown(f"**Invoice {sel}**: {r.n_lines} lines, total {r.total:,.2f}, customer {r.customer or 'unknown'}. {core.reasons(r)}")
cols = ["stockcode", "quantity", "price", "price_ref", "price_z", "qty_ref", "qty_z"]
st.caption("price_ref / qty_ref = what history says is usual (median). z = how many robust spreads away. Blank = not enough history.")
st.dataframe(L[L.invoice == sel][cols].round(2), width="stretch")
if r.dup_match is not None and r.dup_sim >= .5:
    a, b = st.columns(2)
    a.markdown(f"**This invoice** ({sel})"); a.dataframe(lines[lines.invoice == sel][["stockcode", "quantity", "price", "date"]], width="stretch")
    b.markdown(f"**Closest earlier match** ({r.dup_match}, {r.dup_sim:.0%} basket similarity)"); b.dataframe(lines[lines.invoice == r.dup_match][["stockcode", "quantity", "price", "date"]], width="stretch")

dec = st.session_state.setdefault("dec", {})
choice = st.radio("Your decision", ["Worth investigating", "Legitimate", "Unsure"], horizontal=True, key=f"d_{sel}")
note = st.text_input("Note (why?)", key=f"n_{sel}")
if st.button("Save decision"):
    dec[sel] = dict(invoice=sel, decision=choice, note=note, method=method, score=round(float(q.loc[sel, "score"]), 3)); st.success("Saved for this session. Export CSV before closing.")
if dec:
    out = pd.DataFrame(dec.values()); st.subheader("Your review notes"); st.dataframe(out, width="stretch")
    st.download_button("Export review notes (CSV)", out.to_csv(index=False), "review_notes.csv", "text/csv")