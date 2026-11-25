from ..schemas import EnergyProject, EnergyScenario, StorageAsset


def energy_demo_project() -> EnergyProject:
    demand = [65, 61, 58, 55, 54, 57, 65, 78, 86, 90, 88, 84, 80, 79, 82, 91, 105, 118, 124, 116, 101, 88, 77, 69]
    renewable = [18, 20, 22, 24, 25, 24, 22, 20, 18, 21, 28, 34, 42, 48, 43, 35, 26, 18, 12, 10, 11, 13, 15, 17]
    import_price = [42, 39, 36, 34, 33, 38, 52, 71, 83, 86, 79, 68, 59, 56, 63, 81, 112, 148, 162, 139, 102, 76, 58, 48]
    return EnergyProject(
        id="demo-pumped-hydro", name="Alpine Pumped-Hydro Dispatch", description="Hourly dispatch of a pumped-hydro facility against demand, renewables, and grid prices.",
        number_of_periods=24, interval_hours=1, currency="EUR",
        storages=[StorageAsset(id="upper-reservoir", name="Upper Reservoir", energy_capacity_mwh=420, minimum_energy_mwh=42,
            initial_energy_mwh=190, terminal_energy_minimum_mwh=170, maximum_charge_power_mw=75, maximum_discharge_power_mw=90,
            charge_efficiency=.91, discharge_efficiency=.9, variable_charge_cost_per_mwh=1.5, variable_discharge_cost_per_mwh=2),
            StorageAsset(id="valley-battery", name="Valley Battery", energy_capacity_mwh=80, minimum_energy_mwh=4,
            initial_energy_mwh=32, terminal_energy_minimum_mwh=24, maximum_charge_power_mw=35, maximum_discharge_power_mw=35,
            charge_efficiency=.96, discharge_efficiency=.96, variable_charge_cost_per_mwh=.5, variable_discharge_cost_per_mwh=.8)],
        demand_mwh=demand, renewable_generation_mwh=renewable, grid_import_price_per_mwh=import_price,
        grid_export_price_per_mwh=[max(0, p - 8) for p in import_price], shortage_penalty_per_mwh=5000, terminal_energy_value_per_mwh=35,
        scenarios=[
            EnergyScenario(id="expected-day", name="Expected day", probability=.55, demand_multiplier=[1]*24, renewable_multiplier=[1]*24, price_multiplier=[1]*24, natural_inflow_mwh=[0]*24),
            EnergyScenario(id="evening-stress", name="Evening demand stress", probability=.25, demand_multiplier=[1]*15+[1.18]*6+[1]*3, renewable_multiplier=[1]*16+[.65]*8, price_multiplier=[1]*16+[1.25]*5+[1]*3, natural_inflow_mwh=[0]*24),
            EnergyScenario(id="renewable-surplus", name="Renewable surplus", probability=.20, demand_multiplier=[.96]*24, renewable_multiplier=[1.35]*24, price_multiplier=[.9]*24, natural_inflow_mwh=[0]*24),
        ])

