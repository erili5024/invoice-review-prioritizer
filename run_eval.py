"""python run_eval.py [--data file.xlsx] [--seeds 20] [--final]
Default runs the DEV period only. --final also scores the held-out TEST period."""
import argparse, pathlib, json, hashlib, platform, importlib.metadata, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
import core

def md(df):
    c = list(df.columns); out = ["| " + " | ".join(map(str, c)) + " |", "|" + "---|" * len(c)]
    out += ["| " + " | ".join(f"{v:.3f}" if isinstance(v, float) else str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(out)

def report(period, res, by, out):
    a = res.groupby(["method", "budget"]).agg(recall=("recall", "mean"), sd=("recall", "std"), unchanged_flags=("unchanged_flags", "mean"), unchanged_flag_rate=("unchanged_flag_rate", "mean"), unchanged_eligible=("unchanged_eligible", "mean"),
        value_recall=("value_recall", "mean"), oracle=("oracle", "mean")).reset_index()
    order = lambda d: d.reindex(core.METHODS + (["oracle"] if "oracle" in d.index else []))
    pivot = a.pivot(index="method", columns="budget", values="recall"); pivot.loc["oracle"] = a.groupby("budget").oracle.mean()
    pivot = order(pivot); pivot.columns = [f"{b:.0%} budget" for b in pivot.columns]
    five = a[a.budget == .05].set_index("method").loc[core.METHODS].drop(columns="budget").reset_index()
    sev = by.groupby(["type", "severity", "method"]).caught.mean().unstack("method")[core.METHODS].reset_index()
    nohist = by[by.method == "rules"].groupby("type").nohist.mean().reset_index().rename(columns={"nohist": "share_with_no_price_history"})
    txt = f"""## {period.upper()} period ({res.seed.nunique()} random plantings; mean over seeds)
Planted errors per run: {int(res.errors.mean())}. Synthetic stress test, not fraud-prevention performance.

### Recall by review budget (share of planted errors in the top k invoices; oracle = best possible)
{md(pivot.reset_index())}

### At a 5% budget
unchanged_flags = reviewed invoices without a planted error, NOT confirmed clean or wasted attention. unchanged_flag_rate divides by all unchanged eligible invoices. value_recall = share of planted invoices' recorded invoice value caught (GBP, not loss or savings).
{md(five)}

### Recall at 5% by error type and severity (what gets missed)
{md(sev)}

### Planted errors on invoices with no price history for any line
{md(nohist)}
"""
    return txt, a

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data"); ap.add_argument("--prepared",help="Local cache created by audit_data.py only; never load someone else's pickle"); ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--rate", type=float, default=.03); ap.add_argument("--final", action="store_true"); ap.add_argument("--out", default="results")
    a = ap.parse_args(); out = pathlib.Path(a.out)
    if a.seeds<1 or a.seeds>100: raise ValueError("Use 1-100 predeclared seeds")
    if out.exists() and any(out.iterdir()): raise FileExistsError("Output folder is not empty. Use a new folder; never overwrite a final run.")
    out.mkdir(parents=True,exist_ok=True)
    lines = pd.read_pickle(a.prepared) if a.prepared else (core.load_invoices(a.data) if a.data else core.make_synthetic())
    print(("REAL DATA: " + str(a.data or a.prepared)) if (a.data or a.prepared) else "SYNTHETIC DATA", f"| {lines.invoice.nunique()} invoices")
    source_hash=hashlib.sha256(pathlib.Path(a.data).read_bytes()).hexdigest() if a.data else (hashlib.sha256(pathlib.Path(a.prepared).read_bytes()).hexdigest() if a.prepared else "synthetic_seed_0")
    audit=lines.attrs.get("audit",{})
    periods=core.split_periods(lines)
    manifest={"phase":"final" if a.final else "development", "source_sha256":source_hash, "public_zip_sha256":hashlib.sha256(pathlib.Path(__file__).with_name("data").joinpath("uci-online-retail-ii.zip").read_bytes()).hexdigest() if pathlib.Path(__file__).with_name("data").joinpath("uci-online-retail-ii.zip").exists() else None,
      "source":"UCI Online Retail II" if (a.data or a.prepared) else "synthetic demo", "data_audit":audit,
      "periods":{k:{"invoices":v.invoice.nunique(),"rows":len(v),"first":str(v.date.min()),"last":str(v.date.max())} for k,v in periods.items()},
      "settings":{"seeds":list(range(a.seeds)),"rate":a.rate,"budgets":core.BUDGETS,"model_seed":0,"severities":core.SEVERITY,"held_out":core.HELD_OUT,"MIN_HIST":core.MIN_HIST},
      "code_sha256":{f:hashlib.sha256(pathlib.Path(__file__).with_name(f).read_bytes()).hexdigest() for f in ["core.py","run_eval.py"]},
      "python":platform.python_version(), "packages":{k:importlib.metadata.version(k) for k in ["numpy","pandas","scikit-learn"]},
      "claim":"Synthetic stress test; repeated plantings share one underlying dataset and are not independent real populations.",
      "model_fit":"Uninjected earlier F slice, not verified clean; price/quantity references frozen on earlier history. Duplicate references include strictly earlier invoices within scored window, including injected ones."}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2))
    text = ""
    for period in ["dev"] + (["test"] if a.final else []):
        res, by = core.evaluate(lines, period, a.rate, a.seeds); res.to_csv(out / f"{period}_budget.csv", index=False); by.to_csv(out / f"{period}_errors.csv", index=False)
        (out/f"{period}_coverage.json").write_text(json.dumps(res.attrs["coverage"],indent=2))
        t, agg = report(period, res, by, out); text += t + "\n"; print(t)
        fig, ax = plt.subplots(figsize=(6, 4))
        for m in core.METHODS: s = agg[agg.method == m]; ax.plot(s.budget * 100, s.recall, "o-", label=m)
        ax.plot([b * 100 for b in core.BUDGETS], agg.groupby("budget").oracle.mean(), "k--", label="oracle")
        ax.set(xlabel="Review budget (% of invoices)", ylabel="Planted errors caught", title=f"{period}: recall vs budget"); ax.legend(); fig.tight_layout()
        fig.savefig(out / f"{period}_recall_vs_budget.png", dpi=150); plt.close(fig)
    (out / "report.md").write_text(text)
    # Inspection uses DEV only: running development must not expose final-window flags.
    H=core.History(pd.concat([periods["H"],periods["F"]]))
    inv,_,_=(*core.build_features(periods["DEV"],H),H)
    model=core.fit_iforest(core.build_features(periods["F"],core.History(periods["H"]))[0])
    inv["rules"]=core.rules_score(inv); inv["iforest"]=core.iforest_score(model,inv)
    for m in ["rules", "iforest"]:
        q = inv.sort_values(m, ascending=False).head(20).assign(score=lambda d: d[m], why=lambda d: d.apply(core.reasons, axis=1))
        q[["date", "customer", "n_lines", "total", "score", "why"]].to_csv(out / f"inspect_top20_{m}.csv")
    print(f"Evaluation complete. Outputs written to {out}/")

if __name__ == "__main__": main()
