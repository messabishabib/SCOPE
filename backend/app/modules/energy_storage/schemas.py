from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from ...core.identifiers import uid


class StorageAsset(BaseModel):
    id: str = Field(default_factory=uid)
    name: str = Field(min_length=1)
    energy_capacity_mwh: float = Field(gt=0)
    minimum_energy_mwh: float = Field(ge=0, default=0)
    initial_energy_mwh: float = Field(ge=0)
    terminal_energy_minimum_mwh: float = Field(ge=0)
    maximum_charge_power_mw: float = Field(gt=0)
    maximum_discharge_power_mw: float = Field(gt=0)
    charge_efficiency: float = Field(gt=0, le=1)
    discharge_efficiency: float = Field(gt=0, le=1)
    variable_charge_cost_per_mwh: float = Field(ge=0, default=0)
    variable_discharge_cost_per_mwh: float = Field(ge=0, default=0)

    @model_validator(mode="after")
    def validate_energy_levels(self):
        for label, value in (("minimum", self.minimum_energy_mwh), ("initial", self.initial_energy_mwh), ("terminal minimum", self.terminal_energy_minimum_mwh)):
            if value > self.energy_capacity_mwh:
                raise ValueError(f"{label} energy cannot exceed energy capacity")
        if self.initial_energy_mwh < self.minimum_energy_mwh or self.terminal_energy_minimum_mwh < self.minimum_energy_mwh:
            raise ValueError("initial and terminal energy must respect the minimum energy level")
        return self


class EnergyPlanningMode(str, Enum):
    deterministic = "deterministic"
    stochastic = "stochastic"


class EnergyScenario(BaseModel):
    id: str = Field(default_factory=uid)
    name: str = Field(min_length=1)
    probability: float | None = Field(default=None, ge=0, le=1)
    demand_multiplier: list[float]
    renewable_multiplier: list[float]
    price_multiplier: list[float]
    natural_inflow_mwh: list[float] = Field(default_factory=list)
    natural_inflow_mwh_by_storage: dict[str, list[float]] = Field(default_factory=dict)


class EnergyProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    number_of_periods: int = Field(ge=1, le=8760)
    interval_hours: float = Field(gt=0, le=24, default=1)
    currency: str = Field(min_length=3, max_length=3, default="EUR")
    storages: list[StorageAsset] = Field(min_length=1)
    demand_mwh: list[float]
    renewable_generation_mwh: list[float]
    grid_import_price_per_mwh: list[float]
    grid_export_price_per_mwh: list[float]
    shortage_penalty_per_mwh: float = Field(gt=0, default=10000)
    terminal_energy_value_per_mwh: float = Field(ge=0, default=0)
    scenarios: list[EnergyScenario] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_single_storage(cls, values):
        """Load v1 projects while exposing a portfolio-shaped v2 contract."""
        if isinstance(values, dict) and "storages" not in values and values.get("storage") is not None:
            values = {**values, "storages": [values["storage"]]}
        return values

    @property
    def storage(self) -> StorageAsset:
        """Compatibility accessor for older internal callers and Python clients."""
        return self.storages[0]

    @model_validator(mode="after")
    def validate_series(self):
        series = {
            "demand": self.demand_mwh,
            "renewable generation": self.renewable_generation_mwh,
            "grid import price": self.grid_import_price_per_mwh,
            "grid export price": self.grid_export_price_per_mwh,
        }
        for name, values in series.items():
            if len(values) != self.number_of_periods:
                raise ValueError(f"{name} series must match number_of_periods")
            if any(v < 0 for v in values):
                raise ValueError(f"{name} values cannot be negative")
        if any(export > imported for imported, export in zip(self.grid_import_price_per_mwh, self.grid_export_price_per_mwh)):
            raise ValueError("grid export price cannot exceed import price in deterministic v1")
        scenario_ids = {s.id for s in self.scenarios}
        if len(scenario_ids) != len(self.scenarios):
            raise ValueError("energy scenario IDs must be unique")
        for scenario in self.scenarios:
            if not scenario.natural_inflow_mwh:
                scenario.natural_inflow_mwh = [0.0] * self.number_of_periods
            for name, values in (("demand multiplier", scenario.demand_multiplier), ("renewable multiplier", scenario.renewable_multiplier), ("price multiplier", scenario.price_multiplier), ("natural inflow", scenario.natural_inflow_mwh)):
                if len(values) != self.number_of_periods:
                    raise ValueError(f"scenario {name} series must match number_of_periods")
                if any(v < 0 for v in values):
                    raise ValueError(f"scenario {name} values cannot be negative")
            unknown_assets = set(scenario.natural_inflow_mwh_by_storage) - {storage.id for storage in self.storages}
            if unknown_assets:
                raise ValueError(f"scenario inflows reference unknown storage IDs: {sorted(unknown_assets)}")
            for storage_id, values in scenario.natural_inflow_mwh_by_storage.items():
                if len(values) != self.number_of_periods:
                    raise ValueError(f"scenario inflow series for storage {storage_id} must match number_of_periods")
                if any(v < 0 for v in values):
                    raise ValueError(f"scenario inflow values for storage {storage_id} cannot be negative")
        storage_ids = [storage.id for storage in self.storages]
        if len(storage_ids) != len(set(storage_ids)):
            raise ValueError("storage IDs must be unique")
        return self


class EnergyProject(EnergyProjectCreate):
    id: str = Field(default_factory=uid)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EnergyOptimizationRequest(BaseModel):
    time_limit_seconds: int = Field(default=60, ge=1, le=3600)
    mode: EnergyPlanningMode = EnergyPlanningMode.deterministic
    current_period: int = Field(default=0, ge=0)
    current_energy_mwh: float | None = Field(default=None, ge=0)
    current_energy_mwh_by_storage: dict[str, float] | None = None
    lookahead_periods: int | None = Field(default=None, ge=1)
    commitment_periods: int = Field(default=1, ge=1)


class StoragePeriodResult(BaseModel):
    storage_id: str
    storage_name: str
    charge_power_mw: float
    discharge_power_mw: float
    stored_energy_start_mwh: float
    stored_energy_end_mwh: float


class EnergyPeriodResult(BaseModel):
    period: int
    demand_mwh: float
    renewable_generation_mwh: float
    import_price_per_mwh: float
    charge_power_mw: float
    discharge_power_mw: float
    stored_energy_start_mwh: float
    stored_energy_end_mwh: float
    grid_import_mwh: float
    grid_export_mwh: float
    unserved_energy_mwh: float
    renewable_curtailment_mwh: float
    storage_dispatches: list[StoragePeriodResult] = Field(default_factory=list)


class EnergyCostBreakdown(BaseModel):
    grid_import: float
    grid_export_revenue: float
    charging: float
    discharging: float
    shortage: float
    terminal_value: float
    total: float


class EnergyScenarioPerformance(BaseModel):
    scenario_id: str
    scenario_name: str
    probability: float
    total_cost: float
    total_unserved_mwh: float
    terminal_energy_mwh: float
    terminal_energy_mwh_by_storage: dict[str, float] = Field(default_factory=dict)


class StorageRecommendedAction(BaseModel):
    storage_id: str
    storage_name: str
    charge_power_mw: float
    discharge_power_mw: float


class EnergyRecommendedAction(BaseModel):
    period: int
    charge_power_mw: float
    discharge_power_mw: float
    explanation: str
    storage_actions: list[StorageRecommendedAction] = Field(default_factory=list)


class EnergyOptimizationResult(BaseModel):
    status: str
    objective_value: float | None
    solver_runtime_seconds: float
    periods: list[EnergyPeriodResult]
    costs: EnergyCostBreakdown
    total_unserved_mwh: float
    renewable_curtailment_mwh: float
    planning_mode: EnergyPlanningMode = EnergyPlanningMode.deterministic
    start_period: int = 0
    recommended_action: EnergyRecommendedAction | None = None
    scenario_performance: list[EnergyScenarioPerformance] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class EnergyOptimizationRun(BaseModel):
    id: str = Field(default_factory=uid)
    project_id: str
    status: str = "queued"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    input_snapshot: dict[str, Any]
    result: EnergyOptimizationResult | None = None
    error: str | None = None


class EnergySimulationRequest(BaseModel):
    """Configuration for a closed-loop comparison on one realized path."""

    policies: list[EnergyPlanningMode] = Field(
        default_factory=lambda: [EnergyPlanningMode.deterministic, EnergyPlanningMode.stochastic],
        min_length=1,
    )
    realized_scenario_id: str | None = None
    start_period: int = Field(default=0, ge=0)
    horizon_periods: int | None = Field(default=None, ge=1)
    current_energy_mwh: float | None = Field(default=None, ge=0)
    current_energy_mwh_by_storage: dict[str, float] | None = None
    lookahead_periods: int = Field(default=12, ge=1)
    commitment_periods: int = Field(default=1, ge=1)
    time_limit_seconds: int = Field(default=30, ge=1, le=3600)

    @model_validator(mode="after")
    def validate_policies(self):
        if len(set(self.policies)) != len(self.policies):
            raise ValueError("simulation policies must be unique")
        return self


class StorageSimulationStep(BaseModel):
    storage_id: str
    storage_name: str
    realized_inflow_mwh: float
    planned_charge_power_mw: float
    planned_discharge_power_mw: float
    applied_charge_power_mw: float
    applied_discharge_power_mw: float
    action_adjusted: bool
    stored_energy_start_mwh: float
    stored_energy_end_mwh: float
    spilled_inflow_mwh: float


class EnergySimulationStep(BaseModel):
    period: int
    solve_status: str
    solver_runtime_seconds: float
    realized_demand_mwh: float
    realized_renewable_mwh: float
    realized_import_price_per_mwh: float
    realized_export_price_per_mwh: float
    realized_inflow_mwh: float
    planned_charge_power_mw: float
    planned_discharge_power_mw: float
    applied_charge_power_mw: float
    applied_discharge_power_mw: float
    action_adjusted: bool
    stored_energy_start_mwh: float
    stored_energy_end_mwh: float
    spilled_inflow_mwh: float
    grid_import_mwh: float
    grid_export_mwh: float
    period_cost: float
    storage_steps: list[StorageSimulationStep] = Field(default_factory=list)


class EnergySimulationPolicyResult(BaseModel):
    planning_mode: EnergyPlanningMode
    status: str
    steps: list[EnergySimulationStep]
    costs: EnergyCostBreakdown
    total_grid_import_mwh: float
    total_grid_export_mwh: float
    total_charge_mwh: float
    total_discharge_mwh: float
    total_spilled_inflow_mwh: float
    final_energy_mwh: float
    final_energy_mwh_by_storage: dict[str, float] = Field(default_factory=dict)
    solver_runtime_seconds: float


class EnergySimulationResult(BaseModel):
    status: str
    realized_scenario_id: str
    realized_scenario_name: str
    start_period: int
    horizon_periods: int
    policy_results: list[EnergySimulationPolicyResult]
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class EnergySimulationRun(BaseModel):
    id: str = Field(default_factory=uid)
    project_id: str
    status: str = "queued"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    input_snapshot: dict[str, Any]
    result: EnergySimulationResult | None = None
    error: str | None = None

