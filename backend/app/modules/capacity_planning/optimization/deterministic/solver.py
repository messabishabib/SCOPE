from __future__ import annotations

"""Readable deterministic allocation and capacity-activation model."""

import time
from collections import defaultdict

from pyomo.environ import Binary, ConcreteModel, Constraint, NonNegativeReals, Objective, Set, SolverFactory, Var, minimize, value
from pyomo.opt import SolverStatus, TerminationCondition

from ...schemas import AllocationResult, CapacityResult, CostBreakdown, DemandResult, OptimizationResult, Project, Scenario


def solve(project: Project, scenario: Scenario | None, time_limit_seconds: int = 60) -> OptimizationResult:
    started = time.perf_counter()
    demand_multiplier = scenario.demand_multiplier if scenario else 1.0
    resources = {r.id: r for r in project.resources}
    demands = {d.id: d for d in project.demands}
    periods = list(range(project.number_of_periods))
    availability = {}
    for r in project.resources:
        multipliers = scenario.availability_multipliers.get(r.id, [1.0] * project.number_of_periods) if scenario else [1.0] * project.number_of_periods
        for t in periods:
            availability[r.id, t] = r.availability[t] * multipliers[t]

    compatible = [(r.id, d.id) for r in project.resources for d in project.demands if r.type == d.required_resource_type]
    demand_qty = {(d.id, d.period): d.quantity * demand_multiplier for d in project.demands}
    m = ConcreteModel()
    m.R = Set(initialize=list(resources))
    m.D = Set(initialize=list(demands))
    m.T = Set(initialize=periods)
    m.PAIRS = Set(dimen=2, initialize=compatible)
    m.allocate = Var(m.PAIRS, m.T, domain=NonNegativeReals)
    m.unmet = Var(m.D, m.T, domain=NonNegativeReals)
    m.expand = Var(m.R, m.T, domain=NonNegativeReals)
    fixed_resources = [r.id for r in project.resources if r.capacity_option and r.capacity_option.fixed_cost]
    m.FIXED_R = Set(initialize=fixed_resources)
    m.is_active = Var(m.FIXED_R, m.T, domain=Binary)

    def demand_balance(model, d, t):
        qty = demand_qty.get((d, t), 0)
        incoming = sum(model.allocate[r, d, t] for r in resources if (r, d) in compatible)
        return incoming + model.unmet[d, t] == qty
    m.demand_balance = Constraint(m.D, m.T, rule=demand_balance)

    def capacity_limit(model, r, t):
        used = sum(model.allocate[r, d, t] for d in demands if (r, d) in compatible)
        return used <= availability[r, t] + model.expand[r, t]
    m.capacity_limit = Constraint(m.R, m.T, rule=capacity_limit)

    def expansion_limit(model, r, t):
        option = resources[r].capacity_option
        if not option or t < option.activation_lead_time:
            return model.expand[r, t] == 0
        maximum = option.maximum_activated_capacity or 0
        return model.expand[r, t] <= (maximum * model.is_active[r, t] if option.fixed_cost else maximum)
    m.expansion_limit = Constraint(m.R, m.T, rule=expansion_limit)

    if project.budget is not None:
        def budget(model):
            expansion = sum(model.expand[r, t] * (resources[r].capacity_option.variable_operating_cost if resources[r].capacity_option else 0) for r in resources for t in periods)
            fixed = sum(model.is_active[r, t] * resources[r].capacity_option.activation_cost for r in fixed_resources for t in periods)
            return expansion + fixed <= project.budget
        m.budget = Constraint(rule=budget)

    def objective(model):
        operating = sum(model.allocate[r, d, t] * resources[r].operating_cost for r, d in compatible for t in periods)
        allocation = sum(model.allocate[r, d, t] * (0 if resources[r].location_id == demands[d].location_id else 1) for r, d in compatible for t in periods)
        expansion = sum(model.expand[r, t] * (resources[r].capacity_option.variable_operating_cost if resources[r].capacity_option else 0) for r in resources for t in periods)
        fixed = sum(model.is_active[r, t] * resources[r].capacity_option.activation_cost for r in fixed_resources for t in periods)
        shortage = sum(model.unmet[d, t] * demands[d].shortage_penalty for d in demands for t in periods)
        return operating + allocation + expansion + fixed + shortage
    m.objective = Objective(rule=objective, sense=minimize)

    optimizer = SolverFactory("appsi_highs")
    if not optimizer.available(exception_flag=False):
        raise RuntimeError("HiGHS is unavailable. Install backend requirements, including highspy.")
    optimizer.config.time_limit = time_limit_seconds
    outcome = optimizer.solve(m)
    termination = outcome.solver.termination_condition
    status_map = {
        TerminationCondition.optimal: "optimal",
        TerminationCondition.feasible: "feasible",
        TerminationCondition.infeasible: "infeasible",
        TerminationCondition.unbounded: "unbounded",
        TerminationCondition.maxTimeLimit: "time_limit",
    }
    status = status_map.get(termination, "error")
    if status in {"infeasible", "unbounded", "error"}:
        return OptimizationResult(status=status, objective_value=None, solver_runtime_seconds=time.perf_counter() - started,
            allocations=[], capacities=[], demands=[], costs=CostBreakdown(operating=0, allocation=0, expansion=0, shortage=0, total=0),
            service_rate=0, recommendations=[], diagnostics={"termination_condition": str(termination), "solver_status": str(outcome.solver.status)})

    allocations = []
    allocated_by_resource_period = defaultdict(float)
    allocated_by_demand_period = defaultdict(float)
    operating = allocation_cost = 0.0
    for r, d in compatible:
        for t in periods:
            qty = value(m.allocate[r, d, t]) or 0
            if qty > 1e-7:
                unit_allocation = 0 if resources[r].location_id == demands[d].location_id else 1
                allocations.append(AllocationResult(resource_id=r, demand_id=d, period=t, quantity=qty, unit_cost=resources[r].operating_cost + unit_allocation))
                allocated_by_resource_period[r, t] += qty
                allocated_by_demand_period[d, t] += qty
                operating += qty * resources[r].operating_cost
                allocation_cost += qty * unit_allocation
    capacities, expansion_cost, recommendations = [], 0.0, []
    for r in resources:
        for t in periods:
            expanded = value(m.expand[r, t]) or 0
            total = availability[r, t] + expanded
            utilization = allocated_by_resource_period[r, t] / total if total else 0
            capacities.append(CapacityResult(resource_id=r, period=t, base_capacity=availability[r, t], activated_capacity=expanded, utilization=utilization))
            if expanded > 1e-7:
                option = resources[r].capacity_option
                expansion_cost += expanded * option.variable_operating_cost
                if option.fixed_cost:
                    expansion_cost += (value(m.is_active[r, t]) or 0) * option.activation_cost
                recommendations.append(f"Activate {expanded:.1f} additional {resources[r].capacity_unit} at {resources[r].name} in period {t + 1}.")
    demand_results, shortage_cost, total_required, total_unmet = [], 0.0, 0.0, 0.0
    for d in demands.values():
        for t in periods:
            required = demand_qty.get((d.id, t), 0)
            unmet = value(m.unmet[d.id, t]) or 0
            demand_results.append(DemandResult(demand_id=d.id, period=t, required=required, allocated=allocated_by_demand_period[d.id, t], unmet=unmet))
            total_required += required
            total_unmet += unmet
            shortage_cost += unmet * d.shortage_penalty
            if unmet > 1e-7:
                recommendations.append(f"Address {unmet:.1f} {project.default_capacity_unit} of unmet {d.name} demand in period {t + 1}.")
    total = operating + allocation_cost + expansion_cost + shortage_cost
    return OptimizationResult(status=status, objective_value=value(m.objective), solver_runtime_seconds=time.perf_counter() - started,
        allocations=allocations, capacities=capacities, demands=demand_results,
        costs=CostBreakdown(operating=operating, allocation=allocation_cost, expansion=expansion_cost, shortage=shortage_cost, total=total),
        service_rate=(1 - total_unmet / total_required) if total_required else 1.0, recommendations=recommendations,
        diagnostics={"termination_condition": str(termination), "solver_status": str(outcome.solver.status), "solution_validated": abs(total - value(m.objective)) < 1e-5})

