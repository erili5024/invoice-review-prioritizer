"""Measure real DEV baseline scores and planted-error ranking behavior."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import core


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared", default="data/prepared.pkl")
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--rate", type=float, default=.03)
    args = parser.parse_args()
    if not 1 <= args.seeds <= 100:
        raise ValueError("Use 1-100 predeclared seeds")
    source = Path(args.prepared)
    if not source.is_file():
        raise FileNotFoundError(f"Prepared data not found: {source}")

    lines = pd.read_pickle(source)
    periods = core.split_periods(lines)
    dev = periods["DEV"]
    history = core.History(pd.concat([periods["H"], periods["F"]]))
    baseline, _ = core.build_features(dev, history)
    baseline_z = np.maximum(baseline.price_z, baseline.qty_z)
    baseline_rules = core.rules_score(baseline)
    model = core.fit_iforest(
        core.build_features(periods["F"], core.History(periods["H"]))[0]
    )
    baseline_summary = {
        "invoices": len(baseline),
        "not_planted_is_not_verified_clean": True,
        "max_line_z_quantiles": {
            str(q): float(baseline_z.quantile(q)) for q in (.5, .9, .95, .99, 1.0)
        },
        "share_max_line_z_at_least_4": float((baseline_z >= 4).mean()),
        "share_max_line_z_at_least_10": float((baseline_z >= 10).mean()),
        "share_rules_score_at_least_10": float((baseline_rules >= 10).mean()),
        "share_multiline_rules_score_at_least_10": float(
            (baseline_rules[baseline.n_lines >= 2] >= 10).mean()
        ) if (baseline.n_lines >= 2).any() else 0.0,
    }

    observations = []
    for seed in range(args.seeds):
        injected, labels = core.inject(
            dev, core.DEV_TYPES, args.rate, seed=seed, history=history
        )
        scored, _ = core.build_features(injected, history)
        scores = {
            "rules": core.rules_score(scored).to_numpy(),
            "iforest": core.iforest_score(model, scored),
        }
        labels = labels[labels.invoice.isin(scored.index)].copy()
        labels["n_lines"] = scored.loc[labels.invoice, "n_lines"].to_numpy()
        labels["price_z"] = scored.loc[labels.invoice, "price_z"].to_numpy()
        labels["qty_z"] = scored.loc[labels.invoice, "qty_z"].to_numpy()
        parent_ids = labels.parent_invoice.to_numpy()
        labels["baseline_price_z"] = baseline.loc[parent_ids, "price_z"].to_numpy()
        labels["baseline_qty_z"] = baseline.loc[parent_ids, "qty_z"].to_numpy()
        labels["price_z_change"] = labels.price_z - labels.baseline_price_z
        labels["qty_z_change"] = labels.qty_z - labels.baseline_qty_z
        labels["max_line_z"] = np.maximum(
            labels.price_z,
            labels.qty_z,
        )
        labels["rules_score"] = core.rules_score(scored.loc[labels.invoice]).to_numpy()
        labels["rules_z_component"] = np.minimum(labels.max_line_z, 10)
        labels["line_group"] = np.select(
            [labels.n_lines == 1, labels.n_lines == 2],
            ["1 line", "2 lines"],
            default="3+ lines",
        )
        for method, values in scores.items():
            ordering = core.ranking(values, scored.index)
            rank = np.empty(len(ordering), dtype=int)
            rank[ordering] = np.arange(1, len(ordering) + 1)
            for budget in (.01, .02, .05):
                cutoff = int(np.ceil(budget * len(scored)))
                labels[f"{method}_rank"] = rank[
                    scored.index.get_indexer(labels.invoice)
                ]
                labels[f"{method}_caught_{budget}"] = (
                    labels[f"{method}_rank"] <= cutoff
                )
        observations.append(labels)

    planted = pd.concat(observations, ignore_index=True)
    recall_rows = []
    for (method, budget, error_type, severity), group in (
        planted.melt(
            id_vars=["type", "severity"],
            value_vars=[
                f"{m}_caught_{b}" for m in ("rules", "iforest")
                for b in (.01, .02, .05)
            ],
            var_name="metric",
            value_name="caught",
        )
        .assign(
            method=lambda d: d.metric.str.extract(r"^(rules|iforest)")[0],
            budget=lambda d: d.metric.str.extract(r"caught_(0\.\d+)")[0].astype(float),
        )
        .groupby(["method", "budget", "type", "severity"], observed=True)
    ):
        recall_rows.append({
            "method": method,
            "budget": budget,
            "type": error_type,
            "severity": severity,
            "recall": float(group.caught.mean()),
            "n_plantings": int(len(group)),
        })

    duplicate_rows = []
    duplicates = planted[planted.type == "dup_invoice"]
    for (method, budget, line_group), group in (
        duplicates.melt(
            id_vars=["line_group"],
            value_vars=[
                f"{m}_caught_{b}" for m in ("rules", "iforest")
                for b in (.01, .02, .05)
            ],
            var_name="metric",
            value_name="caught",
        )
        .assign(
            method=lambda d: d.metric.str.extract(r"^(rules|iforest)")[0],
            budget=lambda d: d.metric.str.extract(r"caught_(0\.\d+)")[0].astype(float),
        )
        .groupby(["method", "budget", "line_group"], observed=True)
    ):
        duplicate_rows.append({
            "method": method,
            "budget": budget,
            "line_group": line_group,
            "recall": float(group.caught.mean()),
            "n_plantings": int(len(group)),
        })

    injection_summary = {}
    for error_type, group in planted.groupby("type", observed=True):
        target_z = group.price_z if error_type == "price_x" else group.qty_z
        baseline_target_z = (
            group.baseline_price_z if error_type == "price_x"
            else group.baseline_qty_z
        )
        target_z_change = (
            group.price_z_change if error_type == "price_x"
            else group.qty_z_change
        )
        injection_summary[error_type] = {
            "n_plantings": int(len(group)),
            "median_target_feature_z": float(target_z.median()),
            "share_target_feature_z_at_least_4": float((target_z >= 4).mean()),
            "median_baseline_target_feature_z": float(baseline_target_z.median()),
            "median_target_feature_z_change": float(target_z_change.median()),
            "share_max_line_z_at_least_4": float((group.max_line_z >= 4).mean()),
            "share_max_line_z_at_least_10": float((group.max_line_z >= 10).mean()),
            "median_max_line_z": float(group.max_line_z.median()),
            "median_rules_score": float(group.rules_score.median()),
        }

    result = {
        "source": str(source),
        "dev_invoices": len(dev.invoice.unique()),
        "seeds": args.seeds,
        "injection_rate": args.rate,
        "baseline_ordinary_invoice_scores": baseline_summary,
        "planted_error_score_summary": injection_summary,
        "recall_by_error_and_budget": recall_rows,
        "duplicate_recall_by_invoice_size_and_budget": duplicate_rows,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
