import numpy as np, pandas as pd, core
LINES = core.make_synthetic(3000, seed=1); P = core.split_periods(LINES)

def test_features_ignore_later_invoices():
    H = core.History(pd.concat([P["H"], P["F"]])); b = P["TEST"]; inv1, _ = core.build_features(b, H)
    cut = b.date.quantile(.5); b2 = b.copy(); m = b2.date >= cut; b2.loc[m, "price"] *= 3; b2.loc[m, "quantity"] *= 7
    inv2, _ = core.build_features(b2, H); early = inv1.index[inv1.date < cut]; cols = ["price_z", "qty_z", "z_total", "dup_sim", "nohist"]
    pd.testing.assert_frame_equal(inv1.loc[early, cols], inv2.loc[early, cols])

def test_insufficient_history_is_not_flagged():
    inv, L = core.build_features(LINES.iloc[3:20], core.History(LINES.iloc[:3]))
    assert (L.price_z == 0).all() and (L.nohist == 1).all()

def test_injection_touches_only_labelled_invoices():
    b = P["DEV"]; inj, lab = core.inject(b, core.DEV_TYPES, .05, seed=3)
    assert set(lab.type) == set(core.DEV_TYPES) and lab.invoice.is_unique
    a, c = b[~b.invoice.isin(lab.invoice)], inj[~inj.invoice.isin(lab.invoice)]
    pd.testing.assert_frame_equal(a.reset_index(drop=True), c.reset_index(drop=True))

def test_exact_duplicate_scores_one():
    inj, lab = core.inject(P["DEV"], ["dup_invoice"], .03, seed=5)
    inv, _ = core.build_features(inj, core.History(pd.concat([P["H"], P["F"]])))
    assert (inv.loc[lab[lab.severity == "exact"].invoice, "dup_sim"] == 1).all()

def test_recall_bounded_by_oracle_and_random_is_weak():
    res, by = core.evaluate(LINES, "dev", .03, n_seeds=3)
    assert (res.recall <= res.oracle + 1e-9).all()
    assert res[(res.method == "random") & (res.budget == .10)].recall.mean() < .35

def test_equal_time_not_prior():
    x = pd.DataFrame([("A", "10001", 1, pd.Timestamp("2020-01-01"), 5, "1"),
                      ("B", "10001", 1, pd.Timestamp("2020-01-01"), 5, "1")], columns=core.COLS)
    sim, match = core.duplicate_scores(x, x.iloc[:0])
    assert (sim == 0).all()

def test_duplicate_multiplicity():
    a = pd.DataFrame([("A", "10001", 1, pd.Timestamp("2020-01-01"), 5, "1")], columns=core.COLS)
    b = pd.DataFrame([("B", "10001", 1, pd.Timestamp("2020-01-02"), 5, "1")] * 2, columns=core.COLS)
    assert core.duplicate_scores(b, a)[0]["B"] == .5

def test_budget_breakdown_consistency():
    res, by = core.evaluate(LINES, "dev", n_seeds=3)
    for s in range(3):
        for m in core.METHODS:
            subset = res[(res.seed == s) & (res.method == m)].sort_values("budget")
            assert np.all(np.diff(subset.recall) >= -1e-12)
            five = float(subset[subset.budget == .05].recall.iloc[0])
            assert abs(by[(by.seed == s) & (by.method == m)].caught.mean() - five) < 1e-12
            row = subset[subset.budget == .05].iloc[0]
            assert abs(row.unchanged_flag_rate - row.unchanged_flags / row.unchanged_eligible) < 1e-12

def test_injections_within_period_and_parent_link():
    p = P["DEV"]; inj, lab = core.inject(p, core.DEV_TYPES, .1, seed=42)
    assert inj.date.max() <= p.date.max()
    assert set(lab.parent_invoice) <= set(p.invoice)

def test_invoice_split_disjoint():
    sets = [set(x.invoice) for x in P.values()]
    assert all(not sets[i] & sets[j] for i in range(4) for j in range(i))

if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("ok", name)
