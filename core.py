"""Invoice Review Prioritizer: loading, leakage-safe history features, error injection, detectors, evaluation.
Synthetic stress test on retail transaction data, not fraud-prevention performance."""
from collections import Counter
import numpy as np, pandas as pd
from sklearn.ensemble import IsolationForest

MIN_HIST = 5      # history lines needed before a product/customer baseline is trusted
Z_FLAG = 4.0      # rule thresholds fixed in advance
DUP_FLAG = 0.8
WINDOW = np.timedelta64(30, "D")
COLS = ["invoice", "stockcode", "quantity", "date", "price", "customer"]

# ------------------------------------------------------------------ data
def load_invoices(src, name=None):
    """UCI-compatible invoice lines. Audit exclusions; reject inconsistent invoice identity."""
    name = str(name or src)
    df = pd.concat(pd.read_excel(src, sheet_name=None).values(), ignore_index=True) if name.lower().endswith((".xlsx", ".xls")) else pd.read_csv(src)
    df = df.rename(columns={"Invoice": "invoice", "InvoiceNo": "invoice", "StockCode": "stockcode", "Quantity": "quantity",
                            "InvoiceDate": "date", "Price": "price", "UnitPrice": "price", "Customer ID": "customer", "CustomerID": "customer"})
    required = set(COLS)-{"customer"}
    if not required.issubset(df): raise ValueError("Missing columns: " + str(sorted(required-set(df))))
    if "customer" not in df: df["customer"] = np.nan
    audit = {"raw_rows":len(df), "missing_customer_rows":int(df.customer.isna().sum())}
    df["invoice"] = df.invoice.fillna("").astype(str)
    df["stockcode"] = df.stockcode.fillna("").astype(str)
    df["quantity"] = pd.to_numeric(df.quantity, errors="coerce")
    df["price"] = pd.to_numeric(df.price, errors="coerce")
    df["date"] = pd.to_datetime(df.date, errors="coerce")
    masks = [ ("cancelled",df.invoice.str.upper().str.startswith("C")),
              ("invalid_required",(df.invoice == "")|df.date.isna()|df.quantity.isna()|df.price.isna()|~np.isfinite(df.quantity)|~np.isfinite(df.price)),
              ("nonpositive",(df.quantity<=0)|(df.price<=0)),
              ("nonproduct",~df.stockcode.str.match(r"^\d{5}[A-Za-z]*$")) ]
    keep = pd.Series(True,index=df.index)
    for reason,m in masks:
        audit["excluded_"+reason] = int((keep&m).sum()); keep &= ~m
    df = df[keep].copy()
    df["customer"] = pd.to_numeric(df.customer,errors="coerce").map(lambda v:"" if pd.isna(v) else str(int(v)))
    meta = df.groupby("invoice").agg(n_dates=("date","nunique"),n_customers=("customer","nunique"))
    ambiguous=meta.index[(meta.n_dates>1)|(meta.n_customers>1)]
    audit["ambiguous_invoice_ids"]=len(ambiguous)
    audit["excluded_ambiguous_invoice_rows"]=int(df.invoice.isin(ambiguous).sum())
    df=df[~df.invoice.isin(ambiguous)].copy()
    # Conservative: exclude timestamp/customer conflicts rather than invent availability.

    out = df[COLS].sort_values("date",kind="stable").reset_index(drop=True)
    audit.update(kept_rows=len(out),invoices=out.invoice.nunique(),anonymous_rows=int((out.customer=="").sum()),
                 repeated_exact_lines=int(out.duplicated().sum()))
    out.attrs["audit"] = audit
    return out

def make_synthetic(n_invoices=12000, seed=0):
    """Stand-in with the same schema: stable product prices, customer-specific quantity scales, 20% anonymous customers."""
    r = np.random.default_rng(seed); P, C = 300, 500
    base = np.round(np.exp(r.normal(1.0, .8, P)).clip(.3), 2)
    pop = r.dirichlet(np.ones(P) * .3) + 1e-6; pop /= pop.sum()
    cq = np.exp(r.normal(1.6, .7, C)); cpop = r.dirichlet(np.ones(C))
    t0, rows = pd.Timestamp("2010-12-01"), []
    for i, h in enumerate(np.sort(r.uniform(0, 365 * 24, n_invoices))):
        c = r.choice(C, p=cpop) if r.random() > .2 else -1
        scale, date = (cq[c] if c >= 0 else 8.0), t0 + pd.Timedelta(hours=float(h))
        for p in r.choice(P, min(P, 1 + r.poisson(4)), replace=False, p=pop):
            price = round(base[p] * np.exp(r.normal(0, .03)) * (1 + .0002 * h / 24) * (.9 if r.random() < .05 else 1), 2)
            rows.append((f"{500000 + i}", f"{10000 + p}", max(1, int(round(r.lognormal(np.log(scale), .5)))), date,
                         max(price, .01), "" if c < 0 else str(10000 + c)))
    return pd.DataFrame(rows, columns=COLS)

# ------------------------------------------------------------------ history features
def _robust(df, key, col):
    med = df.groupby(key)[col].median()
    mad = (df[col] - df[key].map(med)).abs().groupby(df[key]).median() * 1.4826
    return pd.DataFrame({"med": med, "mad": mad, "n": df.groupby(key).size()})

class History:
    """Baselines computed ONLY from the (earlier) lines passed in. Medians/MAD reduce sensitivity to some outliers; real history is not verified clean."""
    def __init__(self, lines):
        h = lines.assign(lp=np.log(lines.price), lq=np.log(lines.quantity), amt=lines.price * lines.quantity)
        self.price = _robust(h, "stockcode", "lp")
        self.qprod = _robust(h, "stockcode", "lq")
        self.qcust = _robust(h[h.customer != ""], "customer", "lq")
        g = h.groupby("invoice"); t = pd.DataFrame({"customer": g.customer.first(), "ltot": np.log(g.amt.sum())})
        self.tcust = _robust(t[t.customer != ""], "customer", "ltot")
        med = t.ltot.median(); self.tall = (med, (t.ltot - med).abs().median() * 1.4826)
        self.recent = lines[lines.date >= lines.date.max() - pd.Timedelta(days=30)]  # for duplicate matching

def _ref(L, tbl, key, floor):
    j = tbl.reindex(L[key].to_numpy())
    return j["med"].to_numpy(), np.maximum(j["mad"].to_numpy(), floor), (j["n"].fillna(0) >= MIN_HIST).to_numpy()

def duplicate_scores(lines, recent):
    """For each invoice: best multiset Jaccard similarity of its lines to an earlier invoice (same customer, <=30 days)."""
    allx = pd.concat([recent, lines], ignore_index=True); allx["amt"] = allx.price * allx.quantity
    sets = {}
    for i, k in zip(allx.invoice, zip(allx.stockcode, allx.quantity, allx.price.round(2))): sets.setdefault(i, Counter())[k] += 1
    meta = allx.groupby("invoice").agg(date=("date", "min"), customer=("customer", "first"), total=("amt", "sum"))
    meta["block"] = np.where(meta.customer != "", meta.customer, "T" + meta.total.round(2).astype(str))  # anonymous: match on total
    target, sim, match = set(lines.invoice), {}, {}
    for _, g in meta.sort_values("date").groupby("block"):
        d, ids = g.date.to_numpy(), g.index.to_numpy()
        for i in range(len(ids)):
            if ids[i] not in target: continue
            best, bj = 0.0, None
            for j in range(i - 1, -1, -1):
                if d[i] - d[j] > WINDOW: break
                if d[j] >= d[i]: continue  # equal-time records have no known availability ordering
                a, b = sets[ids[i]], sets[ids[j]]
                s = sum((a & b).values()) / sum((a | b).values())
                if s > best: best, bj = s, ids[j]
            sim[ids[i]], match[ids[i]] = best, bj
    return pd.Series(sim, dtype=float), pd.Series(match, dtype=object)

def build_features(lines, H):
    """Line-level comparisons to history, rolled up to one row per invoice (the unit a reviewer opens)."""
    L = lines.copy(); L["lp"], L["lq"], L["amt"] = np.log(L.price), np.log(L.quantity), L.price * L.quantity
    pm, ps, pok = _ref(L, H.price, "stockcode", .05)
    L["price_ref"] = np.where(pok, np.exp(pm), np.nan)
    L["price_dev"] = np.where(pok, (L.lp - pm).abs(), 0.0); L["price_z"] = np.where(pok, L.price_dev / ps, 0.0)
    cm, cs, cok = _ref(L, H.qcust, "customer", .3); cok = cok & (L.customer != "").to_numpy()
    qm, qs, qok = _ref(L, H.qprod, "stockcode", .3)             # quantity: customer norm, else product norm
    med, sc, ok = np.where(cok, cm, qm), np.where(cok, cs, qs), cok | qok
    L["qty_ref"] = np.where(ok, np.exp(med), np.nan)
    L["qty_dev"] = np.where(ok, (L.lq - med).abs(), 0.0); L["qty_z"] = np.where(ok, L.qty_dev / sc, 0.0)
    L["nohist"] = (~pok).astype(float)
    L["noqtyhist"] = (~ok).astype(float)
    L["customer_fallback"] = (~cok).astype(float)
    inv = L.groupby("invoice", sort=False).agg(date=("date", "min"), customer=("customer", "first"), n_lines=("price", "size"),
        total=("amt", "sum"), price_z=("price_z", "max"), qty_z=("qty_z", "max"), max_price_dev=("price_dev", "max"),
        max_qty_dev=("qty_dev", "max"), nohist=("nohist", "mean"), noqtyhist=("noqtyhist", "mean"), customer_fallback=("customer_fallback", "mean"))
    tl, tj = np.log(inv.total), H.tcust.reindex(inv.customer.to_numpy())
    tok = (tj["n"].fillna(0) >= MIN_HIST).to_numpy() & (inv.customer != "").to_numpy()
    inv["z_total"] = (tl - np.where(tok, tj["med"], H.tall[0])).abs() / np.where(tok, np.maximum(tj["mad"], .3), max(H.tall[1], .3))
    sim, match = duplicate_scores(lines, H.recent)
    inv["dup_sim"], inv["dup_match"] = sim.reindex(inv.index).fillna(0.0), match.reindex(inv.index)
    inv["log_lines"], inv["log_total"] = np.log1p(inv.n_lines), tl
    return inv, L

# ------------------------------------------------------------------ detectors
def rules_score(inv):
    """Transparent: duplicate points (weighted by invoice size, since 1-line repeats are often legitimate) + biggest z (cap 10)."""
    w = np.where(inv.n_lines >= 3, 10, np.where(inv.n_lines == 2, 6, 3))
    return inv.dup_sim.where(inv.dup_sim >= DUP_FLAG, 0) * w + np.minimum(np.maximum(inv.price_z, inv.qty_z), 10)

IF_FEATS = ["max_price_dev", "max_qty_dev", "log_lines", "log_total", "dup_sim", "nohist"]
def fit_iforest(inv, seed=0): return IsolationForest(n_estimators=200, random_state=seed).fit(inv[IF_FEATS])
def iforest_score(m, inv): return -m.score_samples(inv[IF_FEATS])   # higher = more unusual; NOT a probability

def reasons(r):
    out = []
    if r.price_z >= Z_FLAG: out.append(f"a line's price is {np.exp(r.max_price_dev):.1f}x away from that product's usual price")
    if r.qty_z >= Z_FLAG: out.append(f"a line's quantity is {np.exp(r.max_qty_dev):.1f}x away from the usual quantity")
    if r.dup_sim >= DUP_FLAG: out.append(f"line-basket multiset similarity {r.dup_sim:.0%} to earlier invoice {r.dup_match}")
    if r.nohist == 1: out.append("no price history for any line, so prices cannot be checked")
    return "; ".join(out) or "no single rule triggered (unusual combination of features)"

# ------------------------------------------------------------------ periods and app queue
def split_periods(lines):
    """Cutoffs are invoice-date quantiles. Entire invoices belong to one period."""
    dates = lines.groupby("invoice").date.agg(["min","max"])
    if (dates["min"] != dates["max"]).any(): raise ValueError("Invoice dates must be consistent")
    c = [dates["min"].quantile(f) for f in (.35,.50,.70)]
    d = lines.date
    out = {"H":lines[d<c[0]],"F":lines[(d>=c[0])&(d<c[1])],"DEV":lines[(d>=c[1])&(d<c[2])],"TEST":lines[d>=c[2]]}
    if any(v.invoice.nunique()<10 for v in out.values()): raise ValueError("Too few invoices/date diversity for four periods")
    ids=[set(v.invoice) for v in out.values()]
    assert all(not ids[i]&ids[j] for i in range(4) for j in range(i))
    return out

def queue_setup(lines, queue_frac=.25):
    """Latest data = review queue. Earlier data = history; Isolation Forest is fit on a uninjected slice just before the queue."""
    d = lines.date; cq, cf = d.quantile(1 - queue_frac), d.quantile((1 - queue_frac) * .7)
    H0, F, Q = lines[d < cf], lines[(d >= cf) & (d < cq)], lines[d >= cq]
    model = fit_iforest(build_features(F, History(H0))[0])
    Hall = History(pd.concat([H0, F])); inv, L = build_features(Q, Hall)
    inv["rules"], inv["iforest"], inv["largest"], inv["hist_z"] = rules_score(inv), iforest_score(model, inv), inv.total, inv.z_total
    return inv, L, Hall

# ------------------------------------------------------------------ planted errors (spec written before detectors)
SEVERITY = {"price_x": [1.15, 1.5, 2.0], "qty_x": [2, 5, 10], "dup_invoice": ["exact", "near"], "wrong_product": ["near", "mid", "far"]}
DEV_TYPES, HELD_OUT = ["price_x", "qty_x", "dup_invoice"], ["wrong_product"]   # wrong_product only appears in the final test

def inject(lines, types, rate=.03, seed=0, history=None):
    """Plant labelled errors in ~rate of invoices, cycling types and severities. Returns (lines, labels)."""
    r = np.random.default_rng(seed); L = lines.reset_index(drop=True).copy()
    pos = L.groupby("invoice").indices; ids = np.array(list(pos))
    pm, new, labs = (np.exp(history.price.med) if history is not None else None), [], []
    end = L.date.max()
    if not 0 < rate <= .25: raise ValueError("Injection rate must be in (0, .25]")
    for k, inv in enumerate(r.choice(ids, min(len(ids),max(len(types),int(round(rate*len(ids))))), replace=False)):
        t = types[k % len(types)]; sev = SEVERITY[t][(k // len(types)) % len(SEVERITY[t])]; i = int(r.choice(pos[inv])); eid = inv
        if t == "price_x": L.loc[i, "price"] = round(L.price[i] * sev, 2)
        elif t == "qty_x": L.loc[i, "quantity"] = max(int(round(L.quantity[i] * sev)), L.quantity[i] + 1)
        elif t == "wrong_product":
            if pm is None: raise ValueError("wrong_product injection requires earlier history")
            ratio = np.exp((np.log(pm) - np.log(L.price[i])).abs()); lo, hi = {"near": (1.05, 1.3), "mid": (1.3, 2.5), "far": (2.5, 1e9)}[sev]
            cand = pm.index[((ratio >= lo) & (ratio < hi)).to_numpy() & (pm.index != L.stockcode[i])]
            if not len(cand): continue
            L.loc[i, "stockcode"] = r.choice(cand)
        else:  # dup_invoice: a re-entered copy a few hours/days later; 'near' changes one quantity by 1
            c = L.loc[pos[inv]].copy(); eid = f"DUP{k}"; c["invoice"] = eid
            c["date"] = c.date + pd.Timedelta(days=int(r.integers(0, 6)), hours=int(r.integers(1, 12)))
            if c.date.max() > end: continue  # do not extend the evaluation window
            if sev == "near": c.iloc[0, c.columns.get_loc("quantity")] += 1
            new.append(c)
        labs.append((eid, inv, t, str(sev)))
    return pd.concat([L] + new, ignore_index=True), pd.DataFrame(labs, columns=["invoice", "parent_invoice", "type", "severity"])

# ------------------------------------------------------------------ evaluation
BUDGETS, METHODS = [.01, .02, .05, .10], ["random", "largest", "hist_z", "rules", "iforest"]

def ranking(score, ids):
    return np.lexsort((np.asarray(ids,dtype=str),-np.asarray(score)))

def _top(score,k,rng):  # compatibility only; evaluation uses one frozen ranking
    return np.lexsort((rng.random(len(score)),-np.asarray(score)))[:k]   # random tie-break

def evaluate(lines, period="dev", rate=.03, n_seeds=20, model_seed=0):
    """dev: history=H+F, queue=DEV, dev error types. test: history=H+F+DEV, queue=TEST, adds held-out type. No future data used."""
    P = split_periods(lines)
    hist = pd.concat([P["H"], P["F"]] + ([P["DEV"]] if period == "test" else []))
    batch, types = (P["DEV"], DEV_TYPES) if period == "dev" else (P["TEST"], DEV_TYPES + HELD_OUT)
    model = fit_iforest(build_features(P["F"], History(P["H"]))[0], model_seed); H = History(hist)
    rows, by = [], []
    original,_ = build_features(batch,H)
    coverage = coverage_summary(original)
    for s in range(n_seeds):
        rng = np.random.default_rng(1000 + s); inj, lab = inject(batch, types, rate, seed=s,history=H)
        inv, _ = build_features(inj, H); y = inv.index.isin(lab.invoice); E = int(y.sum()); tot = inv.total.to_numpy()
        typ = pd.Series(inv.index).map(dict(zip(lab.invoice, lab.type))).to_numpy()
        sev = pd.Series(inv.index).map(dict(zip(lab.invoice, lab.severity))).to_numpy()
        scores = {"random": rng.random(len(inv)), "largest": tot, "hist_z": inv.z_total.to_numpy(),
                  "rules": rules_score(inv).to_numpy(), "iforest": iforest_score(model, inv)}
        for m, v in scores.items():
            order = ranking(v,inv.index)
            for b in BUDGETS:
                k = int(np.ceil(b * len(inv))); top = order[:k]; hit = int(y[top].sum())
                rows.append(dict(seed=s, method=m, budget=b, k=k, errors=E, recall=hit / E, oracle=min(1, k / E),
                                 unchanged_flags=k-hit, unchanged_eligible=len(inv)-E, unchanged_flag_rate=(k-hit)/(len(inv)-E), invoices=len(inv), value_recall=tot[top][y[top]].sum() / tot[y].sum()))
            caught = np.zeros(len(inv), bool); caught[order[:int(np.ceil(.05*len(inv)))]] = True
            d = pd.DataFrame({"type": typ, "severity": sev, "caught": caught, "nohist": inv.nohist.to_numpy() == 1})[y]
            d.insert(0, "method", m); d.insert(0, "seed", s); by.append(d)
    res=pd.DataFrame(rows); res.attrs["coverage"]=coverage
    return res, pd.concat(by)


def coverage_summary(inv):
    n=len(inv)
    return {"invoices":n,"all_lines_price_history":int((inv.nohist==0).sum()),
            "partial_price_history":int(((inv.nohist>0)&(inv.nohist<1)).sum()),
            "no_price_history":int((inv.nohist==1).sum()),
            "all_lines_quantity_history":int((inv.noqtyhist==0).sum()),
            "any_customer_quantity_fallback":int((inv.customer_fallback>0).sum()),
            "all_lines_price_history_rate":float((inv.nohist==0).mean()),
            "note":"All invoices remain rankable; missing references use zero deviation and explicit history indicators. Coverage is not error-detection accuracy."}