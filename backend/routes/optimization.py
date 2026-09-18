"""FastAPI REST routes for constrained load optimization and closed-loop decision support.

Exposes:
- POST /api/v1/optimization/solve: Solve rolling 24-hour MILP schedule.
- GET /api/v1/optimization/recommendations: Retrieve prioritized operational action recommendations.
- POST /api/v1/optimization/verify: Certify real telemetry against baseline counterfactual.
- GET /api/v1/optimization/status: Engine operational status and solver capability metadata.
- GET /api/v1/optimization/verifications: Retrieve audit log of verified interventions.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from optimization_engine.models import (
    ActionRecommendation,
    BESSLoad,
    DefrostLoad,
    HVACLoad,
    OptimizationProblem,
    ProductionBatchLoad,
    VerificationRecord,
)
from optimization_engine.solver import ConstrainedLoadSolver
from optimization_engine.decision_support import ClosedLoopVerifier, DecisionSupportEngine

router = APIRouter(prefix="/optimization", tags=["Optimization & Decision Support"])

# In-memory recommendation and verification registry partitioned by facility_id
_active_recommendations: Dict[str, List[ActionRecommendation]] = {}
_active_verifications: Dict[str, List[VerificationRecord]] = {}


class SolveRequest(BaseModel):
    facility_id: str = "fac_bakery_01"
    contracted_capacity_kw: float = Field(default=35.0, gt=0.0)
    baseline_load_kw: Optional[List[float]] = None
    tariff_rates_eur_kwh: Optional[List[float]] = None
    include_defrost: bool = True
    include_batch_ovens: bool = True
    include_hvac: bool = True
    include_bess: bool = True

    @field_validator("baseline_load_kw")
    @classmethod
    def validate_baseline(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) != 24:
            raise ValueError(f"baseline_load_kw must have exactly 24 hourly entries, received {len(v)}")
        return v

    @field_validator("tariff_rates_eur_kwh")
    @classmethod
    def validate_tariffs(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) != 24:
            raise ValueError(f"tariff_rates_eur_kwh must have exactly 24 hourly entries, received {len(v)}")
        return v


class VerificationRequest(BaseModel):
    recommendation_id: str
    actual_measured_kw: float
    counterfactual_baseline_kw: float
    tariff_eur_kwh: float = 0.225
    capacity_penalty_rate: float = 18.50


@router.get("/status")
def get_optimization_status():
    """Return optimization engine capabilities and health status."""
    total_recs = sum(len(recs) for recs in _active_recommendations.values())
    total_vers = sum(len(vers) for vers in _active_verifications.values())
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
        "active_recommendations_count": total_recs,
        "verified_interventions_count": total_vers,
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

    # Store active recommendations partitioned by facility_id
    _active_recommendations[req.facility_id] = recs

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
    """Retrieve active decision-support recommendations with optional facility filtering."""
    if facility_id:
        return _active_recommendations.get(facility_id, [])
    return [rec for recs in _active_recommendations.values() for rec in recs]


@router.post("/verify", response_model=VerificationRecord)
def verify_intervention(req: VerificationRequest):
    """Certify post-intervention telemetry against baseline counterfactual.
    
    Raises 404 if the recommendation_id is not found in the active registry.
    """
    rec: Optional[ActionRecommendation] = None
    for facility_recs in _active_recommendations.values():
        for r in facility_recs:
            if r.recommendation_id == req.recommendation_id:
                rec = r
                break
        if rec:
            break

    if not rec:
        raise HTTPException(
            status_code=404,
            detail=f"Recommendation '{req.recommendation_id}' not found. Cannot verify non-existent intervention.",
        )

    verifier = ClosedLoopVerifier()
    record = verifier.verify_intervention(
        recommendation=rec,
        actual_measured_kw=req.actual_measured_kw,
        counterfactual_baseline_kw=req.counterfactual_baseline_kw,
        tariff_eur_kwh=req.tariff_eur_kwh,
        capacity_penalty_rate=req.capacity_penalty_rate,
    )

    _active_verifications.setdefault(rec.facility_id, []).append(record)
    return record


@router.get("/verifications", response_model=List[VerificationRecord])
def get_verifications(facility_id: Optional[str] = Query(None)):
    """Retrieve history of certified closed-loop intervention audits."""
    if facility_id:
        return _active_verifications.get(facility_id, [])
    return [v for vers in _active_verifications.values() for v in vers]
