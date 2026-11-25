from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, model_validator

from ...core.identifiers import uid


class TimeUnit(str, Enum):
    day = "day"
    week = "week"
    month = "month"


class PlanningMode(str, Enum):
    deterministic = "deterministic"
    expected = "expected"
    risk_aware = "risk_aware"
    high_protection = "high_protection"


class Location(BaseModel):
    id: str = Field(default_factory=uid)
    name: str = Field(min_length=1)
    description: str = ""


class CapacityOption(BaseModel):
    additional_capacity: float = Field(ge=0)
    activation_cost: float = Field(ge=0, default=0)
    variable_operating_cost: float = Field(ge=0, default=0)
    activation_lead_time: int = Field(ge=0, default=0)
    maximum_activated_capacity: float | None = Field(default=None, ge=0)
    minimum_activation_duration: int | None = Field(default=None, ge=1)
    fixed_cost: bool = False

    @model_validator(mode="after")
    def normalize_max(self):
        if self.maximum_activated_capacity is None:
            self.maximum_activated_capacity = self.additional_capacity
        if self.maximum_activated_capacity > self.additional_capacity:
            raise ValueError("maximum_activated_capacity cannot exceed additional_capacity")
        if self.minimum_activation_duration is not None:
            raise ValueError("minimum activation duration is not supported in deterministic v1")
        return self


class Resource(BaseModel):
    id: str = Field(default_factory=uid)
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    location_id: str
    capacity_unit: str
    minimum_capacity: float = Field(ge=0, default=0)
    maximum_capacity: float = Field(gt=0)
    operating_cost: float = Field(ge=0, default=0)
    availability: list[float]
    capacity_option: CapacityOption | None = None

    @model_validator(mode="after")
    def capacities_are_valid(self):
        if self.minimum_capacity > self.maximum_capacity:
            raise ValueError("minimum_capacity cannot exceed maximum_capacity")
        if any(v < 0 or v > self.maximum_capacity for v in self.availability):
            raise ValueError("availability must be between zero and maximum_capacity")
        return self


class Demand(BaseModel):
    id: str = Field(default_factory=uid)
    name: str = Field(min_length=1)
    location_id: str
    required_resource_type: str
    period: int = Field(ge=0)
    quantity: float = Field(ge=0)
    priority: int = Field(ge=1, le=5, default=3)
    shortage_penalty: float = Field(ge=0)


class Scenario(BaseModel):
    id: str = Field(default_factory=uid)
    name: str
    description: str = ""
    demand_multiplier: float = Field(gt=0, default=1)
    availability_multipliers: dict[str, list[float]] = Field(default_factory=dict)
    probability: float | None = Field(default=None, ge=0, le=1)


class ScenarioDuplicate(BaseModel):
    name: str = Field(min_length=1)


class PlanComparison(BaseModel):
    baseline_run_id: str
    candidate_run_id: str
    total_cost_change: float
    total_cost_change_percent: float | None
    service_rate_change: float
    unmet_demand_change: float
    activated_capacity_change: float


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    planning_start_date: date
    time_unit: TimeUnit
    number_of_periods: int = Field(ge=1, le=520)
    currency: str = Field(min_length=3, max_length=3, default="USD")
    default_capacity_unit: str = Field(min_length=1)
    locations: list[Location]
    resources: list[Resource]
    demands: list[Demand]
    scenarios: list[Scenario] = Field(default_factory=list)
    budget: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_references(self):
        location_ids = {x.id for x in self.locations}
        if len(location_ids) != len(self.locations):
            raise ValueError("location IDs must be unique")
        resource_ids = {x.id for x in self.resources}
        if len(resource_ids) != len(self.resources):
            raise ValueError("resource IDs must be unique")
        if any(r.location_id not in location_ids for r in self.resources):
            raise ValueError("resource references an unknown location")
        if any(len(r.availability) != self.number_of_periods for r in self.resources):
            raise ValueError("each availability series must match number_of_periods")
        if any(d.location_id not in location_ids for d in self.demands):
            raise ValueError("demand references an unknown location")
        if any(d.period >= self.number_of_periods for d in self.demands):
            raise ValueError("demand period is outside the planning horizon")
        scenario_ids = {x.id for x in self.scenarios}
        if len(scenario_ids) != len(self.scenarios):
            raise ValueError("scenario IDs must be unique")
        for s in self.scenarios:
            for rid, values in s.availability_multipliers.items():
                if rid not in resource_ids or len(values) != self.number_of_periods or any(v < 0 for v in values):
                    raise ValueError("scenario availability adjustment is invalid")
        return self


class Project(ProjectCreate):
    id: str = Field(default_factory=uid)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OptimizationRequest(BaseModel):
    scenario_id: str | None = None
    mode: PlanningMode = PlanningMode.deterministic
    time_limit_seconds: int = Field(default=60, ge=1, le=3600)


class AllocationResult(BaseModel):
    resource_id: str
    demand_id: str
    period: int
    quantity: float
    unit_cost: float


class CapacityResult(BaseModel):
    resource_id: str
    period: int
    base_capacity: float
    activated_capacity: float
    utilization: float


class DemandResult(BaseModel):
    demand_id: str
    period: int
    required: float
    allocated: float
    unmet: float


class CostBreakdown(BaseModel):
    operating: float
    allocation: float
    expansion: float
    shortage: float
    total: float


class ScenarioPerformance(BaseModel):
    scenario_id: str
    scenario_name: str
    probability: float
    total_cost: float
    service_rate: float
    unmet_demand: float


class OptimizationResult(BaseModel):
    status: str
    objective_value: float | None
    solver_runtime_seconds: float
    allocations: list[AllocationResult]
    capacities: list[CapacityResult]
    demands: list[DemandResult]
    costs: CostBreakdown
    service_rate: float
    recommendations: list[str]
    scenario_performance: list[ScenarioPerformance] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class OptimizationRun(BaseModel):
    id: str = Field(default_factory=uid)
    project_id: str
    scenario_id: str | None = None
    mode: PlanningMode
    status: str = "queued"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    input_snapshot: dict[str, Any]
    result: OptimizationResult | None = None
    error: str | None = None

