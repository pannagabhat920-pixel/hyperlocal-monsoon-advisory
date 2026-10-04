# Pannaga: Scientific Methodology & Agronomic Decision Framework

## 1. Meteorological Indicator Definitions

Pannaga operationalizes sub-seasonal monsoon forecasts across Indian Gram Panchayats using formal meteorological criteria aligned with the India Meteorological Department (IMD) standards:

### 1.1 Monsoon Onset
- **Physical Definition:** The sustained arrival of the southwest monsoon over a Gram Panchayat centroid.
- **Quantitative Criterion:** First occurrence after May 1st where precipitation $\ge 2.5\text{ mm/day}$ occurs on $\ge 3$ consecutive days within a 7-day rolling window, accompanied by synoptic-scale wind transition (850 hPa westerly wind anomaly).
- **Probabilistic Metric:** `onset_prob` $\in [0.0, 1.0]$, representing the proportion of ensemble members predicting onset in the target week.

### 1.2 Monsoon Break (Dry Spell)
- **Physical Definition:** Significant cessation of rainfall during the core southwest monsoon season (June–September) resulting in moisture stress for rainfed crops.
- **Quantitative Criterion:** $\ge 5$ consecutive days with rainfall $< 2.5\text{ mm/day}$ over the Gram Panchayat centroid, coinciding with northward migration of the monsoon trough towards the Himalayan foothills.
- **Duration Quantile:** $\text{break\_duration\_days\_p50}$, representing the median anticipated length of the dry spell.
- **Probabilistic Metric:** `break_prob` $\in [0.0, 1.0]$.

### 1.3 False Onset (Premature Sowing Hazard)
- **Physical Definition:** Transient pre-monsoon convective showers that induce early germination followed immediately by a prolonged dry spell ($\ge 10$ days), leading to seed desiccation and crop failure.
- **Quantitative Criterion:** `onset_prob` $\ge 0.60$ immediately followed by a dry spell $\ge 10$ days within the subsequent 14 days.
- **Probabilistic Metric:** `false_onset_prob` $\in [0.0, 1.0]$.

### 1.4 Heavy Downpour / Excess Rainfall
- **Physical Definition:** High-intensity episodic downpour posing severe waterlogging, soil erosion, and crop lodging hazards.
- **Quantitative Criterion:** 7-day accumulated precipitation exceeding the 80th climatological percentile ($P_{80}$) for that calendar week and agro-climatic zone.
- **Probabilistic Metric:** `excess_rain_prob` $\in [0.0, 1.0]$.

---

## 2. Temporal Forecast Windows (1–4 Weeks)

Forecasts are generated and partitioned into 4 distinct lead-time pentad/weekly buckets:

| Lead Horizon | Target Window | Meteorological Skill Expectation | Agronomic Decision Scope |
|---|---|---|---|
| **Week 1** | Days 1–7 | High synoptic NWP skill | Field operations: spraying, fertilizing, harvesting, drainage prep |
| **Week 2** | Days 8–14 | Moderate sub-seasonal skill | Sowing scheduling, protective irrigation planning |
| **Week 3** | Days 15–21 | Sub-seasonal teleconnection signal | Crop variety selection, contingency seed arrangement |
| **Week 4** | Days 22–28 | Near-climatological prior | Broad seasonal planning and water budgeting |

---

## 3. Agronomic Decision Logic & Rules Engine

Agronomic advisories are produced deterministically by evaluating peer-reviewed rules against panchayat forecasts, crop stage, and farmer profile attributes.

### 3.1 Non-Negotiable Rule 0: Harvested & Finished Crops
Any crop record identified as `HARVESTED`, `FINISHED`, or `COMPLETED` is strictly suppressed from receiving sowing, irrigation, or fertilizer advisories. Only post-harvest storage or land-preparation guidance may be issued.

### 3.2 Canonical Crop Stages
To guarantee schema integrity, all incoming farmer statuses are normalized to 5 canonical stages:
1. `NOT_STARTED`: Pre-sowing, land preparation, seed procurement.
2. `SOWN`: Seed sown, germination, seedling emergence.
3. `VEGETATIVE`: Active leaf, stem, and root development.
4. `FLOWERING_PODDING`: Flowering, pollination, grain/pod filling (moisture critical).
5. `HARVEST_READY`: Physiological maturity, ripening, pre-harvest.

### 3.3 Rule Decision Matrix

| Rule ID | Trigger Conditions | Applicable Crop Stage | Severity | Advisory Output |
|---|---|---|---|---|
| `SAFE_TO_SOW` | `onset_prob` $\ge 0.65$ AND `false_onset_prob` $< 0.30$ | `NOT_STARTED` | `ADVISORY` | Favorable soil moisture conditions anticipated. Recommended to proceed with primary sowing. |
| `DELAY_SOWING` | `false_onset_prob` $\ge 0.60$ | `NOT_STARTED` | `HIGH` | High risk of transient false onset. Hold sowing until sustained monsoon pulse is established. |
| `ALTER_CROP` | `false_onset_prob` $\ge 0.60$ AND `is_past_sowing_window` = True | `NOT_STARTED` | `CRITICAL` | Sowing window expired. Switch immediately to short-duration or drought-hardy contingency crops (e.g. pulses, millets). |
| `BREAK_PROTECTIVE` | `break_prob` $\ge 0.70$ AND duration $\ge 10\text{d}$ AND irrigated source | `SOWN`, `VEGETATIVE`, `FLOWERING_PODDING` | `HIGH` | Extended break forecasted. Schedule protective canal/borewell irrigation during flowering/podding. |
| `BREAK_MOISTURE` | `break_prob` $\ge 0.70$ AND duration $\ge 10\text{d}$ AND rainfed/drip/sprinkler | `SOWN`, `VEGETATIVE`, `FLOWERING_PODDING` | `HIGH` | Extended break forecasted. Apply organic mulch, shallow intercultural hoeing, or anti-transpirants to conserve soil moisture. |
| `DRAINAGE_PREP` | `excess_rain_prob` $\ge 0.75$ | `SOWN`, `VEGETATIVE`, `FLOWERING_PODDING` | `HIGH` | Heavy downpour expected. Clear drainage channels, open field bund trenches to prevent water stagnation. |
| `EARLY_HARVEST` | `excess_rain_prob` $\ge 0.75$ | `HARVEST_READY` | `CRITICAL` | Imminent extreme downpour. Harvest standing mature crops immediately and store in elevated, dry facilities. |

### 3.4 Exhaustive Irrigation Branching
Every valid `IrrigationSource` enum maps to exactly one branch:
- **Irrigated Branch (`PROTECTIVE_IRRIGATION`):** `CANAL`, `BOREWELL`, `TANK`.
- **Conservation Branch (`MOISTURE_CONSERVATION`):** `RAINFED`, `DRIP_SPRINKLER`, `OTHER`.

---

## 4. Farmer Cooldown & Escalation Safety Rules

To protect farmers from information fatigue and alarm fatigue:
1. **72-Hour Farmer Cooldown:** A farmer may receive at most one routine notification per 72 hours.
2. **Escalation Exception:** The 72-hour cooldown is bypassed **only** if an incoming advisory represents an escalation in risk severity (`CRITICAL > HIGH > ADVISORY > INFO`) or changes the physical hazard event.
3. **Cycle Quota:** At most 1 primary advisory + 1 secondary advisory may be delivered to a single farmer within a forecast issuance cycle.
4. **Channel Consent:** Independent consent is maintained and validated for `WHATSAPP` and `SMS`. Any explicit `STOP` request sets `opted_out_at` and blocks future outbound notifications immediately.

---

## 5. Regional Language Translation & Audio Synthesis

Advisories are generated in English and localized into 6 regional languages:
- **Languages:** Hindi (`hi`), Marathi (`mr`), Telugu (`te`), Kannada (`kn`), Punjabi (`pa`), and English (`en`).
- **Data Integrity Preservation:** Machine translation algorithms are validated against regex checks to ensure numbers, units (e.g. `mm`, `days`, `acres`), and calendar dates remain identical to the approved source.
- **Extension Officer Review:** Unvetted machine translations are flagged in the Extension Officer UI (`flagged_for_review = True`).
- **Persistent Bhashini TTS Caching:** Text-to-speech audio is pre-rendered upon officer approval, keyed by unguessable HMAC-SHA256 tokens derived from `SECRET_KEY`, written to persistent storage (`/app/media/audio`), and served as static WAV files. In mock/demo mode (prior to live Bhashini API key wiring), a valid 440 Hz synthetic PCM sine wave is generated as an operational audio placeholder.

---

## 6. Data Honesty Tiers

Every prediction, advisory, and notification is immutably tagged:

- `LIVE`: Generated from real-time global index feeds and Open-Meteo operational ensembles. Dispatched to messaging channels when approved.
- `HINDCAST`: Derived from historical reanalysis for model scoring and evaluation. Blocked from live broadcast.
- `SIMULATED`: Derived from the deterministic prior simulator (untrained pipeline). **Strictly forbidden from reaching real telecom/messaging networks** (`BLOCKED_SIMULATED`). Rendered with a persistent amber data honesty banner in all user interfaces.
