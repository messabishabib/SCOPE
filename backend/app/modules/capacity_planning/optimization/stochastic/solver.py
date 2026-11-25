from __future__ import annotations

"""Scenario-based capacity planning with shared capacity commitments."""

import time
from collections import defaultdict

from pyomo.environ import Binary, ConcreteModel, Constraint, ConstraintList, NonNegativeReals, Objective, Set, SolverFactory, Var, minimize, value
from pyomo.opt import TerminationCondition

from ...schemas import AllocationResult, CapacityResult, CostBreakdown, DemandResult, OptimizationResult, PlanningMode, Project, Scenario, ScenarioPerformance


def solve_uncertainty(project: Project, mode: PlanningMode, time_limit_seconds: int = 60) -> OptimizationResult:
    if mode == PlanningMode.deterministic:
        raise ValueError("Use the deterministic solver for deterministic runs")
    started = time.perf_counter()
    scenarios = project.scenarios or [Scenario(id="baseline", name="Baseline")]
    if len(scenarios) < 2:
        raise ValueError("Uncertainty planning requires at least two configured scenarios")
    raw = [s.probability for s in scenarios]
    weights = raw if all(x is not None for x in raw) and sum(raw) > 0 else [1 / len(scenarios)] * len(scenarios)
    total_weight = sum(weights)
    probabilities = {s.id: float(weights[i] / total_weight) for i, s in enumerate(scenarios)}
    scenario_map, resources, demands = {s.id: s for s in scenarios}, {r.id: r for r in project.resources}, {d.id: d for d in project.demands}
    periods, compatible = list(range(project.number_of_periods)), [(r.id, d.id) for r in project.resources for d in project.demands if r.type == d.required_resource_type]

    m = ConcreteModel()
    m.S, m.R, m.D, m.T = Set(initialize=list(scenario_map)), Set(initialize=list(resources)), Set(initialize=list(demands)), Set(initialize=periods)
    m.PAIRS = Set(dimen=2, initialize=compatible)
    m.allocate = Var(m.S, m.PAIRS, m.T, domain=NonNegativeReals)
    m.unmet = Var(m.S, m.D, m.T, domain=NonNegativeReals)
    m.expand = Var(m.R, m.T, domain=NonNegativeReals)
    fixed = [r.id for r in project.resources if r.capacity_option and r.capacity_option.fixed_cost]
    m.FIXED_R = Set(initialize=fixed)
    m.is_active = Var(m.FIXED_R, m.T, domain=Binary)

    def adjusted_capacity(sid, rid, t):
        scenario = scenario_map[sid]
        multipliers = scenario.availability_multipliers.get(rid, [1.0] * project.number_of_periods)
        return resources[rid].availability[t] * multipliers[t]

    def balance(model, s, d, t):
        demand = demands[d]
        required = demand.quantity * scenario_map[s].demand_multiplier if demand.period == t else 0
        return sum(model.allocate[s, r, d, t] for r in resources if (r, d) in compatible) + model.unmet[s, d, t] == required
    m.balance = Constraint(m.S, m.D, m.T, rule=balance)

    def capacity(model, s, r, t):
        return sum(model.allocate[s, r, d, t] for d in demands if (r, d) in compatible) <= adjusted_capacity(s, r, t) + model.expand[r, t]
    m.capacity = Constraint(m.S, m.R, m.T, rule=capacity)

    def expansion(model, r, t):
        option = resources[r].capacity_option
        if not option or t < option.activation_lead_time:
            return model.expand[r, t] == 0
        maximum = option.maximum_activated_capacity or 0
        return model.expand[r, t] <= (maximum * model.is_active[r, t] if option.fixed_cost else maximum)
    m.expansion = Constraint(m.R, m.T, rule=expansion)

    expansion_cost = sum(m.expand[r, t] * (resources[r].capacity_option.variable_operating_cost if resources[r].capacity_option else 0) for r in resources for t in periods) + sum(m.is_active[r, t] * resources[r].capacity_option.activation_cost for r in fixed for t in periods)
    if project.budget is not None:
        m.budget = Constraint(expr=expansion_cost <= project.budget)

    def recourse(s):
        operating = sum(m.allocate[s, r, d, t] * resources[r].operating_cost for r, d in compatible for t in periods)
        allocation = sum(m.allocate[s, r, d, t] * (0 if resources[r].location_id == demands[d].location_id else 1) for r, d in compatible for t in periods)
        shortage = sum(m.unmet[s, d, t] * demands[d].shortage_penalty for d in demands for t in periods)
        return operating + allocation + shortage
    expected_recourse = sum(probabilities[s] * recourse(s) for s in scenario_map)
    m.worst_recourse = Var(domain=NonNegativeReals)
    m.worst_bounds = ConstraintList()
    for s in scenario_map:
        m.worst_bounds.add(m.worst_recourse >= recourse(s))
    objective = expansion_cost + (expected_recourse if mode == PlanningMode.expected else .65 * expected_recourse + .35 * m.worst_recourse if mode == PlanningMode.risk_aware else m.worst_recourse)
    m.objective = Objective(expr=objective, sense=minimize)

    optimizer = SolverFactory("appsi_highs")
    if not optimizer.available(exception_flag=False):
        raise RuntimeError("HiGHS is unavailable. Install backend requirements, including highspy.")
    optimizer.config.time_limit = time_limit_seconds
    outcome = optimizer.solve(m)
    termination = outcome.solver.termination_condition
    status = {TerminationCondition.optimal:"optimal",TerminationCondition.feasible:"feasible",TerminationCondition.infeasible:"infeasible",TerminationCondition.unbounded:"unbounded",TerminationCondition.maxTimeLimit:"time_limit"}.get(termination,"error")
    empty_cost = CostBreakdown(operating=0, allocation=0, expansion=0, shortage=0, total=0)
    if status in {"infeasible", "unbounded", "error"}:
        return OptimizationResult(status=status, objective_value=None, solver_runtime_seconds=time.perf_counter()-started, allocations=[], capacities=[], demands=[], costs=empty_cost, service_rate=0, recommendations=[], diagnostics={"termination_condition":str(termination)})

    expansion_value, recommendations = 0.0, []
    for r in resources:
        for t in periods:
            qty=value(m.expand[r,t]) or 0
            option=resources[r].capacity_option
            expansion_value += qty*(option.variable_operating_cost if option else 0)
            if option and option.fixed_cost: expansion_value += (value(m.is_active[r,t]) or 0)*option.activation_cost
            if qty>1e-7: recommendations.append(f"Commit {qty:.1f} additional {resources[r].capacity_unit} at {resources[r].name} in period {t+1} before demand is known.")

    expected_alloc, expected_demand, expected_resource = defaultdict(float), defaultdict(float), defaultdict(float)
    operating=allocation_cost=shortage_cost=total_required=total_unmet=0.0
    performances=[]
    for sid,s in scenario_map.items():
        p=probabilities[sid]; s_required=s_unmet=s_operating=s_allocation=s_shortage=0.0
        for d in demands.values():
            required=d.quantity*s.demand_multiplier
            unmet=value(m.unmet[sid,d.id,d.period]) or 0
            expected_demand[d.id,d.period]+=p*required; total_required+=p*required; total_unmet+=p*unmet; s_required+=required; s_unmet+=unmet; s_shortage+=unmet*d.shortage_penalty
        for r,d in compatible:
            for t in periods:
                qty=value(m.allocate[sid,r,d,t]) or 0
                expected_alloc[r,d,t]+=p*qty; expected_resource[r,t]+=p*qty
                s_operating+=qty*resources[r].operating_cost; s_allocation+=qty*(0 if resources[r].location_id==demands[d].location_id else 1)
        operating+=p*s_operating; allocation_cost+=p*s_allocation; shortage_cost+=p*s_shortage
        performances.append(ScenarioPerformance(scenario_id=sid,scenario_name=s.name,probability=p,total_cost=expansion_value+s_operating+s_allocation+s_shortage,service_rate=(1-s_unmet/s_required) if s_required else 1,unmet_demand=s_unmet))
    allocations=[AllocationResult(resource_id=r,demand_id=d,period=t,quantity=q,unit_cost=resources[r].operating_cost+(0 if resources[r].location_id==demands[d].location_id else 1)) for (r,d,t),q in expected_alloc.items() if q>1e-7]
    demand_results=[DemandResult(demand_id=d.id,period=t,required=expected_demand[d.id,t],allocated=expected_demand[d.id,t]-sum(probabilities[sid]*(value(m.unmet[sid,d.id,t]) or 0) for sid in scenario_map),unmet=sum(probabilities[sid]*(value(m.unmet[sid,d.id,t]) or 0) for sid in scenario_map)) for d in demands.values() for t in periods]
    capacities=[]
    for r in resources:
        for t in periods:
            expected_base=sum(probabilities[sid]*adjusted_capacity(sid,r,t) for sid in scenario_map); expanded=value(m.expand[r,t]) or 0; total=expected_base+expanded
            capacities.append(CapacityResult(resource_id=r,period=t,base_capacity=expected_base,activated_capacity=expanded,utilization=expected_resource[r,t]/total if total else 0))
    total=expansion_value+operating+allocation_cost+shortage_cost
    return OptimizationResult(status=status,objective_value=value(m.objective),solver_runtime_seconds=time.perf_counter()-started,allocations=allocations,capacities=capacities,demands=demand_results,costs=CostBreakdown(operating=operating,allocation=allocation_cost,expansion=expansion_value,shortage=shortage_cost,total=total),service_rate=(1-total_unmet/total_required) if total_required else 1,recommendations=recommendations,scenario_performance=performances,diagnostics={"termination_condition":str(termination),"nonanticipativity":"shared first-stage capacity commitments","objective_basis":mode.value,"probabilities_normalized":probabilities})
