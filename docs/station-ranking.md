# Station ranking

The ranked rate is minutes of delay per logged incident at a station, i.e. how much a typical incident there costs. Each station's average is shrunk toward its own line's average with a normal-normal empirical-Bayes model, using method-of-moments estimates (`sql/ranking.sql`, `ttc_delay/ranking.py`):

```
x_i      station mean minutes per incident (n_i incidents)
mu_L     line mean = line minutes / line incidents
sigma2_L pooled within-station variance on line L
v_i      = sigma2_L / n_i                                  sampling noise of x_i
tau2     = max(0, mean_i[(x_i - mu_L)^2 - v_i])            true spread between stations
B_i      = v_i / (v_i + tau2)                              shrinkage weight (1 if tau2 = 0)
shrunk_i = (1 - B_i) * x_i + B_i * mu_L
```

- The ranking is materialised for three periods: all years, the last 36 months and the last 12 months.
- Each row has the naive rank, the shrunk rank, the count rank, the rank change and a plain-language explanation.
- Only real stations are ranked. A station closed before a period starts (Line 3) is left out of that period.
- `station_ranking_for(from, to)` is a DuckDB table macro, so any other window can be ranked.

The normal approximation is rough for data this skewed. Shrinkage handles stations with few incidents, not single extreme incidents.
