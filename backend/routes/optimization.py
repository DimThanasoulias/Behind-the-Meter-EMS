"""FastAPI REST routes for constrained load optimization and closed-loop decision support.

Exposes:
- POST /api/v1/optimization/solve: Solve rolling 24-hour MILP schedule.
- GET /api/v1/optimization/recommendations: Retrieve prioritized operational action recommendations.
- POST /api/v1/optimization/verify: Certify real telemetry against baseline counterfactual.
- GET /api/v1/optimization/status: Engine operational status and solver capability metadata.
"""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from optimization_engine.models import (
    ActionRecommendation,
    BESSLoad,
    DefrostLoad,
    HVACLoad,
    OptimizationProblem,
    ProductionBatchLoad,
    ScheduleResult,
    VerificationRecord,
)
from optimization_engine.solver import ConstrainedLoadSolver
from optimization_engine.decision_support import ClosedLoopVerifier, DecisionSupportEngine

router = APIRouter(prefix="/optimization", tags=["Optimization & Decision Support"])

# In-memory recommendation and verification registry for active session
_active_recommendations: List[ActionRecommendation] = []
_active_verifications: List[VerificationRecord] = []


class SolveRequest(BaseModel):
    facility_id: str = "fac_bakery_01"
    contracted_capacity_kw: float = Field(default=35.0, gt=0.0)
    baseline_load_kw: Optional[List[float]] = None
    tariff_rates_eur_kwh: Optional[List[float]] = None
    include_defrost: bool = True
    include_batch_ovens: bool = True
    include_hvac: bool = True
    include_bess: bool = True


class VerificationRequest(BaseModel):
    recommendation_id: str
    actual_measured_kw: float
    counterfactual_baseline_kw: float
    tariff_eur_kwh: float = 0.225
    capacity_penalty_rate: float = 18.50


@router.get("/status")
def get_optimization_status():
    """Return optimization engine capabilities and health status."""
    return {
        "status": "operational",
        "solver_backend": "scipy_highs_milp",
        "paradigm": "Measure -> Predict -> Optimize -> Act -> Verify",
        "supported_constraints": [
            "flexible_refrigeration_defrost",
            "production_batch_deck_ovens",
            "hvac_thermal_comfort_deadbands",
            "bess_soc_and_power_limits",
            "contracted_capacity_surcharge_avoidance",
        ],
        "active_recommendations_count": len(_active_recommendations),
        "verified_interventions_count": len(_active_verifications),
    }


@router.post("/solve", response_model=dict)
def solve_schedule(req: SolveRequest):
    """Solve multi-period rolling constrained load scheduling problem."""
    # Build default commercial profile if not provided
    baseline = req.baseline_load_kw or [
        8.0, 7.5, 7.0, 6.8, 12.0, 18.5, 22.0, 24.5,
        26.0, 28.0, 27.5, 25.0, 24.0, 26.5, 29.0, 31.5,
        28.0, 22.0, 18.0, 15.0, 14.0, 12.5, 10.0, 8.5,
    ]

    # Default day-ahead spot / yellow tariff curve with afternoon peak
    tariffs = req.tariff_rates_eur_kwh or [
        0.095, 0.088, 0.082, 0.080, 0.085, 0.110, 0.145, 0.180,
        0.195, 0.210, 0.225, 0.240, 0.255, 0.285, 0.310, 0.290,
        0.245, 0.210, 0.190, 0.175, 0.150, 0.135, 0.115, 0.100,
    ]

    defrost_loads = [DefrostLoad()] if req.include_defrost else []
    batch_loads = [ProductionBatchLoad()] if req.include_batch_ovens else []
    hvac_loads = [HVACLoad()] if req.include_hvac else []
    bess = BESSLoad() if req.include_bess else None

    problem = OptimizationProblem(
        horizon_hours=24,
        time_step_hours=1.0,
        baseline_load_kw=baseline,
        tariff_rates_eur_kwh=tariffs,
        contracted_capacity_kw=req.contracted_capacity_kw,
        defrost_loads=defrost_loads,
        hvac_loads=hvac_loads,
        batch_loads=batch_loads,
        bess=bess,
    )

    solver = ConstrainedLoadSolver(problem)
    res = solver.solve()

    # Generate decision support recommendations
    engine = DecisionSupportEngine(facility_id=req.facility_id)
    recs = engine.generate_recommendations(problem, res)

    # Store active recommendations
    global _active_recommendations
    _active_recommendations = recs

    return {
        "status": res.status,
        "is_optimal": res.is_optimal,
        "horizon_hours": res.horizon_hours,
        "baseline_cost_eur": res.baseline_cost_eur,
        "optimized_cost_eur": res.optimized_cost_eur,
        "savings_eur": res.savings_eur,
        "savings_pct": res.savings_pct,
        "peak_baseline_kw": res.peak_baseline_kw,
        "peak_optimized_kw": res.peak_optimized_kw,
        "peak_reduction_kw": res.peak_reduction_kw,
        "capacity_breached_baseline": res.capacity_breached_baseline,
        "capacity_breached_optimized": res.capacity_breached_optimized,
        "solve_time_ms": res.solve_time_ms,
        "device_schedules": res.device_schedules,
        "hvac_temperatures": res.hvac_temperatures,
        "bess_soc_history": res.bess_soc_history,
        "recommendations_count": len(recs),
        "recommendations": [r.model_dump() for r in recs],
    }


@router.get("/recommendations", response_model=List[ActionRecommendation])
def get_recommendations(facility_id: Optional[str] = Query(None)):
    """Retrieve active decision-support recommendations."""
    if facility_id:
        return [r for r in _active_recommendations if r.facility_id == facility_id]
    return _active_recommendations


@router.post("/verify", response_model=VerificationRecord)
def verify_intervention(req: VerificationRequest):
    """Certify post-intervention telemetry against baseline counterfactual."""
    rec = next((r for r in _active_recommendations if r.recommendation_id == req.recommendation_id), None)
    if not rec:
        # Generate synthetic reference recommendation if not found
        from optimization_engine.models import PriorityLevel, RecommendationCategory
        rec = ActionRecommendation(
            recommendation_id=req.recommendation_id,
            facility_id="fac_commercial_01",
            category=RecommendationCategory.DEFROST_SHIFT,
            priority=PriorityLevel.HIGH,
            title="Ad-hoc Intervention Verification",
            description_el="Επαλήθευση παρέμβασης",
            description_en="Intervention verification",
            asset_name="Cold Storage Compressor",
            original_window="14:00-15:00",
            recommended_window="16:00-17:00",
            peak_load_avoided_kw=6.8,
            estimated_savings_eur=14.20,
            confidence_score=0.92,
            contracted_capacity_kw=35.0,
            projected_peak_kw=28.2,
        )

    verifier = ClosedLoopVerifier()
    record = verifier.verify_intervention(
        recommendation=rec,
        actual_measured_kw=req.actual_measured_kw,
        counterfactual_baseline_kw=req.counterfactual_baseline_kw,
        tariff_eur_kwh=req.tariff_eur_kwh,
        capacity_penalty_rate=req.capacity_penalty_rate,
    )

    _active_verifications.append(record)
    return record


@router.get("/verifications", response_model=List[VerificationRecord])
def get_verifications():
    """Retrieve history of certified closed-loop intervention audits."""
    return _active_verifications
