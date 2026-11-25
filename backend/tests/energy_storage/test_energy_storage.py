"""Energy dispatch, uncertainty, rolling-horizon, and simulation tests."""

from time import sleep

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.energy_storage.optimization.solve import solve
from app.modules.energy_storage.optimization.stochastic.solve import solve as solve_stochastic
from app.modules.energy_storage.schemas import EnergyOptimizationRequest, EnergyPlanningMode, EnergyProject, EnergyScenario, EnergySimulationRequest, StorageAsset
from app.modules.energy_storage.services.runs import prepare_rolling_project
from app.modules.energy_storage.services.simulation import simulate


def project(prices=(10, 100), demand=(10, 10), initial=0, terminal=0, efficiency=1):
    return EnergyProject(name="test storage", number_of_periods=2, interval_hours=1, currency="EUR",
        storage=StorageAsset(name="store", energy_capacity_mwh=10, initial_energy_mwh=initial,
            terminal_energy_minimum_mwh=terminal, maximum_charge_power_mw=10, maximum_discharge_power_mw=10,
            charge_efficiency=efficiency, discharge_efficiency=efficiency),
        demand_mwh=list(demand), renewable_generation_mwh=[0, 0], grid_import_price_per_mwh=list(prices),
        grid_export_price_per_mwh=[0, 0], shortage_penalty_per_mwh=10000)


def test_storage_shifts_grid_energy_to_low_price_period():
    result = solve(project())
    assert result.status == "optimal"
    assert result.periods[0].charge_power_mw == pytest.approx(10)
    assert result.periods[1].discharge_power_mw == pytest.approx(10)
    assert result.periods[0].grid_import_mwh == pytest.approx(20)
    assert result.periods[1].grid_import_mwh == pytest.approx(0)
    assert result.costs.total == pytest.approx(200)
    assert result.diagnostics["solution_validated"] is True


def test_terminal_requirement_prevents_end_horizon_depletion():
    result = solve(project(prices=(100, 100), demand=(5, 5), initial=5, terminal=5))
    assert sum(x.discharge_power_mw for x in result.periods) == pytest.approx(0)
    assert result.periods[-1].stored_energy_end_mwh >= 5


def test_charge_and_discharge_are_mutually_exclusive():
    result = solve(project())
    assert all(min(x.charge_power_mw, x.discharge_power_mw) == pytest.approx(0) for x in result.periods)


def test_grid_import_capacity_creates_unserved_energy_and_scales_with_interval_duration():
    source = project(prices=(100, 100), demand=(10, 10))
    source.interval_hours = 0.5
    source.grid_import_capacity_mw = 8

    result = solve(source)

    assert result.status == "optimal"
    assert all(period.grid_import_mwh <= 4 + 1e-6 for period in result.periods)
    assert result.total_unserved_mwh == pytest.approx(12)
    assert result.costs.shortage == pytest.approx(120000)
    assert result.diagnostics["maximum_grid_import_limit_violation_mwh"] <= 1e-6
    assert result.diagnostics["solution_validated"] is True


def test_grid_export_capacity_forces_renewable_curtailment():
    source = project(prices=(10, 10), demand=(0, 0), initial=10, terminal=10)
    source.renewable_generation_mwh = [10, 0]
    source.grid_export_price_per_mwh = [5, 0]
    source.grid_export_capacity_mw = 3

    result = solve(source)

    assert result.periods[0].grid_export_mwh == pytest.approx(3)
    assert result.periods[0].renewable_curtailment_mwh == pytest.approx(7)
    assert result.diagnostics["maximum_grid_export_limit_violation_mwh"] <= 1e-6
    assert result.diagnostics["solution_validated"] is True


def test_multiple_storage_units_have_independent_dispatch_and_states():
    source = project(prices=(10, 100), demand=(20, 20))
    source.storages.append(StorageAsset(
        id="fast-battery", name="Fast battery", energy_capacity_mwh=6, initial_energy_mwh=0,
        terminal_energy_minimum_mwh=0, maximum_charge_power_mw=6, maximum_discharge_power_mw=6,
        charge_efficiency=1, discharge_efficiency=1,
    ))
    result = solve(source)
    assert result.status == "optimal"
    assert result.diagnostics["storage_count"] == 2
    assert all(len(period.storage_dispatches) == 2 for period in result.periods)
    for period in result.periods:
        assert period.charge_power_mw == pytest.approx(sum(asset.charge_power_mw for asset in period.storage_dispatches))
        assert period.discharge_power_mw == pytest.approx(sum(asset.discharge_power_mw for asset in period.storage_dispatches))
        assert period.stored_energy_end_mwh == pytest.approx(sum(asset.stored_energy_end_mwh for asset in period.storage_dispatches))
    assert {asset.storage_id for asset in result.periods[0].storage_dispatches} == {source.storages[0].id, "fast-battery"}


def test_legacy_single_storage_payload_is_migrated_to_portfolio_contract():
    payload = project().model_dump(mode="json")
    first = payload["storages"][0]
    payload.pop("storages")
    payload["storage"] = first
    migrated = EnergyProject.model_validate(payload)
    assert len(migrated.storages) == 1
    assert migrated.storage.id == first["id"]
    assert "storages" in migrated.model_dump(mode="json")


def test_energy_api_runs_real_demo_model():
    with TestClient(app) as client:
        projects = client.get("/api/energy/projects")
        assert projects.status_code == 200
        project_id = projects.json()[0]["id"]
        response = client.post(f"/api/energy/projects/{project_id}/runs", json={"time_limit_seconds": 20})
        assert response.status_code == 202
        run_id = response.json()["id"]
        for _ in range(100):
            run = client.get(f"/api/energy/runs/{run_id}").json()
            if run["status"] not in {"queued", "running"}:
                break
            sleep(.05)
        assert run["status"] == "optimal"
        assert run["result"]["diagnostics"]["solution_validated"] is True
        assert len(run["result"]["periods"]) == 24


def stochastic_project():
    base = project(prices=(10, 100), demand=(10, 10))
    base.scenarios = [
        EnergyScenario(id="normal", name="Normal", probability=.7, demand_multiplier=[1,1], renewable_multiplier=[1,1], price_multiplier=[1,1], natural_inflow_mwh=[0,0]),
        EnergyScenario(id="peak", name="Peak", probability=.3, demand_multiplier=[1,1.5], renewable_multiplier=[1,1], price_multiplier=[1,1.2], natural_inflow_mwh=[0,0]),
    ]
    return base


def spill_project():
    source = EnergyProject(
        name="spill test",
        number_of_periods=1,
        interval_hours=1,
        currency="EUR",
        storage=StorageAsset(
            id="reservoir",
            name="Reservoir",
            energy_capacity_mwh=10,
            initial_energy_mwh=10,
            terminal_energy_minimum_mwh=0,
            maximum_charge_power_mw=10,
            maximum_discharge_power_mw=10,
            charge_efficiency=1,
            discharge_efficiency=1,
            variable_discharge_cost_per_mwh=10,
        ),
        demand_mwh=[0],
        renewable_generation_mwh=[0],
        grid_import_price_per_mwh=[0],
        grid_export_price_per_mwh=[0],
        shortage_penalty_per_mwh=10000,
        spill_penalty_per_mwh=1,
        scenarios=[
            EnergyScenario(id="dry", name="Dry", probability=.5, demand_multiplier=[1], renewable_multiplier=[1], price_multiplier=[1], natural_inflow_mwh=[0]),
            EnergyScenario(id="wet", name="Wet", probability=.5, demand_multiplier=[1], renewable_multiplier=[1], price_multiplier=[1], natural_inflow_mwh=[5]),
        ],
    )
    return source


def test_stochastic_model_shares_immediate_physical_decision():
    result = solve_stochastic(stochastic_project(), commitment_periods=1)
    assert result.status == "optimal"
    assert len(result.scenario_performance) == 2
    assert result.recommended_action is not None
    assert result.diagnostics["maximum_nonanticipativity_residual"] <= 1e-6
    assert result.diagnostics["solution_validated"] is True


def test_stochastic_model_enforces_grid_capacity_in_every_scenario():
    source = stochastic_project()
    source.grid_import_capacity_mw = 5

    result = solve_stochastic(source, commitment_periods=1)

    assert result.status == "optimal"
    assert all(period.grid_import_mwh <= 5 + 1e-6 for period in result.periods)
    assert result.total_unserved_mwh > 0
    assert result.diagnostics["maximum_grid_import_limit_violation_mwh"] <= 1e-6
    assert result.diagnostics["solution_validated"] is True


def test_stochastic_portfolio_supports_asset_specific_inflows_and_commitments():
    source = stochastic_project()
    source.storages.append(StorageAsset(
        id="river-store", name="River store", energy_capacity_mwh=8, initial_energy_mwh=0,
        terminal_energy_minimum_mwh=0, maximum_charge_power_mw=4, maximum_discharge_power_mw=4,
        charge_efficiency=1, discharge_efficiency=1,
    ))
    source.scenarios[0].natural_inflow_mwh_by_storage = {"river-store": [0, 4]}
    source.scenarios[1].natural_inflow_mwh_by_storage = {"river-store": [0, 2]}
    result = solve_stochastic(source, commitment_periods=1)
    assert result.status == "optimal"
    assert result.diagnostics["storage_count"] == 2
    assert result.diagnostics["maximum_nonanticipativity_residual"] <= 1e-6
    assert len(result.recommended_action.storage_actions) == 2
    assert all(set(performance.terminal_energy_mwh_by_storage) == {storage.id for storage in source.storages} for performance in result.scenario_performance)


def test_stochastic_spill_is_bounded_costed_and_reported_by_scenario_and_storage():
    result = solve_stochastic(spill_project(), commitment_periods=1)

    assert result.status == "optimal"
    assert result.total_spilled_inflow_mwh == pytest.approx(2.5)
    assert result.periods[0].spilled_inflow_mwh == pytest.approx(2.5)
    assert result.periods[0].storage_dispatches[0].spilled_inflow_mwh == pytest.approx(2.5)
    performance = {item.scenario_id: item for item in result.scenario_performance}
    assert performance["dry"].total_spilled_inflow_mwh == pytest.approx(0)
    assert performance["wet"].total_spilled_inflow_mwh == pytest.approx(5)
    assert performance["wet"].spilled_inflow_mwh_by_storage == pytest.approx({"reservoir": 5})
    assert result.costs.spillage == pytest.approx(2.5)
    assert result.costs.total == pytest.approx(2.5)
    assert result.objective_value == pytest.approx(result.costs.total)
    assert result.diagnostics["maximum_spill_limit_violation_mwh"] <= 1e-6
    assert result.diagnostics["solution_validated"] is True


def test_rolling_horizon_updates_each_storage_state():
    source = stochastic_project()
    source.storages.append(StorageAsset(
        id="second", name="Second", energy_capacity_mwh=12, initial_energy_mwh=3,
        terminal_energy_minimum_mwh=0, maximum_charge_power_mw=4, maximum_discharge_power_mw=4,
        charge_efficiency=1, discharge_efficiency=1,
    ))
    rolling = prepare_rolling_project(source, EnergyOptimizationRequest(
        current_period=0, lookahead_periods=1,
        current_energy_mwh_by_storage={source.storages[0].id: 4, "second": 7},
    ))
    assert {storage.id: storage.initial_energy_mwh for storage in rolling.storages} == {source.storages[0].id: 4, "second": 7}


def test_rolling_horizon_slices_forecasts_and_updates_state():
    source = stochastic_project()
    rolling = prepare_rolling_project(source, EnergyOptimizationRequest(mode=EnergyPlanningMode.stochastic, current_period=1, current_energy_mwh=6, lookahead_periods=1))
    assert rolling.number_of_periods == 1
    assert rolling.storage.initial_energy_mwh == 6
    assert rolling.demand_mwh == [10]
    assert rolling.scenarios[1].demand_multiplier == [1.5]


def test_stochastic_energy_api_returns_scenario_performance():
    with TestClient(app) as client:
        project_id = client.get("/api/energy/projects").json()[0]["id"]
        response = client.post(f"/api/energy/projects/{project_id}/runs", json={"mode":"stochastic","current_period":0,"lookahead_periods":12,"commitment_periods":1})
        assert response.status_code == 202
        run_id = response.json()["id"]
        for _ in range(120):
            run = client.get(f"/api/energy/runs/{run_id}").json()
            if run["status"] not in {"queued","running"}: break
            sleep(.05)
        assert run["status"] == "optimal"
        assert len(run["result"]["scenario_performance"]) >= 2
        assert run["result"]["recommended_action"]["period"] == 0


def test_simulation_reoptimizes_and_updates_state_on_the_same_realized_path():
    source = stochastic_project()
    source.storages.append(StorageAsset(
        id="simulation-battery", name="Simulation battery", energy_capacity_mwh=5, initial_energy_mwh=2,
        terminal_energy_minimum_mwh=0, maximum_charge_power_mw=2, maximum_discharge_power_mw=2,
        charge_efficiency=1, discharge_efficiency=1,
    ))
    result = simulate(source, EnergySimulationRequest(
        policies=[EnergyPlanningMode.deterministic, EnergyPlanningMode.stochastic],
        realized_scenario_id="peak",
        horizon_periods=2,
        lookahead_periods=2,
    ))

    assert result.status == "optimal"
    assert len(result.policy_results) == 2
    deterministic, stochastic = result.policy_results
    assert len(deterministic.steps) == len(stochastic.steps) == 2
    assert [step.realized_demand_mwh for step in deterministic.steps] == [step.realized_demand_mwh for step in stochastic.steps]
    assert deterministic.steps[1].stored_energy_start_mwh == pytest.approx(deterministic.steps[0].stored_energy_end_mwh)
    assert stochastic.steps[1].stored_energy_start_mwh == pytest.approx(stochastic.steps[0].stored_energy_end_mwh)
    assert all(len(step.storage_steps) == 2 for policy in result.policy_results for step in policy.steps)
    for policy in result.policy_results:
        previous = {asset.storage_id: asset.stored_energy_end_mwh for asset in policy.steps[0].storage_steps}
        current = {asset.storage_id: asset.stored_energy_start_mwh for asset in policy.steps[1].storage_steps}
        assert current == pytest.approx(previous)
    assert deterministic.costs.total == pytest.approx(sum(step.period_cost for step in deterministic.steps))
    assert result.diagnostics["same_realized_path_for_all_policies"] is True


def test_simulation_charges_realized_spill_consistently_with_the_optimizer():
    source = spill_project()
    result = simulate(source, EnergySimulationRequest(
        policies=[EnergyPlanningMode.deterministic, EnergyPlanningMode.stochastic],
        realized_scenario_id="wet",
        horizon_periods=1,
        lookahead_periods=1,
    ))

    for policy in result.policy_results:
        assert policy.total_spilled_inflow_mwh == pytest.approx(5)
        assert policy.steps[0].spilled_inflow_mwh == pytest.approx(5)
        assert policy.costs.spillage == pytest.approx(5)
        assert policy.costs.total == pytest.approx(5)
        assert policy.steps[0].period_cost == pytest.approx(5)


def test_simulation_enforces_grid_outage_and_prices_unserved_energy():
    source = stochastic_project()
    source.grid_import_capacity_mw = 0
    source.storages[0].initial_energy_mwh = 0

    result = simulate(source, EnergySimulationRequest(
        policies=[EnergyPlanningMode.deterministic],
        realized_scenario_id="normal",
        horizon_periods=1,
        lookahead_periods=1,
    ))

    policy = result.policy_results[0]
    step = policy.steps[0]
    assert step.grid_import_mwh == pytest.approx(0)
    assert step.unserved_energy_mwh == pytest.approx(10)
    assert policy.total_unserved_mwh == pytest.approx(10)
    assert policy.costs.shortage == pytest.approx(100000)
    assert policy.costs.total == pytest.approx(step.period_cost)


def test_simulation_clips_discharge_when_realized_surplus_cannot_be_exported():
    source = project(prices=(100, 100), demand=(10, 10), initial=10)
    source.grid_export_capacity_mw = 0
    source.scenarios = [EnergyScenario(
        id="zero-demand",
        name="Zero realized demand",
        probability=1,
        demand_multiplier=[0, 1],
        renewable_multiplier=[1, 1],
        price_multiplier=[1, 1],
        natural_inflow_mwh=[0, 0],
    )]

    result = simulate(source, EnergySimulationRequest(
        policies=[EnergyPlanningMode.deterministic],
        realized_scenario_id="zero-demand",
        horizon_periods=1,
        lookahead_periods=1,
    ))

    step = result.policy_results[0].steps[0]
    assert step.planned_discharge_power_mw == pytest.approx(10)
    assert step.applied_discharge_power_mw == pytest.approx(0)
    assert step.grid_export_mwh == pytest.approx(0)
    assert step.stored_energy_end_mwh == pytest.approx(10)
    assert step.action_adjusted is True


def test_energy_simulation_api_runs_in_background():
    with TestClient(app) as client:
        project_id = client.get("/api/energy/projects").json()[0]["id"]
        response = client.post(f"/api/energy/projects/{project_id}/simulations", json={
            "policies": ["deterministic", "stochastic"],
            "realized_scenario_id": "evening-stress",
            "horizon_periods": 2,
            "lookahead_periods": 2,
        })
        assert response.status_code == 202
        run_id = response.json()["id"]
        for _ in range(160):
            run = client.get(f"/api/energy/simulations/{run_id}").json()
            if run["status"] not in {"queued", "running"}:
                break
            sleep(.05)
        assert run["status"] == "optimal"
        assert len(run["result"]["policy_results"]) == 2
        assert all(len(policy["steps"]) == 2 for policy in run["result"]["policy_results"])
