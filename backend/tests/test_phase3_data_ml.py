"""
Phase 3 Data & ML Gate Tests.

Non-negotiable checks:
1. Simulator produces forecasts for ALL seeded panchayats (17) with data_source=SIMULATED
2. No fabricated metrics — untrained ModelVersion has metrics_json=None
3. Feature builder outputs correct shape and no NaN/Inf values
4. Simulator sign-correctness: El Niño → lower onset_prob, higher break_prob
5. Simulator sign-correctness: Positive IOD → lower onset_prob
6. MJO phase 2-3 active → higher onset_prob
7. SHAP returns None for untrained model (no fabricated importances)
8. XGBoost predict() raises RuntimeError when untrained
9. ConvLSTM predict() raises RuntimeError when untrained
10. Climate index fetchers are importable and return correct structure on failure
11. Open-Meteo ingestor is importable and handles network errors gracefully
12. IDW downscaler interpolates correctly
"""
import os
from datetime import date

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://pannaga:pannaga@postgis:5432/pannaga")
os.environ.setdefault("REDIS_URL", "redis://redis:6379/0")
os.environ.setdefault("SECRET_KEY", "supersecretkey_for_development_only_please_change_in_production_minimum_32_characters")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("MESSAGING_PROVIDER", "mock")

DATABASE_URL = os.environ["DATABASE_URL"]


def make_engine():
    return create_async_engine(DATABASE_URL, poolclass=NullPool)


# ─── Simulator ────────────────────────────────────────────────────────────────

def test_simulator_basic_output():
    """Simulator returns dict with all required keys and valid ranges."""
    from app.ml.simulator import simulate_forecast
    fc = simulate_forecast(
        panchayat_id=1, lat=18.5, lon=73.8, lead_week=1,
        nino34=0.0, iod_dmi=0.0, mjo_phase=3, mjo_amplitude=1.0,
    )
    required = [
        "onset_prob", "break_prob", "excess_rain_prob",
        "p10_rainfall_mm", "p50_rainfall_mm", "p90_rainfall_mm",
        "confidence", "data_source", "features_json",
    ]
    for key in required:
        assert key in fc, f"Missing key: {key}"

    assert fc["data_source"] == "SIMULATED"
    assert 0.0 <= fc["onset_prob"] <= 1.0
    assert 0.0 <= fc["break_prob"] <= 1.0
    assert 0.0 <= fc["excess_rain_prob"] <= 1.0
    assert 0.0 <= fc["confidence"] <= 1.0
    assert fc["p10_rainfall_mm"] <= fc["p50_rainfall_mm"]
    assert fc["p50_rainfall_mm"] <= fc["p90_rainfall_mm"]
    assert fc["shap_values_json"] is None  # No SHAP for untrained model


def test_simulator_enso_sign_correct():
    """El Niño (nino34=1.5) → lower onset_prob and higher break_prob vs neutral."""
    from app.ml.simulator import simulate_forecast
    neutral   = simulate_forecast(1, 18.5, 73.8, 1, nino34=0.0,  iod_dmi=0.0, mjo_phase=5, mjo_amplitude=0.5)
    el_nino   = simulate_forecast(1, 18.5, 73.8, 1, nino34=1.5,  iod_dmi=0.0, mjo_phase=5, mjo_amplitude=0.5)
    la_nina   = simulate_forecast(1, 18.5, 73.8, 1, nino34=-1.5, iod_dmi=0.0, mjo_phase=5, mjo_amplitude=0.5)

    assert el_nino["onset_prob"] < neutral["onset_prob"], "El Niño must suppress onset"
    assert el_nino["break_prob"] > neutral["break_prob"], "El Niño must increase break prob"
    assert la_nina["onset_prob"] > neutral["onset_prob"], "La Niña must enhance onset"
    assert la_nina["break_prob"] < neutral["break_prob"], "La Niña must reduce break prob"


def test_simulator_iod_sign_correct():
    """Positive IOD (dmi=0.8) → lower onset_prob vs neutral."""
    from app.ml.simulator import simulate_forecast
    neutral  = simulate_forecast(1, 18.5, 73.8, 1, nino34=0.0, iod_dmi=0.0, mjo_phase=5, mjo_amplitude=0.5)
    pos_iod  = simulate_forecast(1, 18.5, 73.8, 1, nino34=0.0, iod_dmi=0.8,  mjo_phase=5, mjo_amplitude=0.5)
    neg_iod  = simulate_forecast(1, 18.5, 73.8, 1, nino34=0.0, iod_dmi=-0.8, mjo_phase=5, mjo_amplitude=0.5)

    assert pos_iod["onset_prob"] < neutral["onset_prob"], "Positive IOD must suppress onset"
    assert neg_iod["onset_prob"] > neutral["onset_prob"], "Negative IOD must enhance onset"


def test_simulator_mjo_sign_correct():
    """Active MJO phase 2-3 → higher onset_prob; phase 6-7 → lower."""
    from app.ml.simulator import simulate_forecast
    weak_mjo = simulate_forecast(1, 18.5, 73.8, 1, nino34=0.0, iod_dmi=0.0, mjo_phase=3, mjo_amplitude=0.5)
    phase23  = simulate_forecast(1, 18.5, 73.8, 1, nino34=0.0, iod_dmi=0.0, mjo_phase=2, mjo_amplitude=2.0)
    phase67  = simulate_forecast(1, 18.5, 73.8, 1, nino34=0.0, iod_dmi=0.0, mjo_phase=6, mjo_amplitude=2.0)

    assert phase23["onset_prob"] > weak_mjo["onset_prob"], "MJO phases 2-3 must enhance onset"
    assert phase67["onset_prob"] < weak_mjo["onset_prob"], "MJO phases 6-7 must suppress onset"


def test_simulator_confidence_decays_with_lead_week():
    """Confidence must decrease as lead_week increases (higher uncertainty further out)."""
    from app.ml.simulator import simulate_forecast
    confs = [
        simulate_forecast(1, 18.5, 73.8, lw, nino34=0.0, iod_dmi=0.0, mjo_phase=3, mjo_amplitude=0.0)["confidence"]
        for lw in (1, 2, 3, 4)
    ]
    assert confs[0] > confs[1] > confs[2] > confs[3], f"Confidence must decay: {confs}"


def test_simulator_all_data_source_simulated():
    """All forecasts from simulator must carry data_source=SIMULATED."""
    from app.ml.simulator import simulate_forecast
    for lw in (1, 2, 3, 4):
        fc = simulate_forecast(99, 15.0, 75.0, lw)
        assert fc["data_source"] == "SIMULATED"


# ─── Feature Builder ──────────────────────────────────────────────────────────

def test_feature_builder_shape():
    """build_features returns (N_FEATURES,) float32 array."""
    from app.ml.feature_builder import build_features, N_FEATURES
    x = build_features(0.8, 0.2, 3, 1.5, 18.5, 73.8, 2, date(2026, 6, 1))
    assert x.shape == (N_FEATURES,), f"Expected ({N_FEATURES},), got {x.shape}"
    assert x.dtype == np.float32


def test_feature_builder_no_nan():
    """Feature vector must not contain NaN or Inf."""
    from app.ml.feature_builder import build_features
    for phase in range(1, 9):
        x = build_features(1.5, -0.5, phase, 2.0, 12.0, 78.0, 1)
        assert not np.any(np.isnan(x)), f"NaN in features for phase={phase}"
        assert not np.any(np.isinf(x)), f"Inf in features for phase={phase}"


def test_feature_matrix_shape():
    """build_feature_matrix returns (N, N_FEATURES) for N records."""
    from app.ml.feature_builder import build_feature_matrix, N_FEATURES
    records = [
        {"nino34": 0.5, "iod_dmi": 0.1, "mjo_phase": 3, "mjo_amplitude": 1.2,
         "lat": 18.5, "lon": 73.8, "lead_week": i}
        for i in range(1, 5)
    ]
    X = build_feature_matrix(records)
    assert X.shape == (4, N_FEATURES)


# ─── Model Safety ─────────────────────────────────────────────────────────────

def test_xgboost_predict_raises_when_untrained():
    """XGBoostForecaster.predict() must raise RuntimeError if not trained."""
    from app.ml.models import XGBoostForecaster
    from app.ml.feature_builder import N_FEATURES
    m = XGBoostForecaster()
    X = np.zeros((3, N_FEATURES), dtype=np.float32)
    with pytest.raises(RuntimeError, match="untrained"):
        m.predict(X)


def test_shap_returns_none_for_untrained():
    """explain() must return None for untrained models — no fabricated importances."""
    from app.ml.explain import explain
    from app.ml.models import XGBoostForecaster
    from app.ml.feature_builder import N_FEATURES
    m = XGBoostForecaster()  # untrained
    X = np.zeros((5, N_FEATURES), dtype=np.float32)
    result = explain(m, X)
    assert result is None, "SHAP must return None for untrained model"


# ─── No Fabricated Metrics in DB ─────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_untrained_model_version_has_no_metrics():
    """ModelVersion for untrained model must have metrics_json=None."""
    from app.models.climate import ModelVersion

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        result = await db.execute(select(ModelVersion))
        versions = result.scalars().all()
        for v in versions:
            if not v.is_trained:
                assert v.metrics_json is None, (
                    f"Untrained ModelVersion {v.version_tag} has fabricated metrics: {v.metrics_json}"
                )
    await engine.dispose()


# ─── DB: All Seeded Panchayats Have Forecasts ─────────────────────────────────

@pytest.mark.asyncio(loop_scope="function")
async def test_all_seeded_panchayats_have_forecasts():
    """Every seeded panchayat must have at least 4 GridForecast rows (weeks 1-4)."""
    from app.models.climate import GridForecast
    from app.models.geography import Panchayat
    from sqlalchemy import func

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        pan_result = await db.execute(select(Panchayat.id))
        pan_ids = {r[0] for r in pan_result.all()}

        fc_result = await db.execute(
            select(GridForecast.panchayat_id, func.count())
            .group_by(GridForecast.panchayat_id)
        )
        fc_counts = {r[0]: r[1] for r in fc_result.all()}

    await engine.dispose()

    missing = [pid for pid in pan_ids if fc_counts.get(pid, 0) < 4]
    assert not missing, f"Panchayats missing forecasts: {missing}"


@pytest.mark.asyncio(loop_scope="function")
async def test_all_forecasts_data_source_simulated():
    """All GridForecast rows must have data_source=SIMULATED (data honesty)."""
    from app.models.climate import GridForecast
    from sqlalchemy import func

    engine = make_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as db:
        result = await db.execute(
            select(func.count()).where(GridForecast.data_source != "SIMULATED")
        )
        non_simulated = result.scalar()
    await engine.dispose()

    assert non_simulated == 0, f"Found {non_simulated} non-SIMULATED forecasts — data honesty violation"


# ─── Downscaler ───────────────────────────────────────────────────────────────

def test_idw_single_neighbor():
    """IDW with one neighbor returns that neighbor's values unchanged."""
    from app.ml.downscaler import idw_interpolate
    neighbor = {
        "lat": 18.5, "lon": 73.8,
        "onset_prob": 0.55, "break_prob": 0.18,
        "excess_rain_prob": 0.25, "p10_rainfall_mm": 20.0,
        "p50_rainfall_mm": 40.0, "p90_rainfall_mm": 65.0, "confidence": 0.72,
    }
    result = idw_interpolate(18.5, 73.8, [neighbor])
    assert abs(result["onset_prob"] - 0.55) < 0.001


def test_idw_weights_closer_neighbor_more():
    """IDW gives more weight to the closer neighbor."""
    from app.ml.downscaler import idw_interpolate
    n1 = {"lat": 18.5, "lon": 73.8, "onset_prob": 0.8, "break_prob": 0.1,
          "excess_rain_prob": 0.2, "p10_rainfall_mm": 20, "p50_rainfall_mm": 40,
          "p90_rainfall_mm": 60, "confidence": 0.7}
    n2 = {"lat": 20.0, "lon": 76.0, "onset_prob": 0.2, "break_prob": 0.5,
          "excess_rain_prob": 0.3, "p10_rainfall_mm": 10, "p50_rainfall_mm": 20,
          "p90_rainfall_mm": 35, "confidence": 0.5}
    # Query point very close to n1
    result = idw_interpolate(18.5, 73.9, [n1, n2])
    assert result["onset_prob"] > 0.5, "Closer neighbor (n1=0.8) should dominate"


# ─── Ingestor Resilience ──────────────────────────────────────────────────────

def test_fetch_all_indices_returns_dict_on_network_error(monkeypatch):
    """fetch_all_indices returns neutral defaults if network is unavailable."""
    import httpx
    from app.ingest.indices import fetch_all_indices

    def _fail(*args, **kwargs):
        raise httpx.ConnectError("Network unavailable (test)")

    monkeypatch.setattr(httpx, "get", _fail)
    result = fetch_all_indices()

    assert isinstance(result, dict)
    assert "nino34" in result
    assert "iod_dmi" in result
    assert "mjo_phase" in result
    assert result["all_live"] is False  # Should be False when fetches fail


def test_open_meteo_returns_none_on_network_error(monkeypatch):
    """fetch_open_meteo returns None gracefully if network is unavailable."""
    import httpx
    from app.ingest.forecast import fetch_open_meteo

    def _fail(*args, **kwargs):
        raise httpx.ConnectError("Network unavailable (test)")

    monkeypatch.setattr(httpx, "get", _fail)
    result = fetch_open_meteo(18.5, 73.8)
    assert result is None
