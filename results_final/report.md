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

## TEST period (20 random plantings; mean over seeds)
Planted errors per run: 352. Synthetic stress test, not fraud-prevention performance.

### Recall by review budget (share of planted errors in the top k invoices; oracle = best possible)
| method | 1% budget | 2% budget | 5% budget | 10% budget |
|---|---|---|---|---|
| random | 0.009 | 0.021 | 0.052 | 0.108 |
| largest | 0.011 | 0.023 | 0.059 | 0.118 |
| hist_z | 0.009 | 0.016 | 0.045 | 0.097 |
| rules | 0.191 | 0.201 | 0.233 | 0.287 |
| iforest | 0.116 | 0.170 | 0.253 | 0.322 |
| oracle | 0.340 | 0.677 | 1.000 | 1.000 |

### At a 5% budget
unchanged_flags = reviewed invoices without a planted error, NOT confirmed clean or wasted attention. unchanged_flag_rate divides by all unchanged eligible invoices. value_recall = share of planted invoices' recorded invoice value caught (GBP, not loss or savings).
| method | recall | sd | unchanged_flags | unchanged_flag_rate | unchanged_eligible | value_recall | oracle |
|---|---|---|---|---|---|---|---|
| random | 0.052 | 0.012 | 577.600 | 0.050 | 11564.050 | 0.047 | 1.000 |
| largest | 0.059 | 0.012 | 575.050 | 0.050 | 11564.050 | 0.406 | 1.000 |
| hist_z | 0.045 | 0.008 | 580.200 | 0.050 | 11564.050 | 0.099 | 1.000 |
| rules | 0.233 | 0.013 | 513.750 | 0.044 | 11564.050 | 0.219 | 1.000 |
| iforest | 0.253 | 0.015 | 506.600 | 0.044 | 11564.050 | 0.366 | 1.000 |

### Recall at 5% by error type and severity (what gets missed)
| type | severity | random | largest | hist_z | rules | iforest |
|---|---|---|---|---|---|---|
| dup_invoice | exact | 0.064 | 0.043 | 0.053 | 0.905 | 1.000 |
| dup_invoice | near | 0.052 | 0.045 | 0.051 | 0.603 | 0.727 |
| price_x | 1.15 | 0.048 | 0.048 | 0.047 | 0.047 | 0.035 |
| price_x | 1.5 | 0.050 | 0.060 | 0.025 | 0.045 | 0.038 |
| price_x | 2.0 | 0.038 | 0.060 | 0.031 | 0.098 | 0.043 |
| qty_x | 10 | 0.066 | 0.116 | 0.052 | 0.034 | 0.064 |
| qty_x | 2 | 0.053 | 0.058 | 0.032 | 0.035 | 0.038 |
| qty_x | 5 | 0.053 | 0.072 | 0.028 | 0.052 | 0.032 |
| wrong_product | far | 0.055 | 0.050 | 0.060 | 0.128 | 0.166 |
| wrong_product | mid | 0.038 | 0.064 | 0.053 | 0.084 | 0.038 |
| wrong_product | near | 0.050 | 0.052 | 0.053 | 0.042 | 0.030 |

### Planted errors on invoices with no price history for any line
| type | share_with_no_price_history |
|---|---|
| dup_invoice | 0.024 |
| price_x | 0.027 |
| qty_x | 0.017 |
| wrong_product | 0.006 |

