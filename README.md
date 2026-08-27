<div align="center">
  <picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/SDCofA/border-neighbor-threat-index/main/docs/logo-dark.png"><img src="docs/logo.png" alt="Border-Neighbor Threat Index — institutional seal" width="140"></picture>

  # Border-Neighbor Threat Index
  ### A standing geopolitical assessment of Türkiye's border neighbors

  ![Assessment](https://img.shields.io/badge/Assessment-Open%20Source-0b1f3a)
  ![Classification](https://img.shields.io/badge/Classification-Unclassified-6e1f2b)
  ![Cadence](https://img.shields.io/badge/Cadence-2--hour%20refresh-b0894f)
  ![Coverage](https://img.shields.io/badge/Coverage-7%20border%20states-0b1f3a)
  ![Method](https://img.shields.io/badge/Method-Deterministic%20scoring-b0894f)
  ![License](https://img.shields.io/badge/License-MIT-6e1f2b)

  **[Live assessment](https://sdcofa.github.io/border-neighbor-threat-index/)** · **[Methodology whitepaper](methodology.pdf)** · **[Reproduction guide](DEPLOYMENT_GUIDE.md)**
</div>

> ASSESSMENT · OPEN SOURCE · UNCLASSIFIED

---

## Executive Summary

The Border-Neighbor Threat Index (BNTI) is a standing, continuously refreshed assessment of the threat environment along Türkiye's land frontiers. It converts multilingual open-source reporting from the country's seven border neighbors into a normalized, repeatable signal: a calibrated 1–10 index for each neighboring state and a single composite national figure.

The Index ingests open, lawfully accessible RSS/Atom reporting; attributes each headline to a border country and a canonical threat category by means of a large language model; and maps those categories onto fixed, published weights to produce auditable scores. The model classifies; the arithmetic is deterministic. The Company publishes the result as a public dashboard for analysts, desk officers, and decision-makers who require a defensible read on the regional picture rather than an unstructured feed of news.

---

## The Assessment

The Index measures the prevailing threat posture of seven states sharing a land border with the Republic of Türkiye, evaluated continuously against open-source reporting.

- **Subjects of assessment** — Armenia, Georgia, Greece, Iran, Iraq, Syria, and Bulgaria.
- **Instrument** — a per-country index on a calibrated 1–10 scale, together with a strategic-importance-weighted composite figure for the national picture.
- **Canonical taxonomy** — every signal is assigned to one of a fixed set of categories: military conflict, terrorism, border security, political instability, humanitarian crisis, diplomatic tensions, trade agreement, or neutral.
- **Operational tiers** — both per-country and composite figures resolve into three standing tiers for rapid interpretation.

| Tier | Range |
|---|---|
| `STABLE` | 1.0 – 4.0 |
| `ELEVATED` | 4.0 – 7.0 |
| `CRITICAL` | 7.0 – 10.0 |

The assessment is deliberately conservative in publication. A collection cycle that cannot meet minimum thresholds for signal volume, active countries, and coverage ratio is rejected outright; the prior validated snapshot remains live. The Index prefers a stale-but-trustworthy figure to a published-but-thin one.

---

## Methodology & Provenance

The Company holds to a single discipline above all others: **evidence before assertion**. No figure is published that cannot be traced to the reporting that produced it.

**Collection.** The analyzer draws headlines from a curated set of public RSS/Atom feeds spanning each neighboring state — a mixture of English-language outlets, international wire services, and native-language sources in Armenian, Georgian, Greek, Persian, Arabic, and Bulgarian. Items are time-filtered to a recent window and deduplicated by source link. Native-language material is normalized and translated for summary briefings.

**Attribution & classification.** Candidate headlines are batched and submitted to OpenRouter's `openrouter/free` route. For each item the model performs two functions: it selects the final **border-country attribution** and assigns a **canonical threat category** from the fixed taxonomy above. Primary and backup API keys provide failover so that a single credential outage does not interrupt the assessment.

**Scoring.** Each category carries a fixed, published weight — for example `military_conflict = 8.0`, `terrorism = 7.0`, `trade_agreement = -2.0`. Per-country figures are computed on the 1–10 scale by a saturating transform; the composite national index is a strategic-importance-weighted average of the per-country figures. Because classification is the sole non-deterministic step and all weights, the scale, and the thresholds are fixed and carried in the published data file, the path from source headline to final score is auditable from end to end.

**Provenance carried per signal.** Every attributed event retains its original title, translated title, **source URL**, **publication timestamp**, attributed country, and chosen threat category — so that any score resolves back to the headlines beneath it. In the language of the Company's standing conventions: each datum carries its `source`, `source_url`, `collected_at`, and `method`.

**Lawful collection only.** The Index is built exclusively on open, lawfully accessible sources. There is no scraping behind authentication and no collection of material the Company was not granted access to read.

### Early-warning precursor ensemble

BNTI also publishes a separate 0–7 day triage signal. It combines narrative precursor pressure (40%), unusual five-session moves in WTI crude, VIX, and US high-yield spreads (35%), and synchronized country-index acceleration (25%). Missing components are removed and the available weights are renormalized.

Market anomalies use a median/MAD robust z-score. WTI crude is evaluated in both directions; VIX and high-yield spread use positive anomalies. Narrative detections retain matching terms and evidence links, while cross-source confirmation requires two independent domains. Cached market data expires after 72 hours. The published `early_warning` record includes component scores, alerts, health metrics, rolling history, weights, taxonomy, and source links.

This output is not an event probability. Its confidence label measures data coverage only; the 0–7 day field is a triage horizon, not a promise that a specified event will occur.

---

## Coverage

Seven border states are under continuous assessment, each monitored against a dedicated set of national and international feeds:

| State | Native-language collection |
|---|---|
| Armenia | Armenian |
| Georgia | Georgian |
| Greece | Greek |
| Iran | Persian |
| Iraq | Arabic |
| Syria | Arabic |
| Bulgaria | Bulgarian |

The collection cycle refreshes the full intelligence picture every two hours and redeploys the public assessment without manual intervention.

---

## Data & Sources

- **Sources** — curated public news feeds for each of the seven border states, comprising native-language outlets and international wire services. Open sources only.
- **Outputs** — `bnti_data.json` and `bnti_data.js` carry the current dashboard dataset, including the methodology block, weights, scale, and thresholds; `bnti_history.csv` preserves the per-country and composite time series underpinning the trend and forecast views.
- **Auditability** — because the weighting is fixed and published within the data file itself, an external reviewer can reconstruct any score from the retained signals without privileged access.

---

## Reproduction

The standing assessment is public and requires nothing of the reader:

**Consult the live assessment** — [https://sdcofa.github.io/border-neighbor-threat-index/](https://sdcofa.github.io/border-neighbor-threat-index/)

**Run the analyzer locally:**
```bash
git clone https://github.com/SDCofA/border-neighbor-threat-index.git
cd border-neighbor-threat-index
pip install -r requirements.txt

# Provide an OpenRouter API key (a free model route is used by default)
export OPENROUTER_API_KEY="sk-or-..."
export OPENROUTER_MODEL="openrouter/free"   # optional, this is the default

python borderneighboursthreatindex.py
```
The run regenerates `bnti_data.json`, `bnti_data.js`, and `bnti_history.csv` in place. Open `index.html` to review the dashboard against the freshly generated data.

**Automated operation.** The `BNTI Intelligence Update` workflow (`.github/workflows/bnti_update.yml`) executes every two hours. It runs the analyzer with `OPENROUTER_API_KEY` and `OPENROUTER_API_KEY_BACKUP` supplied as repository secrets, commits any updated data files, and redeploys to GitHub Pages. It may also be invoked manually, including a deploy-only mode. The full zero-cost setup is documented in **[`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md)**.

### Instrument & repository

- **Intelligence engine (Python 3.11)** — `feedparser`, `pandas`, `numpy`, `python-dateutil`, `requests`, `googletrans`.
- **Classification layer** — OpenRouter (`openrouter/free`) for country re-attribution and canonical threat labeling, with primary/backup key failover.
- **Presentation** — HTML, CSS, and vanilla JavaScript (`js/core.js`, `js/map.js`, `js/stream.js`, `js/charts.js`) with Chart.js.
- **Automation** — GitHub Actions, cron-scheduled every two hours plus manual `workflow_dispatch`.
- **Hosting** — GitHub Pages (static deploy).
- **Methodology** — LaTeX source (`methodology.tex`) compiled to `methodology.pdf`.

| Path | Purpose |
|---|---|
| `borderneighboursthreatindex.py` | The analyzer — collection, attribution, scoring, gating, and data generation |
| `index.html` | Dashboard entry point |
| `js/` | Dashboard logic (core engine, map, threat stream, charts) |
| `css/` | Visual system and component styling |
| `bnti_data.json` / `bnti_data.js` | Current dataset consumed by the dashboard |
| `bnti_history.csv` | Per-country and composite score history |
| `.github/workflows/bnti_update.yml` | 2-hour update and GitHub Pages deployment |
| `methodology.tex` / `methodology.pdf` | Whitepaper — methodology and scoring design |
| `BNTIndex.pdf` | Assessment report artifact |
| `DEPLOYMENT_GUIDE.md` | Step-by-step zero-cost deployment guide |
| `requirements.txt` | Python dependencies |

---

## Standards

The Index is held to the Company's standing doctrine:

- **Evidence before assertion** — every score ships with its sources and collection timestamps; no un-provenanced figure appears on the dashboard.
- **Lawful collection only** — open, publicly accessible sources; access controls respected; official feeds preferred over circumvention.
- **Reproducibility** — the assessment can be re-run from a clean checkout, and the published data file carries the weights, scale, and thresholds required to audit any figure.
- **Conservative publication** — a cycle that fails coverage thresholds is rejected rather than shipped degraded.

### Citation
```bibtex
@software{bnti2026,
  author = {Akgul, Arda},
  title  = {Border Neighbor Threat Index: Multilingual Geopolitical Risk Assessment},
  year   = {2026},
  url    = {https://github.com/SDCofA/border-neighbor-threat-index}
}
```

Licensed under the MIT License. See [`LICENSE`](LICENSE) for details. © 2026 Monarch Castle Holdings · Ankara, Türkiye.

---

A standing index of the **Strategic Data Company of Ankara** — a constituent house of [Monarch Castle Holdings](https://github.com/MonarchCastleHoldings). Sister company: [Monarch Castle Technologies](https://github.com/monarchcastletech).

<div align="center"><sub>STRATEGIC DATA COMPANY OF ANKARA · ANKARA · TÜRKİYE · MMXXVI</sub></div>

---

<!-- repository-hygiene:start -->

![Strategic Data Company of Ankara approved lockup](docs/brand/organization-lockup.png)

BNTI — multilingual, LLM-normalized geopolitical threat index for Türkiye's seven border neighbors. Auto-refreshed every 2 hours via GitHub Actions and published to GitHub Pages.

![Lifecycle: Active](docs/lifecycle-active.svg)

## Repository status

Lifecycle: **Active**. The badge and this statement describe maintenance status, not service availability.

## Public access

[Open the published project](https://sdcofa.github.io/border-neighbor-threat-index/)

## Screenshots

![Border Neighbor Threat Index repository preview](docs/social-preview.png)

The preview is maintained as a repository asset; the live interface or generated output remains authoritative.

## Data and methodology

- [methodology.tex](methodology.tex)

These repository-specific sources define the methodology or provenance boundary. Source dates, transformation steps, and known gaps must travel with analytical outputs.

## Update frequency

The publishing workflow targets a two-hour refresh; freshness and publish gates may defer a run.

## Quick start

```shell
python -m pytest -q
```

Run only in a trusted development environment and review repository-specific prerequisites before using networked or hardware features.

## Architecture

- `borderneighboursthreatindex.py` — repository-specific implementation, data, or configuration boundary.
- `bnti_data.json` — repository-specific implementation, data, or configuration boundary.

## Tests

```shell
python -m pytest -q tests/test_repository_hygiene.py
```

## Provenance

Original software history is maintained in Git. External datasets, reports, trademarks, screenshots, and assets are not relicensed by this repository; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before reuse.

## Forecast limitations

Forecasts and model-derived scores are probabilistic, time-bound analytical outputs—not facts, guarantees, or advice. Evaluate them against their stated horizon, source timestamp, methodology, and subsequent outcomes. Missing or delayed inputs can defer publication.

## Security

Do not publish vulnerabilities in an issue. Use GitHub's private vulnerability-reporting flow when available, or follow the [organization security policy](https://github.com/SDCofA/.github/security/policy).

## License

Original repository code and documentation are available under **MIT**; see [LICENSE](LICENSE). That license does not override third-party terms documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Citation

Use the machine-readable [CITATION.cff](CITATION.cff). Cite the specific commit and, for analytical use, record the data or model snapshot date.

## Masterbrand endorsement

Border Neighbor Threat Index is published by the Strategic Data Company of Ankara, an endorsed analytical unit. **Part of Monarch Castle Technologies.**

<!-- repository-hygiene:end -->
