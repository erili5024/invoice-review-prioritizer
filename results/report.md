## DEV period (20 random plantings; mean over seeds)
Planted errors per run: 235. Synthetic stress test, not fraud-prevention performance.

### Recall by review budget (share of planted errors in the top k invoices; oracle = best possible)
| method | 1% budget | 2% budget | 5% budget | 10% budget |
|---|---|---|---|---|
| random | 0.014 | 0.023 | 0.053 | 0.101 |
| largest | 0.010 | 0.022 | 0.059 | 0.115 |
| hist_z | 0.007 | 0.018 | 0.044 | 0.092 |
| rules | 0.219 | 0.260 | 0.291 | 0.334 |
| iforest | 0.074 | 0.144 | 0.317 | 0.376 |
| oracle | 0.339 | 0.679 | 1.000 | 1.000 |

### At a 5% budget
unchanged_flags = reviewed invoices without a planted error, NOT confirmed clean or wasted attention. unchanged_flag_rate divides by all unchanged eligible invoices. value_recall = share of planted invoices' recorded invoice value caught (GBP, not loss or savings).
| method | recall | sd | unchanged_flags | unchanged_flag_rate | unchanged_eligible | value_recall | oracle |
|---|---|---|---|---|---|---|---|
| random | 0.053 | 0.013 | 386.600 | 0.050 | 7729.000 | 0.051 | 1.000 |
| largest | 0.059 | 0.014 | 385.150 | 0.050 | 7729.000 | 0.366 | 1.000 |
| hist_z | 0.044 | 0.014 | 388.700 | 0.050 | 7729.000 | 0.118 | 1.000 |
| rules | 0.291 | 0.017 | 330.450 | 0.043 | 7729.000 | 0.324 | 1.000 |
| iforest | 0.317 | 0.017 | 324.300 | 0.042 | 7729.000 | 0.390 | 1.000 |

### Recall at 5% by error type and severity (what gets missed)
| type | severity | random | largest | hist_z | rules | iforest |
|---|---|---|---|---|---|---|
| dup_invoice | exact | 0.059 | 0.052 | 0.051 | 0.894 | 1.000 |
| dup_invoice | near | 0.037 | 0.037 | 0.059 | 0.602 | 0.754 |
| price_x | 1.15 | 0.041 | 0.061 | 0.046 | 0.039 | 0.039 |
| price_x | 1.5 | 0.063 | 0.038 | 0.042 | 0.031 | 0.048 |
| price_x | 2.0 | 0.052 | 0.069 | 0.033 | 0.177 | 0.027 |
| qty_x | 10 | 0.062 | 0.102 | 0.050 | 0.052 | 0.071 |
| qty_x | 2 | 0.069 | 0.063 | 0.037 | 0.043 | 0.028 |
| qty_x | 5 | 0.042 | 0.062 | 0.021 | 0.050 | 0.031 |

### Planted errors on invoices with no price history for any line
| type | share_with_no_price_history |
|---|---|
| dup_invoice | 0.021 |
| price_x | 0.024 |
| qty_x | 0.025 |

