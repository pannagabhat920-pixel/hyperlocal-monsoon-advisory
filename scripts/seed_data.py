import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Ensure backend app is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.core.config import settings
from app.models.enums import (
    UserRole,
    IrrigationSource,
    DataSource,
    AdvisorySeverity,
    AdvisoryApprovalStatus,
    NotificationChannel,
    NotificationStatus,
)
from app.models.geography import State, District, Block, Panchayat
from app.models.users import User, FarmerProfile, OfficerJurisdiction
from app.models.climate import GlobalIndices, ModelVersion, GridForecast
from app.models.agronomy import AgronomicRule, GeneratedAdvisory, NotificationLog

def make_box_multipolygon(lon: float, lat: float, delta: float = 0.04) -> str:
    """Creates a valid WKT MultiPolygon centered around lon, lat."""
    min_x, max_x = round(lon - delta, 6), round(lon + delta, 6)
    min_y, max_y = round(lat - delta, 6), round(lat + delta, 6)
    return f"SRID=4326;MULTIPOLYGON((({min_x} {min_y}, {max_x} {min_y}, {max_x} {max_y}, {min_x} {max_y}, {min_x} {min_y})))"

def make_point(lon: float, lat: float) -> str:
    """Creates a valid WKT Point."""
    return f"SRID=4326;POINT({round(lon, 6)} {round(lat, 6)})"

async def seed_geography(session: AsyncSession):
    print("-> Seeding Geography across MH, KA, TS, MP, and PB (15+ Panchayats)...")
    
    # 5 States
    states_data = [
        {"name": "Maharashtra", "lgd_code": 27, "lon": 75.7, "lat": 19.7},
        {"name": "Karnataka", "lgd_code": 29, "lon": 75.8, "lat": 15.3},
        {"name": "Telangana", "lgd_code": 36, "lon": 79.0, "lat": 18.1},
        {"name": "Madhya Pradesh", "lgd_code": 23, "lon": 77.4, "lat": 23.2},
        {"name": "Punjab", "lgd_code": 3, "lon": 75.3, "lat": 31.1},
    ]
    
    state_objs = {}
    for s in states_data:
        state = State(
            name=s["name"],
            lgd_code=s["lgd_code"],
            geom=make_box_multipolygon(s["lon"], s["lat"], delta=0.5),
            is_synthetic_boundary=True
        )
        session.add(state)
        state_objs[s["name"]] = state
    await session.flush()

    # Districts
    districts_data = [
        {"name": "Pune", "state": "Maharashtra", "lgd": 490, "lon": 73.85, "lat": 18.52},
        {"name": "Nashik", "state": "Maharashtra", "lgd": 487, "lon": 73.78, "lat": 19.99},
        {"name": "Dharwad", "state": "Karnataka", "lgd": 526, "lon": 75.01, "lat": 15.45},
        {"name": "Mandya", "state": "Karnataka", "lgd": 537, "lon": 76.89, "lat": 12.52},
        {"name": "Warangal", "state": "Telangana", "lgd": 668, "lon": 79.59, "lat": 17.97},
        {"name": "Indore", "state": "Madhya Pradesh", "lgd": 403, "lon": 75.85, "lat": 22.71},
        {"name": "Ludhiana", "state": "Punjab", "lgd": 33, "lon": 75.85, "lat": 30.90},
    ]

    district_objs = {}
    for d in districts_data:
        dist = District(
            name=d["name"],
            state_id=state_objs[d["state"]].id,
            lgd_code=d["lgd"],
            geom=make_box_multipolygon(d["lon"], d["lat"], delta=0.2),
            is_synthetic_boundary=True
        )
        session.add(dist)
        district_objs[d["name"]] = dist
    await session.flush()

    # Blocks
    blocks_data = [
        {"name": "Haveli", "district": "Pune", "lgd": 4501, "lon": 73.86, "lat": 18.50},
        {"name": "Dindori", "district": "Nashik", "lgd": 4502, "lon": 73.83, "lat": 20.20},
        {"name": "Hubballi", "district": "Dharwad", "lgd": 4503, "lon": 75.12, "lat": 15.36},
        {"name": "Pandavapura", "district": "Mandya", "lgd": 4504, "lon": 76.66, "lat": 12.49},
        {"name": "Hanamkonda", "district": "Warangal", "lgd": 4505, "lon": 79.54, "lat": 18.01},
        {"name": "Sanwer", "district": "Indore", "lgd": 4506, "lon": 75.82, "lat": 22.97},
        {"name": "Jagraon", "district": "Ludhiana", "lgd": 4507, "lon": 75.47, "lat": 30.78},
    ]

    block_objs = {}
    for b in blocks_data:
        blk = Block(
            name=b["name"],
            district_id=district_objs[b["district"]].id,
            lgd_code=b["lgd"],
            geom=make_box_multipolygon(b["lon"], b["lat"], delta=0.1),
            is_synthetic_boundary=True
        )
        session.add(blk)
        block_objs[b["name"]] = blk
    await session.flush()

    # 17 Gram Panchayats
    panchayats_data = [
        # Maharashtra - Haveli
        {"name": "Wagholi", "block": "Haveli", "lgd": 190001, "lon": 73.98, "lat": 18.57},
        {"name": "Manjari", "block": "Haveli", "lgd": 190002, "lon": 73.97, "lat": 18.51},
        {"name": "Uruli Kanchan", "block": "Haveli", "lgd": 190003, "lon": 74.13, "lat": 18.48},
        # Maharashtra - Dindori
        {"name": "Khadak Sukene", "block": "Dindori", "lgd": 190004, "lon": 73.88, "lat": 20.15},
        {"name": "Nanashi", "block": "Dindori", "lgd": 190005, "lon": 73.74, "lat": 20.28},
        # Karnataka - Hubballi
        {"name": "Unkal", "block": "Hubballi", "lgd": 190006, "lon": 75.11, "lat": 15.38},
        {"name": "Gokul", "block": "Hubballi", "lgd": 190007, "lon": 75.08, "lat": 15.35},
        {"name": "Amargol", "block": "Hubballi", "lgd": 190008, "lon": 75.10, "lat": 15.41},
        # Karnataka - Pandavapura
        {"name": "Chikka Byadarahalli", "block": "Pandavapura", "lgd": 190009, "lon": 76.68, "lat": 12.51},
        {"name": "Halebeedu", "block": "Pandavapura", "lgd": 190010, "lon": 76.62, "lat": 12.48},
        # Telangana - Hanamkonda
        {"name": "Kazipet Rural", "block": "Hanamkonda", "lgd": 190011, "lon": 79.51, "lat": 17.98},
        {"name": "Gopalpuram", "block": "Hanamkonda", "lgd": 190012, "lon": 79.56, "lat": 18.04},
        {"name": "Madikonda", "block": "Hanamkonda", "lgd": 190013, "lon": 79.48, "lat": 17.93},
        # Madhya Pradesh - Sanwer
        {"name": "Ajnod", "block": "Sanwer", "lgd": 190014, "lon": 75.80, "lat": 22.95},
        {"name": "Kshipra", "block": "Sanwer", "lgd": 190015, "lon": 75.87, "lat": 23.01},
        # Punjab - Jagraon
        {"name": "Sidhwan Bet", "block": "Jagraon", "lgd": 190016, "lon": 75.45, "lat": 30.88},
        {"name": "Swaddi Khas", "block": "Jagraon", "lgd": 190017, "lon": 75.52, "lat": 30.74},
    ]

    panchayat_objs = []
    for p in panchayats_data:
        panch = Panchayat(
            name=p["name"],
            block_id=block_objs[p["block"]].id,
            lgd_code=p["lgd"],
            geom=make_box_multipolygon(p["lon"], p["lat"], delta=0.03),
            centroid=make_point(p["lon"], p["lat"]),
            is_synthetic_boundary=True
        )
        session.add(panch)
        panchayat_objs.append(panch)
    await session.flush()
    print(f"-> Seeded {len(panchayat_objs)} Panchayats across 7 Blocks and 5 States.")
    return block_objs, panchayat_objs

async def seed_users(session: AsyncSession, block_objs, panchayat_objs):
    print("-> Seeding Users (1 Admin, 2 Extension Officers, 6 Farmers)...")
    now = datetime.now(timezone.utc)
    
    # 1 Admin (clearly fictitious non-routable number)
    admin = User(
        phone_number="+910000000001",
        role=UserRole.ADMIN,
        preferred_language="en",
        consent_given_at=now,
        is_active=True
    )
    session.add(admin)

    # 2 Extension Officers (fictitious)
    officer_mh = User(
        phone_number="+910000000002",
        role=UserRole.EXTENSION_OFFICER,
        preferred_language="mr",
        consent_given_at=now,
        is_active=True
    )
    officer_ka = User(
        phone_number="+910000000003",
        role=UserRole.EXTENSION_OFFICER,
        preferred_language="kn",
        consent_given_at=now,
        is_active=True
    )
    session.add_all([officer_mh, officer_ka])
    await session.flush()

    # Officer Jurisdictions
    session.add(OfficerJurisdiction(user_id=officer_mh.id, block_id=block_objs["Haveli"].id))
    session.add(OfficerJurisdiction(user_id=officer_mh.id, block_id=block_objs["Dindori"].id))
    session.add(OfficerJurisdiction(user_id=officer_ka.id, block_id=block_objs["Hubballi"].id))
    session.add(OfficerJurisdiction(user_id=officer_ka.id, block_id=block_objs["Pandavapura"].id))

    # 6 Farmers (fictitious)
    farmers_spec = [
        {"phone": "+910000000011", "panchayat_idx": 0, "crop": "cotton", "soil": "black_cotton", "irr": IrrigationSource.RAINFED, "size": 3.5, "status": "VEGETATIVE", "lang": "mr"},
        {"phone": "+910000000012", "panchayat_idx": 1, "crop": "soybean", "soil": "black_cotton", "irr": IrrigationSource.RAINFED, "size": 5.0, "status": "PLANNED", "lang": "mr"},
        {"phone": "+910000000013", "panchayat_idx": 5, "crop": "groundnut", "soil": "red_sandy", "irr": IrrigationSource.BOREWELL, "size": 2.0, "status": "FLOWERING", "lang": "kn"},
        {"phone": "+910000000014", "panchayat_idx": 8, "crop": "rice", "soil": "alluvial", "irr": IrrigationSource.CANAL, "size": 4.2, "status": "TRANSPLANTING", "lang": "kn"},
        {"phone": "+910000000015", "panchayat_idx": 10, "crop": "cotton", "soil": "red_sandy", "irr": IrrigationSource.RAINFED, "size": 3.0, "status": "VEGETATIVE", "lang": "te"},
        {"phone": "+910000000016", "panchayat_idx": 15, "crop": "wheat", "soil": "alluvial", "irr": IrrigationSource.CANAL, "size": 6.5, "status": "PLANNED", "lang": "pa"},
    ]

    for f in farmers_spec:
        user = User(
            phone_number=f["phone"],
            role=UserRole.FARMER,
            preferred_language=f["lang"],
            consent_given_at=now,
            is_active=True
        )
        session.add(user)
        await session.flush()

        profile = FarmerProfile(
            user_id=user.id,
            panchayat_id=panchayat_objs[f["panchayat_idx"]].id,
            crop_type=f["crop"],
            sowing_date=date.today() - timedelta(days=20),
            soil_type=f["soil"],
            irrigation_source=f["irr"],
            farm_size_acres=f["size"],
            crop_status=f["status"]
        )
        session.add(profile)

    await session.flush()
    print("-> Seeded Users and Farmer Profiles successfully.")

async def seed_climate_and_ml(session: AsyncSession, panchayat_objs):
    print("-> Seeding Global Indices, Model Version, and Grid Forecasts...")
    
    # 1. Global Indices
    today = date.today()
    gi = GlobalIndices(
        date=today,
        nino34=0.8, # +0.8 El Nino warm neutral
        iod_dmi=0.2, # +0.2 positive IOD
        mjo_phase=3, # MJO Phase 3
        mjo_amplitude=1.2,
        data_source=DataSource.LIVE
    )
    session.add(gi)

    # 2. Model Version
    # Non-negotiable: metrics_json=None and is_trained=False for an untrained model.
    # Fabricated metrics (e.g. brier_score, auc_roc) must never be stored here.
    # Real metrics are written only after leave-one-year-out evaluation on CHIRPS hindcast.
    mv = ModelVersion(
        version_tag="v1.0.0-xgb-convlstm",
        model_type="XGBoost+ConvLSTM-Ensemble",
        metrics_json=None,   # No metrics until trained on real data (see docs/model_card.md)
        is_active=True,
        is_trained=False,    # Pipeline-only; training requires CHIRPS hindcast (Phase 8+)
    )
    session.add(mv)
    await session.flush()


    # 3. Grid Forecasts for each Panchayat (4 weeks lead time)
    forecast_objs = []
    for panch in panchayat_objs:
        for week in range(1, 5):
            target_start = today + timedelta(days=7 * week)
            target_end = target_start + timedelta(days=6)
            
            # Deterministic, realistic probabilities
            # e.g., onset prob higher in early lead, break prob varying
            base_onset = max(0.1, min(0.9, 0.85 - 0.15 * week))
            base_break = max(0.1, min(0.9, 0.2 + 0.18 * week))
            excess_rain = max(0.05, min(0.8, 0.1 + 0.12 * (4 - week)))

            gf = GridForecast(
                panchayat_id=panch.id,
                block_id=panch.block_id,
                issue_date=today,
                target_week_start=target_start,
                target_week_end=target_end,
                lead_week=week,
                onset_prob=round(base_onset, 3),
                break_prob=round(base_break, 3),
                excess_rain_prob=round(excess_rain, 3),
                p10_rainfall_mm=round(5.0 * week, 1),
                p50_rainfall_mm=round(25.0 + 10.0 * week, 1),
                p90_rainfall_mm=round(65.0 + 15.0 * week, 1),
                confidence=round(0.85 - 0.05 * week, 2),
                data_source=DataSource.SIMULATED, # Enforce data honesty
                model_version_id=mv.id,
                features_json={"nino34": 0.8, "iod_dmi": 0.2, "mjo_phase": 3, "soil_moisture_idx": 0.62},
                shap_values_json={"nino34": -0.12, "iod_dmi": +0.08, "mjo_phase": +0.15}
            )
            session.add(gf)
            forecast_objs.append(gf)

    await session.flush()
    print(f"-> Seeded {len(forecast_objs)} Grid Forecasts across 4 lead weeks.")
    return forecast_objs

async def seed_agronomy_rules_and_advisories(session: AsyncSession, forecast_objs):
    print("-> Seeding Agronomic Rules and Sample Advisories...")
    
    rules = [
        AgronomicRule(
            rule_code="RULE-COTTON-SAFE-TO-SOW",
            crop_type="cotton",
            growth_stage="SOWING_PLANNED",
            trigger_condition_json={"onset_prob_gte": 0.75, "break_prob_lt": 0.40},
            advisory_template_en="Safe to sow cotton: Monsoon onset probability is {onset_prob_pct} with low break risk ({break_prob_pct}). Soil moisture conditions are optimal.",
            advisory_template_local={
                "mr": "कापूस पेरणीस अनुकूल: मान्सून आगमनाची शक्यता {onset_prob_pct} असून खंडाचा धोका कमी आहे. पेरणी सुरू करू शकता.",
                "hi": "कपास बुवाई के लिए अनुकूल समय: मानसून आगमन की संभावना {onset_prob_pct} है।"
            },
            severity=AdvisorySeverity.HIGH,
            action_type="SAFE_TO_SOW",
            source_reference="ICAR-CICR Sowing Guidelines 2024",
            is_approved=True,
            version=1
        ),
        AgronomicRule(
            rule_code="RULE-PULSES-ALTER-CROP",
            crop_type="cotton",
            growth_stage="SOWING_PLANNED",
            trigger_condition_json={"onset_prob_lt": 0.60},
            advisory_template_en="Delayed monsoon onset detected ({onset_prob_pct}). Switch to short-duration alternate crops (pigeon pea, green gram, or pearl millet).",
            advisory_template_local={
                "mr": "मान्सून लांबल्याने ({onset_prob_pct}) कापसाऐवजी कमी कालावधीच्या कडधान्य पिकांची (तूर, मूग, बाजरी) निवड करा.",
                "hi": "मानसून में देरी की स्थिति में कम अवधि की वैकल्पिक फसलों का चयन करें।"
            },
            severity=AdvisorySeverity.HIGH,
            action_type="ALTER_CROP",
            source_reference="CRIDA Contingency Plan 2024",
            is_approved=True,
            version=1
        ),
        AgronomicRule(
            rule_code="RULE-SOYBEAN-EARLY-HARVEST",
            crop_type="soybean",
            growth_stage="MATURITY",
            trigger_condition_json={"excess_rain_prob_gte": 0.75},
            advisory_template_en="Critical downpour expected ({excess_prob_pct}). Harvest mature crop immediately and store in covered sheds to prevent grain rot.",
            advisory_template_local={
                "mr": "मुसळधार पावसाचा इशारा ({excess_prob_pct}). परिपक्व सोयाबीनची तात्काळ काढणी करून सुरक्षित ठिकाणी साठवा.",
                "hi": "भारी वर्षा की चेतावनी। पकी हुई फसल की तुरंत कटाई करें।"
            },
            severity=AdvisorySeverity.CRITICAL,
            action_type="EARLY_HARVEST",
            source_reference="ICAR-IISR Harvest Advisory 2024",
            is_approved=True,
            version=1
        ),
        AgronomicRule(
            rule_code="RULE-GROUNDNUT-PROTECTIVE-IRRIGATION",
            crop_type="groundnut",
            growth_stage="POD_FORMATION",
            trigger_condition_json={"break_prob_gte": 0.70, "irrigation_sources": ["CANAL", "BOREWELL", "TANK"]},
            advisory_template_en="Dry spell forecast ({break_prob_pct}). Irrigated fields: Apply protective irrigation before dry spell to avoid pod drying.",
            advisory_template_local={
                "kn": "ಒಣ ಹವೆಯ ಮುನ್ಸೂಚನೆ ({break_prob_pct}). ನೀರಾವರಿ ಸೌಲಭ್ಯವಿರುವ ಜಮೀನುಗಳಿಗೆ ರಕ್ಷಣಾತ್ಮಕ ನೀರಾವರಿ ಒದಗಿಸಿ."
            },
            severity=AdvisorySeverity.HIGH,
            action_type="PROTECTIVE_IRRIGATION",
            source_reference="UAS Dharwad Contingent Irrigation Advisory 2024",
            is_approved=True,
            version=1
        ),
        AgronomicRule(
            rule_code="RULE-GROUNDNUT-MOISTURE-CONSERVATION",
            crop_type="groundnut",
            growth_stage="POD_FORMATION",
            trigger_condition_json={"break_prob_gte": 0.70, "irrigation_sources": ["RAINFED", "OTHER"]},
            advisory_template_en="Dry spell forecast ({break_prob_pct}). Rainfed fields: Perform shallow inter-cultivation and organic mulching to conserve root zone moisture.",
            advisory_template_local={
                "kn": "ಒಣ ಹವೆಯ ಮುನ್ಸೂಚನೆ ({break_prob_pct}). ಮಳೆಯಾಶ್ರಿತ ಜಮೀನಿನಲ್ಲಿ ತೇವಾಂಶ ಸಂರಕ್ಷಣೆಗಾಗಿ ಎಡೆಕುಂಟೆ ಹೊಡೆದು ಸಾವಯವ ಹೊದಿಕೆ ಹಾಕಿ."
            },
            severity=AdvisorySeverity.HIGH,
            action_type="MOISTURE_CONSERVATION",
            source_reference="CRIDA Rainfed Dryland Advisory 2024",
            is_approved=True,
            version=1
        ),
    ]

    for r in rules:
        session.add(r)
    await session.flush()

    # Generate sample advisories
    adv1 = GeneratedAdvisory(
        panchayat_id=forecast_objs[0].panchayat_id,
        block_id=forecast_objs[0].block_id,
        forecast_id=forecast_objs[0].id,
        rule_id=rules[0].id,
        crop_type="cotton",
        language="mr",
        headline="कोरड्या खंडाचा इशारा: आठवडा 3",
        content="आठवडा 3 मध्ये कोरड्या खंडाची 74% शक्यता आहे. ओलावा टिकवण्यासाठी आच्छादन (मल्चिंग) करा.",
        severity=AdvisorySeverity.HIGH,
        approval_status=AdvisoryApprovalStatus.PENDING, # Pending Officer approval
        data_source=DataSource.SIMULATED
    )
    session.add(adv1)

    adv2 = GeneratedAdvisory(
        panchayat_id=forecast_objs[1].panchayat_id,
        block_id=forecast_objs[1].block_id,
        forecast_id=forecast_objs[1].id,
        rule_id=rules[1].id,
        crop_type="rice",
        language="kn",
        headline="ಭಾರೀ ಮಳೆಯ ಎಚ್ಚರಿಕೆ: ಬಸಿದುಹೋಗುವ ಕಾಲುವೆ ತೆರೆಯಿರಿ",
        content="ಅತಿಯಾದ ಮಳೆ (78%) ಮುನ್ಸೂಚನೆ. ಸಸಿಗಳು ಮುಳುಗಡೆಯಾಗದಂತೆ ತಕ್ಷಣ ನೀರು ಹೊರಹೋಗಲು ಕಾಲುವೆ ಸಿದ್ಧಪಡಿಸಿ.",
        severity=AdvisorySeverity.CRITICAL,
        approval_status=AdvisoryApprovalStatus.APPROVED, # Officer approved
        data_source=DataSource.SIMULATED
    )
    session.add(adv2)
    await session.flush()

    # Notification log with BLOCKED_SIMULATED for non-negotiable data honesty
    notif = NotificationLog(
        advisory_id=adv2.id,
        recipient_user_id=1,
        channel=NotificationChannel.SMS,
        message_content=adv2.content,
        dispatch_status=NotificationStatus.BLOCKED_SIMULATED, # Non-negotiable test safety
        idempotency_key=f"SEED-NOTIF-{adv2.id}-1",
    )
    session.add(notif)
    await session.flush()
    print("-> Seeded Agronomic Rules, Sample Advisories, and BLOCKED_SIMULATED Notification Log.")

async def refresh_materialized_view(session: AsyncSession):
    print("-> Refreshing BlockForecastAgg Materialized View...")
    await session.execute(text("REFRESH MATERIALIZED VIEW block_forecast_agg;"))
    print("-> Materialized View Refreshed successfully.")

def load_real_boundaries(file_path: str):
    """
    Loader for real LGD/SHRUG shapefiles or GeoJSON boundaries.
    Can be called to ingest production-grade polygon shapefiles.
    """
    if not os.path.exists(file_path):
        print(f"Notice: Shapefile path {file_path} does not exist. Skipping real shapefile ingest.")
        return
    try:
        import geopandas as gpd
        gdf = gpd.read_file(file_path)
        print(f"Loaded shapefile with {len(gdf)} records.")
        return gdf
    except Exception as e:
        print(f"Error loading shapefile: {e}")
        return None

async def seed_db():
    print("=== Starting Pannaga Database Seeding ===")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        try:
            block_objs, panchayat_objs = await seed_geography(session)
            await seed_users(session, block_objs, panchayat_objs)
            forecast_objs = await seed_climate_and_ml(session, panchayat_objs)
            await seed_agronomy_rules_and_advisories(session, forecast_objs)
            await session.commit()
            
            # Refresh materialized view in a separate transaction after commit
            await refresh_materialized_view(session)
            await session.commit()
            print("=== Pannaga Database Seeding Completed Successfully! ===")
        except Exception as e:
            await session.rollback()
            print(f"Seeding failed: {e}")
            raise
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_db())
