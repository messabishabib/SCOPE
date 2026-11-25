import time

from pyomo.environ import SolverFactory
from pyomo.opt import TerminationCondition

from ...schemas import EnergyCostBreakdown, EnergyOptimizationResult, EnergyPlanningMode
from .model import build_model
from .results import extract_result


def solve(data,time_limit_seconds=60,commitment_periods=1):
    started=time.perf_counter();model,scenarios,probabilities=build_model(data,commitment_periods)
    optimizer=SolverFactory("appsi_highs")
    if not optimizer.available(exception_flag=False): raise RuntimeError("HiGHS is unavailable. Install highspy from backend requirements.")
    optimizer.config.time_limit=time_limit_seconds;outcome=optimizer.solve(model);termination=outcome.solver.termination_condition
    status={TerminationCondition.optimal:"optimal",TerminationCondition.feasible:"feasible",TerminationCondition.infeasible:"infeasible",TerminationCondition.unbounded:"unbounded",TerminationCondition.maxTimeLimit:"time_limit"}.get(termination,"error")
    runtime=time.perf_counter()-started;diagnostics={"solver":"HiGHS","termination_condition":str(termination),"solver_status":str(outcome.solver.status)}
    if status in {"infeasible","unbounded","error"}:
        zero=EnergyCostBreakdown(grid_import=0,grid_export_revenue=0,charging=0,discharging=0,shortage=0,spillage=0,terminal_value=0,total=0)
        return EnergyOptimizationResult(status=status,objective_value=None,solver_runtime_seconds=runtime,periods=[],costs=zero,total_unserved_mwh=0,renewable_curtailment_mwh=0,total_spilled_inflow_mwh=0,planning_mode=EnergyPlanningMode.stochastic,diagnostics=diagnostics)
    return extract_result(model,data,scenarios,probabilities,status,runtime,commitment_periods,diagnostics)
