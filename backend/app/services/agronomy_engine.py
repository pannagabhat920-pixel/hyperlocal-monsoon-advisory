"""
Agronomy Rules Engine.

Evaluates GridForecast probabilities against AgronomicRule triggers
and manages advisory generation and farmer-level delivery limits.

Core Rules & Thresholds:
  - DELAY_SOWING:              false_onset_prob >= 0.60, crop_status == NOT_STARTED/PLANNED
  - SAFE_TO_SOW:               onset_prob >= 0.65 AND false_onset_prob < 0.30
  - ALTER_CROP:                false_onset_prob >= 0.60 AND past_sowing_window
  - BREAK_WARNING:             break_prob >= 0.70 AND break_duration_days_p50 >= 10
  - EXCESS_RAIN / DOWNPOUR:    excess_rain_prob >= 0.75

Irrigation Branching (Exhaustive & Mutually Exclusive):
  - IRRIGATED (CANAL, BOREWELL_WELL, BOREWELL, TANK_POND, TANK, DRIP_SPRINKLER):
    triggers PROTECTIVE_IRRIGATION
  - RAINFED (RAINFED, OTHER):
    triggers MOISTURE_CONSERVATION

Non-negotiable Delivery & Escalation Policies:
  - 72h cooldown is per FARMER (not panchayat).
  - Escalation exception applies ONLY when risk ESCALATES above the last sent advisory
    (e.g., HIGH -> CRITICAL). Repeated alerts of equal or lower severity (e.g. CRITICAL -> CRITICAL)
    within 72h are suppressed to prevent spam.
  - Farmer cycle limit: At most 1 primary + 1 secondary advisory per farmer per cycle.
  - CRITICAL / HIGH advisories require human-in-the-loop Extension Officer approval (PENDING).
  - MEDIUM / LOW (ADVISORY / INFO) advisories are AUTO_APPROVED.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agronomy import AgronomicRule, GeneratedAdvisory, NotificationLog
from app.models.climate import GridForecast
from app.models.enums import (
    AdvisoryApprovalStatus,
    AdvisorySeverity,
    DataSource,
    IrrigationSource,
    NotificationStatus,
)
from app.models.users import FarmerProfile

logger = logging.getLogger(__name__)

# Trigger thresholds
ONSET_SAFE_MIN = 0.65
FALSE_ONSET_SAFE_MAX = 0.30
FALSE_ONSET_TRIGGER = 0.60
BREAK_PROB_TRIGGER = 0.70
BREAK_DURATION_TRIGGER = 10.0
EXCESS_RAIN_TRIGGER = 0.75

COOLDOWN_HOURS = 72

SEVERITY_WEIGHT = {
    AdvisorySeverity.CRITICAL: 4,
    AdvisorySeverity.HIGH: 3,
    AdvisorySeverity.MEDIUM: 2,
    AdvisorySeverity.LOW: 1,
    AdvisorySeverity.ADVISORY: 2,
    AdvisorySeverity.INFO: 1,
}

IRRIGATED_SOURCES = {
    IrrigationSource.CANAL,
    IrrigationSource.BOREWELL_WELL,
    IrrigationSource.TANK_POND,
    IrrigationSource.DRIP_SPRINKLER,
}

RAINFED_SOURCES = {
    IrrigationSource.RAINFED,
    IrrigationSource.OTHER,
}


def get_irrigation_branch(source: Union[IrrigationSource, str]) -> str:
    """
    Maps every IrrigationSource enum value to exactly one branch:
      - 'IRRIGATED' (for canal, borewell/well, tank/pond, drip/sprinkler)
      - 'RAINFED'   (for rainfed, other)
    """
    val = source.value if hasattr(source, "value") else str(source)
    if any(val == (s.value if hasattr(s, "value") else s) for s in IRRIGATED_SOURCES):
        return "IRRIGATED"
    return "RAINFED"


def _needs_approval(severity: AdvisorySeverity) -> AdvisoryApprovalStatus:
    """CRITICAL and HIGH require human-in-the-loop officer approval."""
    if severity in (AdvisorySeverity.CRITICAL, AdvisorySeverity.HIGH):
        return AdvisoryApprovalStatus.PENDING
    return AdvisoryApprovalStatus.AUTO_APPROVED


def _get_forecast_val(forecast: GridForecast, attr: str, default: float = 0.0) -> float:
    """Safely get numeric attribute from forecast column or features_json."""
    val = getattr(forecast, attr, None)
    if val is not None:
        return float(val)
    if forecast.features_json and isinstance(forecast.features_json, dict):
        if attr in forecast.features_json:
            return float(forecast.features_json[attr])
    return default


def evaluate_rule(
    forecast: GridForecast,
    rule: AgronomicRule,
    farmer_profile: Optional[FarmerProfile] = None,
    is_past_sowing_window: bool = False,
) -> bool:
    """
    Check if a forecast matches an AgronomicRule according to the spec.
    """
    cond = rule.trigger_condition_json or {}

    # 0. Finished/harvested crops receive NO sowing or irrigation advisories
    if farmer_profile and farmer_profile.crop_status:
        st = farmer_profile.crop_status.upper()
        if st in ("HARVESTED", "FINISHED", "COMPLETED"):
            return False
        # Sowing rules strictly require unplanted/NOT_STARTED crops
        if rule.action_type in ("SAFE_TO_SOW", "DELAY_SOWING", "ALTER_CROP") and st not in ("NOT_STARTED", "PLANNED"):
            return False

    # 1. False onset probability
    false_onset = _get_forecast_val(forecast, "false_onset_prob", 0.0)
    fo_min = cond.get("false_onset_prob_gte", cond.get("false_onset_min"))
    if fo_min is not None and false_onset < fo_min:
        return False
    fo_lt = cond.get("false_onset_prob_lt", cond.get("false_onset_max"))
    if fo_lt is not None and false_onset >= fo_lt:
        return False

    # 2. Onset probability
    onset_min = cond.get("onset_prob_gte", cond.get("onset_prob_min"))
    if onset_min is not None and forecast.onset_prob < onset_min:
        return False
    onset_lt = cond.get("onset_prob_lt", cond.get("onset_prob_max"))
    if onset_lt is not None and forecast.onset_prob >= onset_lt:
        return False

    # 3. Break probability
    break_min = cond.get("break_prob_gte", cond.get("break_prob_min"))
    if break_min is not None and forecast.break_prob < break_min:
        return False
    break_lt = cond.get("break_prob_lt", cond.get("break_prob_max"))
    if break_lt is not None and forecast.break_prob >= break_lt:
        return False

    # 4. Break duration (days p50)
    break_dur = _get_forecast_val(forecast, "break_duration_days_p50", 0.0)
    dur_min = cond.get("break_duration_days_p50_gte", cond.get("break_duration_min"))
    if dur_min is not None and break_dur < dur_min:
        return False

    # 5. Excess / heavy rain probability
    excess_min = cond.get("excess_rain_prob_gte", cond.get("excess_rain_prob_min"))
    if excess_min is not None and forecast.excess_rain_prob < excess_min:
        return False
    excess_lt = cond.get("excess_rain_prob_lt", cond.get("excess_rain_prob_max"))
    if excess_lt is not None and forecast.excess_rain_prob >= excess_lt:
        return False

    # 6. Sowing window requirement (for ALTER_CROP: requires false_onset >= 0.60 AND past window)
    if cond.get("requires_past_sowing_window", False) or rule.action_type == "ALTER_CROP":
        past_window = is_past_sowing_window or (farmer_profile and getattr(farmer_profile, "is_past_sowing_window", False))
        if not past_window:
            return False

    # 7. Crop status requirement (e.g. DELAY_SOWING requires NOT_STARTED or PLANNED)
    if "allowed_crop_status" in cond and farmer_profile:
        if farmer_profile.crop_status not in cond["allowed_crop_status"]:
            return False

    # 8. Break rule limited to standing crop stages: SOWN, VEGETATIVE, FLOWERING_PODDING
    if (rule.action_type in ("BREAK_WARNING", "PROTECTIVE_IRRIGATION", "MOISTURE_CONSERVATION") or break_min is not None) and rule.action_type not in ("DELAY_SOWING", "SAFE_TO_SOW"):
        if farmer_profile and farmer_profile.crop_status:
            standing_stages = {"SOWN", "SOWING", "VEGETATIVE", "FLOWERING_PODDING", "FLOWERING"}
            if farmer_profile.crop_status.upper() not in standing_stages:
                return False

    # 9. Excess rain rules stage limitations:
    # DRAINAGE_PREP applies to standing vegetative / flowering crops
    if rule.action_type == "DRAINAGE_PREP" and farmer_profile and farmer_profile.crop_status:
        if farmer_profile.crop_status.upper() not in {"SOWN", "SOWING", "VEGETATIVE", "FLOWERING_PODDING", "FLOWERING"}:
            return False

    # EARLY_HARVEST applies when crop is harvest ready / mature
    if rule.action_type == "EARLY_HARVEST" and farmer_profile and farmer_profile.crop_status:
        if farmer_profile.crop_status.upper() not in {"HARVEST_READY", "HARVESTING", "FLOWERING_PODDING"}:
            return False

    # 10. Irrigation branch check
    if farmer_profile and farmer_profile.irrigation_source:
        branch = get_irrigation_branch(farmer_profile.irrigation_source)
        # Check rule action_type directly
        if rule.action_type == "PROTECTIVE_IRRIGATION" and branch != "IRRIGATED":
            return False
        if rule.action_type == "MOISTURE_CONSERVATION" and branch != "RAINFED":
            return False
        # Check trigger_condition_json overrides if specified
        if "irrigation_branch" in cond and cond["irrigation_branch"] != branch:
            return False
        if "irrigation_sources" in cond:
            farmer_val = farmer_profile.irrigation_source.value if hasattr(farmer_profile.irrigation_source, "value") else str(farmer_profile.irrigation_source)
            if farmer_val not in cond["irrigation_sources"]:
                return False

    return True


def render_template(template: str, forecast: GridForecast, rule: AgronomicRule) -> str:
    """Substitute template variables while strictly preserving formatting."""
    week_labels = {1: "this week", 2: "next week", 3: "in 3 weeks", 4: "in 4 weeks"}
    return template.format(
        onset_prob_pct=f"{forecast.onset_prob * 100:.0f}%",
        break_prob_pct=f"{forecast.break_prob * 100:.0f}%",
        excess_prob_pct=f"{forecast.excess_rain_prob * 100:.0f}%",
        false_onset_prob_pct=f"{_get_forecast_val(forecast, 'false_onset_prob', 0.0) * 100:.0f}%",
        break_duration_days=f"{_get_forecast_val(forecast, 'break_duration_days_p50', 7.0):.0f}",
        lead_week=str(forecast.lead_week),
        p50_mm=f"{forecast.p50_rainfall_mm:.1f} mm",
        week_label=week_labels.get(forecast.lead_week, f"in {forecast.lead_week} weeks"),
        crop_type=rule.crop_type,
    )


async def check_farmer_cooldown(
    farmer_id: int,
    new_severity: AdvisorySeverity,
    db: AsyncSession,
) -> bool:
    """
    72h cooldown check per FARMER.

    CRITICAL escalation exception applies ONLY when risk ESCALATES above
    the last sent advisory (new_severity weight > last_severity weight).
    Repeated alerts of equal or lower severity within 72h (e.g. CRITICAL -> CRITICAL)
    are suppressed to prevent spamming farmers.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=COOLDOWN_HOURS)

    result = await db.execute(
        select(NotificationLog, GeneratedAdvisory.severity)
        .join(GeneratedAdvisory, NotificationLog.advisory_id == GeneratedAdvisory.id)
        .where(
            NotificationLog.recipient_user_id == farmer_id,
            NotificationLog.dispatch_status.in_([
                NotificationStatus.SENT,
                NotificationStatus.DELIVERED,
                NotificationStatus.QUEUED,
                NotificationStatus.BLOCKED_SIMULATED,
            ]),
            NotificationLog.created_at >= cutoff,
        )
        .order_by(NotificationLog.created_at.desc())
        .limit(1)
    )
    row = result.first()

    if not row:
        return True  # No notification in the last 72 hours -> Allowed

    last_log, last_severity = row
    last_weight = SEVERITY_WEIGHT.get(last_severity, 1)
    new_weight = SEVERITY_WEIGHT.get(new_severity, 1)

    # Escalation exception: Allowed ONLY when risk level escalates strictly above previous
    if new_weight > last_weight:
        logger.info(
            f"[AgronomyEngine] Escalation exception granted for farmer {farmer_id}: "
            f"{last_severity.value} (w={last_weight}) -> {new_severity.value} (w={new_weight})"
        )
        return True

    logger.debug(
        f"[AgronomyEngine] Cooldown active for farmer {farmer_id}: "
        f"new severity {new_severity.value} (w={new_weight}) <= last {last_severity.value} (w={last_weight}). Suppressed."
    )
    return False


def select_farmer_cycle_advisories(
    candidate_advisories: list[GeneratedAdvisory],
) -> tuple[Optional[GeneratedAdvisory], Optional[GeneratedAdvisory]]:
    """
    Limits advisories to MAX 1 primary + 1 secondary advisory per farmer per cycle.
    Prioritizes highest severity: CRITICAL > HIGH > MEDIUM > LOW.
    """
    if not candidate_advisories:
        return None, None

    sorted_adv = sorted(
        candidate_advisories,
        key=lambda a: SEVERITY_WEIGHT.get(a.severity, 0),
        reverse=True,
    )

    primary = sorted_adv[0]
    secondary = None

    for adv in sorted_adv[1:]:
        if adv.rule_id != primary.rule_id:
            secondary = adv
            break

    return primary, secondary


async def generate_advisories_for_forecast(
    forecast: GridForecast,
    db: AsyncSession,
) -> list[GeneratedAdvisory]:
    """
    Evaluate all approved rules in the database against a GridForecast.
    """
    rules_result = await db.execute(
        select(AgronomicRule).where(AgronomicRule.is_approved == True)
    )
    rules = rules_result.scalars().all()

    created: list[GeneratedAdvisory] = []

    for rule in rules:
        if not evaluate_rule(forecast, rule):
            continue

        approval_status = _needs_approval(rule.severity)

        try:
            headline = render_template(
                rule.advisory_template_en.split("\n")[0][:200],
                forecast, rule,
            )
            content = render_template(rule.advisory_template_en, forecast, rule)
        except Exception as e:
            logger.warning(f"[AgronomyEngine] Render failed for {rule.rule_code}: {e}")
            headline = rule.advisory_template_en[:100]
            content = rule.advisory_template_en

        advisory = GeneratedAdvisory(
            panchayat_id=forecast.panchayat_id,
            block_id=forecast.block_id,
            forecast_id=forecast.id,
            rule_id=rule.id,
            crop_type=rule.crop_type,
            language="en",
            headline=headline,
            content=content,
            severity=rule.severity,
            approval_status=approval_status,
            data_source=forecast.data_source,
        )
        db.add(advisory)
        created.append(advisory)

    return created
