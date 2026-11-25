from pyomo.environ import ConcreteModel, RangeSet, Set

from ..schemas import EnergyProject
from .constraints import add_energy_balance_constraints, add_operating_limit_constraints, add_storage_dynamics_constraints
from .objective import define_objective
from .variables import declare_decision_variables


def build_model(data: EnergyProject):
    """Construct the deterministic storage model in mathematical reading order."""
    model = ConcreteModel(name=f"energy_storage_{data.id}")
    model.PERIODS = RangeSet(0, data.number_of_periods - 1)
    model.STATE_PERIODS = RangeSet(0, data.number_of_periods)
    model.STORAGES = Set(initialize=[storage.id for storage in data.storages], ordered=True)
    declare_decision_variables(model)
    add_energy_balance_constraints(model, data)
    add_storage_dynamics_constraints(model, data)
    add_operating_limit_constraints(model, data)
    define_objective(model, data)
    return model

