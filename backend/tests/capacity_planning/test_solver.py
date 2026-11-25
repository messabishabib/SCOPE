from datetime import date

"""Deterministic capacity-planning model tests."""

import pytest

from app.modules.capacity_planning.optimization.deterministic.solver import solve
from app.modules.capacity_planning.schemas import CapacityOption, Demand, Location, Project, Resource, Scenario


def project(capacity=10, demand=8, resource_type="machine", demand_type="machine", option=None, periods=1):
    return Project(name="test", planning_start_date=date.today(), time_unit="week", number_of_periods=periods, currency="EUR", default_capacity_unit="units",
        locations=[Location(id="loc", name="Site")],
        resources=[Resource(id="r", name="Line", type=resource_type, location_id="loc", capacity_unit="units", maximum_capacity=20, operating_cost=2, availability=[capacity]*periods, capacity_option=option)],
        demands=[Demand(id=f"d{i}", name="Orders", location_id="loc", required_resource_type=demand_type, period=i, quantity=demand, shortage_penalty=100) for i in range(periods)])


def test_balanced_solution_and_objective():
    result=solve(project(), None)
    assert result.status == "optimal"
    assert result.service_rate == pytest.approx(1)
    assert sum(x.quantity for x in result.allocations) == pytest.approx(8)
    assert result.costs.total == pytest.approx(16)
    assert result.diagnostics["solution_validated"] is True


def test_capacity_shortage_is_reported():
    result=solve(project(capacity=5, demand=8), None)
    assert result.demands[0].unmet == pytest.approx(3)
    assert result.costs.shortage == pytest.approx(300)
    assert result.service_rate == pytest.approx(5/8)


def test_incompatible_resource_cannot_allocate():
    result=solve(project(resource_type="press", demand_type="pack"), None)
    assert not result.allocations
    assert result.demands[0].unmet == pytest.approx(8)


def test_expansion_is_used_when_economic():
    option=CapacityOption(additional_capacity=5, maximum_activated_capacity=5, variable_operating_cost=3)
    result=solve(project(capacity=5, demand=8, option=option), None)
    assert result.capacities[0].activated_capacity == pytest.approx(3)
    assert result.costs.expansion == pytest.approx(9)
    assert result.service_rate == pytest.approx(1)


def test_lead_time_blocks_first_period_expansion():
    option=CapacityOption(additional_capacity=5, maximum_activated_capacity=5, variable_operating_cost=3, activation_lead_time=1)
    result=solve(project(capacity=5, demand=8, option=option, periods=2), None)
    assert result.capacities[0].activated_capacity == 0
    assert result.capacities[1].activated_capacity == pytest.approx(3)
    assert result.demands[0].unmet == pytest.approx(3)


def test_scenario_changes_demand():
    result=solve(project(capacity=10, demand=8), Scenario(name="up", demand_multiplier=1.25))
    assert result.demands[0].required == pytest.approx(10)
    assert result.service_rate == pytest.approx(1)


def test_zero_demand_service_rate_is_complete():
    result=solve(project(capacity=10, demand=0), None)
    assert result.service_rate == 1
    assert result.costs.total == 0

