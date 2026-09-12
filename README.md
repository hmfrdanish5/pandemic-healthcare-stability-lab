# Hospital Resource Stability Lab

Interactive academic tool for **Banker's Algorithm** safety analysis and **Monte Carlo** collapse-probability estimation under pandemic-like hospital workload conditions.

## Problem Statement

During surge conditions, hospitals must allocate scarce resources (ICU beds, oxygen, ventilators, staff, blood products) across patients with varying severity. This project models each patient as a process in a multi-resource allocation system and asks:

1. Is the current allocation state **SAFE** (exists a completion ordering without deadlock)?
2. As patient load increases, what is the **estimated probability of collapse** (admission failure or unsafe state)?

## Mathematical Model

| Symbol | Meaning |
|--------|---------|
| `Allocation[i,j]` | Resource units currently held by patient *i* |
| `Max[i,j]` | Maximum units patient *i* may require |
| `Need[i,j]` | `Max[i,j] − Allocation[i,j]` |
| `Available[j]` | Free units of resource *j* |

**Invariants:** `0 ≤ Allocation ≤ Max`, `Need ≥ 0`, `Total[j] = Available[j] + Σ Allocation[i,j]`

## Banker's Algorithm

Standard safety procedure (Dijkstra, 1965): initialize `Work = Available`, find unfinished patients with `Need ≤ Work`, release their allocation into `Work`, repeat. **SAFE** if all finish; **UNSAFE** otherwise.

## Monte Carlo Methodology

For each patient count *n* = 1…*N*, run *T* independent trials:
1. Generate *n* patients with stochastic severity and demand vectors
2. Attempt sequential admission
3. Run Banker's safety check
4. Record collapse (admission failure **or** unsafe state)

Estimated: `P̂(collapse | n) = K_n / T` with **Wilson 95% score intervals** (z = 1.96). Seed policy: trial `t` at load `n` uses `Random(base_seed + n*1000 + t)`.

**n₅₀** is discrete: `n50 = min { n tested : p̂(n) ≥ 0.50 }`. No interpolation. If no tested n reaches 0.50, n₅₀ is undefined (null).

Collapse, admission failure, Banker's UNSAFE, overflow, and fatigue are **distinct** events. They are not synonyms.

## External Data

Optional Monte Carlo load scaling uses the [Our World in Data COVID-19 dataset](https://github.com/owid/covid-19-data) (CC-BY 4.0) as a **latest-available public epidemiological signal**: `f(X) = clip(X / X_ref, 0.5, 3.0)` where X is 14-day mean global smoothed new cases. `X_ref = 50_000` and clip bounds are **MODEL_ASSUMPTION** normalization choices, not hospital occupancy or capacity. This is **not** real-time facility census.

**Reproducibility policy (default offline):**
- `prefer_live=False` (default): **CACHED_EMPIRICAL** snapshot → **SYNTHETIC_FALLBACK** (labeled, multiplier 1.0)
- `prefer_live=True` or `?live=1` / `live_external: true`: **LIVE_EXTERNAL** fetch; records signal value, retrieval time, and transformation parameters. **Not reproducible from seed alone.**

Calibration provenance is labeled `REAL_OBSERVATION` / `DERIVED_PARAMETER` / `MODEL_ASSUMPTION` / `SIMULATED_VALUE`. Offline runs use a **labeled synthetic arrival fixture**, not empirical hospital data. Catalog: `pandemic_bankers/data/data_sources.json`.

## Time-dependent model (Phase 2)

Discrete-time simulation (`Δt` configurable, default 1 hour) with:

- Nurse capacity `C_nurse(t) = round(C_base × m_shift(t) × m_weekend(t))` (integer; multipliers are configurable **model assumptions**)
- If `C(t)` would fall below current allocation, lowest-priority in-care patients are overflowed **explicitly** (holdings are never silently destroyed)
- Length of stay, fatigue delay `effective_LOS = base_LOS × (1 + α)` (α configurable, not a clinical fact)
- Treatment bundles (all-or-nothing WARD/ICU)
- ED overflow and acuity degradation (overflow ≠ Banker's UNSAFE)
- Severity triage for admission order

Acuity-based preemption is **not** implemented (would make Banker's Max/Need ambiguous).

Resource units in generation are **integers**. ICU beds and ventilators are 0 or 1 per patient. Nurse/oxygen/blood units are model slots, not measured liters or FTE hours.

## Empirical calibration (Phase 3)

The project is **empirically informed**, not a fully calibrated model of a named hospital.

LOS uses **quantile-based distribution reconstruction** from Rees et al. (2020) published Q25/Q50/Q75, scored by quantile reconstruction SSE — **not** patient-level MLE and **not** a formal GOF test. For lognormal reconstruction, Q50 is matched by construction; Q25/Q75 are not guaranteed to match published quartiles unless the data are truly lognormal. Gamma predicted quantiles use Wilson–Hilferty (documented approximation). Arrival counts: Poisson vs negative binomial using mean, variance, and dispersion \(D=\mathrm{Var}/\mathrm{Mean}\) (diagnostic). Negative binomial uses NB2 / Gamma–Poisson (`size` \(\theta\): \(\mathrm{Var}=\mu+\mu^2/\theta\)). Arrival-mean interval is an **IID percentile bootstrap** (does not preserve time-series dependence; block bootstrap is not used). Copulas are **not** used: available data do not support patient-level joint dependence.

**Fallback hierarchy (never silent):** live/current source if requested and reachable → cached `REAL_OBSERVATION` (`CACHED_EMPIRICAL`) → labeled synthetic fixture (`SYNTHETIC_FALLBACK`). Live network access is not required to run the app (`prefer_live=False` on the Phase 3 dashboard route).

### Experiment families (do not collapse these)

1. **Static Banker collapse analysis** — Phase 1 n-sweep: \(\hat p_n\), Wilson CI, discrete \(n_{50}\). Isolated discrete marginal sensitivity is a separate Phase 1 experiment.
2. **Dynamic empirically informed simulation** — Phase 2 time model: overflow rate/duration, fatigue exposure, utilization. Model C uses calibrated arrival family, weekday \(\lambda(t)=\lambda_0 r_{\mathrm{dow}(t)}\), and quantile-reconstructed LOS. Hospital \(\lambda_0\) remains a **MODEL_ASSUMPTION** (`arrivals_per_step`).

### Model A / B / C (what the code actually does)

| Model | Static Banker's collapse (n-sweep) | Dynamic overflow | External data |
|-------|-------------------------------------|------------------|---------------|
| A Independent synthetic demand | Independent draws given severity | Configured arrivals; uniform LOS; bundles | None in the generators |
| B Severity-conditioned demand | Joint ICU/vent given severity | Same dynamic inputs as A | Occupancy mapping may inform p(ICU\|Severe) for **static** B and C; not complete empirical census |
| C Empirically informed dynamic | **Same demand as B** (not a separately calibrated static collapse) | Calibrated family + weekday \(\lambda(t)\) + quantile LOS | Rees LOS quantiles; arrival family/weekday from ingested series or synthetic fixture |

Calibrated arrivals and LOS **do not** change n₅₀ / P(collapse). They affect the **dynamic** overflow experiment only.

Empirical assumption sensitivity (0.9×–1.2× on \(\lambda_0\), LOS, fatigue \(\alpha\)) reports overflow metrics. It does **not** replace isolated discrete marginal sensitivity.

See `docs/MATHEMATICAL_MODEL.md` for numbered formulas.

## Sensitivity Analysis

Isolated one-resource perturbations: `ε_k = (n50(C + Δc_k e_k) − n50(C)) / Δc_k`. Display label: **Discrete Marginal Patient-Capacity Sensitivity**. This is a **local discrete finite-difference sensitivity** near the tested baseline, not standard dimensionless elasticity or an absolute bottleneck. Parameter ±5/10/20% sweeps and 0.9–1.2× empirical-assumption scales are separate experiments. Observed simulation differences are not reported as “statistically significant” unless a test is actually performed (none is).

## Installation

```bash
pip install -r requirements.txt
```

## Running Locally

**Web dashboard (development server):**
```bash
cd pandemic_dashboard
python app.py
# Open http://127.0.0.1:5000
```

Debug is **OFF** by default. For local debugging only:
```bash
set FLASK_DEBUG=1
python app.py
```

**Public / portfolio hosting:** do **not** use `python app.py` or `FLASK_DEBUG=1`. Use a WSGI server, for example:

```bash
cd pandemic_dashboard
pip install waitress
waitress-serve --listen=127.0.0.1:5000 app:app
```

On Linux you may use gunicorn instead: `gunicorn -w 1 -b 127.0.0.1:5000 app:app` (from `pandemic_dashboard/`).

**CLI analysis:**
```bash
cd pandemic_bankers
python main.py
```

**Tests:**
```bash
python tests/run_tests.py
```

**Monte Carlo experiment (dashboard):** configure patient range, trials, model A/B/C, and seed, then **Run Experiment**. Progress and Wilson intervals are streamed from Flask (SSE). Download CSV/JSON from the result card. Same seed and configuration reproduce the same `p_hat` values when using cached/offline data paths.

**Comments:** stored at runtime in `pandemic_dashboard/data/comments.db` (SQLite). A JSON backup may be written locally; **runtime comment data is not intended for version control**. No accounts — an owner token is issued at post time (kept in this browser) so you can edit or delete your own comment. Comment posting is rate-limited (8 seconds per client IP, SQLite-backed, process-shared on one host; not a distributed anti-abuse system).

**Admin comment deletion** (optional):
```bash
set ADMIN_TOKEN=your-secret-token
```
Never commit `ADMIN_TOKEN` or owner tokens. Tokens are not logged or exported.

## Project Structure

```
pandemic_bankers/
  core/bankers_engine.py       Banker's safety algorithm
  simulation/
    resource_generator.py      Patient demand vectors
    domain.py                  Hospital admission logic
    monte_carlo.py             Stochastic collapse estimation
    time_model.py              Discrete time and staffing C(t)
    treatments.py              Pathway bundles and triage ranks
    dynamic_hospital.py        Phase 2 time-stepping simulator
  data/
    data_sources.json          Provenance catalog
    literature_los.json        Published LoS summaries
    pipeline.py                Fetch / validate / cache / fallback
    calibration.py             Derived parameters, weekday λ(t), summary
    signal_transform.py        f(X)=clip(X/X_ref, f_min, f_max) MODEL_ASSUMPTION
    external_fetcher.py        Cached/live epidemiological signal
    provenance.py              Observation vs assumption labels
  analytics/
    phase3_experiment.py       Model A/B/C + empirical-assumption sensitivity
    sensitivity.py             Discrete marginal capacity sensitivity
    stability_analyzer.py      CLI plotting
  utils/config_loader.py       JSON validation
  hospital_config.json         Model parameters

pandemic_dashboard/
  app.py                       Flask API
  comments_store.py            SQLite comments + feedback
  rate_limit_store.py          SQLite comment rate limits
  templates/                   HTML pages
  static/                      CSS + JS

tests/                         Mathematical core tests
```

## Limitations

- Banker's Algorithm assumes maximum demands are known in advance
- Five abstract resource types; ICU/ventilator are binary per patient; other units are integer model slots
- Phase 2 staffing, LOS, fatigue, and degradation parameters are model assumptions, not empirical clinical facts
- Acuity-based preemption is deferred
- National/epidemiological series are not this hospital's census; offline calibration uses a synthetic fixture when needed (labeled `SYNTHETIC_FALLBACK` / `SIMULATED_VALUE`)
- LOS calibration matches three published quantiles via quantile reconstruction (not MLE); Q25/Q75 are not guaranteed exact fits
- IID bootstrap of daily counts ignores serial correlation
- Staffing, nurse FTE, per-patient oxygen liters, and named-hospital ICU census are **MODEL_ASSUMPTION** or unused; they are not fake-calibrated
- n50 and discrete marginal sensitivity inherit Monte Carlo sampling error
- Stochastic results depend on sample size and configured demand profiles
- Simulation outputs are illustrative, not clinical predictions
- In-memory/SQLite rate limiting is suitable for low-traffic demo hosting only; multi-worker deployments across hosts may need centralized rate limiting

## License

Educational / research use. External data subject to [OWID license terms](https://github.com/owid/covid-19-data).
