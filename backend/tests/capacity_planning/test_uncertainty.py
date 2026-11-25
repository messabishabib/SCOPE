from datetime import date

"""Scenario-based capacity-planning model tests."""

import pytest

from app.modules.capacity_planning.optimization.stochastic.solver import solve_uncertainty
from app.modules.capacity_planning.schemas import CapacityOption, Demand, Location, PlanningMode, Project, Resource, Scenario


def uncertain_project():
    return Project(name="uncertain", planning_start_date=date.today(), time_unit="week", number_of_periods=1, currency="EUR", default_capacity_unit="units",
        locations=[Location(id="site", name="Site")],
        resources=[Resource(id="line", name="Line", type="machine", location_id="site", capacity_unit="units", maximum_capacity=15, availability=[5], capacity_option=CapacityOption(additional_capacity=5, maximum_activated_capacity=5, variable_operating_cost=20))],
        demands=[Demand(id="orders", name="Orders", location_id="site", required_resource_type="machine", period=0, quantity=5, shortage_penalty=100)],
        scenarios=[Scenario(id="base", name="Base", probability=.9), Scenario(id="peak", name="Peak", demand_multiplier=2, probability=.1)])


def test_expected_plan_uses_probabilities_and_shared_commitment():
    result = solve_uncertainty(uncertain_project(), PlanningMode.expected)
    assert result.status == "optimal"
    assert result.capacities[0].activated_capacity == pytest.approx(0)
    assert len(result.scenario_performance) == 2
    assert result.scenario_performance[1].unmet_demand == pytest.approx(5)
    assert result.diagnostics["nonanticipativity"] == "shared first-stage capacity commitments"


def test_high_protection_covers_worst_case_with_one_commitment():
    result = solve_uncertainty(uncertain_project(), PlanningMode.high_protection)
    assert result.status == "optimal"
    assert result.capacities[0].activated_capacity == pytest.approx(5)
    assert all(row.unmet_demand == pytest.approx(0) for row in result.scenario_performance)
    assert result.costs.expansion == pytest.approx(100)


def test_uncertainty_requires_multiple_scenarios():
    project = uncertain_project()
    project.scenarios = project.scenarios[:1]
    with pytest.raises(ValueError, match="at least two"):
        solve_uncertainty(project, PlanningMode.expected)
