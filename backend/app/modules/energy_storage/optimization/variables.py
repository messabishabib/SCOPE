from pyomo.environ import Binary, NonNegativeReals, Var


def declare_decision_variables(model) -> None:
    """Declare every business decision and the inter-period storage state."""
    model.charge_power_mw = Var(model.STORAGES, model.PERIODS, domain=NonNegativeReals)
    model.discharge_power_mw = Var(model.STORAGES, model.PERIODS, domain=NonNegativeReals)
    model.stored_energy_mwh = Var(model.STORAGES, model.STATE_PERIODS, domain=NonNegativeReals)
    model.grid_import_mwh = Var(model.PERIODS, domain=NonNegativeReals)
    model.grid_export_mwh = Var(model.PERIODS, domain=NonNegativeReals)
    model.unserved_energy_mwh = Var(model.PERIODS, domain=NonNegativeReals)
    model.renewable_curtailment_mwh = Var(model.PERIODS, domain=NonNegativeReals)
    model.is_charging = Var(model.STORAGES, model.PERIODS, domain=Binary)

