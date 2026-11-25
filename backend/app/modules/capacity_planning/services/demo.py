from datetime import date

from ..schemas import CapacityOption, Demand, Location, Project, Resource, Scenario


def demo_projects() -> list[Project]:
    return [_manufacturing(), _distribution(), _service()]


def _manufacturing() -> Project:
    locations = [Location(id="plant-north", name="North Plant"), Location(id="plant-central", name="Central Plant"), Location(id="plant-south", name="South Plant")]
    resources = [
        Resource(id="press-north", name="North Press Line", type="press", location_id="plant-north", capacity_unit="units", maximum_capacity=180, operating_cost=5.2, availability=[110, 120, 115, 110, 120, 120], capacity_option=CapacityOption(additional_capacity=45, maximum_activated_capacity=45, activation_cost=250, variable_operating_cost=2, fixed_cost=True, activation_lead_time=1)),
        Resource(id="press-central", name="Central Press Line", type="press", location_id="plant-central", capacity_unit="units", maximum_capacity=190, operating_cost=4.8, availability=[130, 125, 130, 125, 120, 125], capacity_option=CapacityOption(additional_capacity=35, maximum_activated_capacity=35, variable_operating_cost=2.5)),
        Resource(id="press-south", name="South Press Line", type="press", location_id="plant-south", capacity_unit="units", maximum_capacity=160, operating_cost=5, availability=[90, 95, 90, 100, 95, 95]),
    ]
    demands = [Demand(id=f"orders-{i}", name="Customer orders", location_id="plant-central", required_resource_type="press", period=i, quantity=q, shortage_penalty=80) for i, q in enumerate([280, 330, 345, 370, 350, 325])]
    scenarios = [Scenario(id="baseline", name="Baseline", description="Approved weekly forecast"), Scenario(id="demand-up", name="Demand +15%", demand_multiplier=1.15, probability=.3), Scenario(id="north-outage", name="North disruption", availability_multipliers={"press-north": [1, .7, .6, .8, 1, 1]}, probability=.1)]
    return Project(id="demo-manufacturing", name="Manufacturing Capacity", description="Weekly press capacity across three facilities", planning_start_date=date(2026, 11, 2), time_unit="week", number_of_periods=6, currency="EUR", default_capacity_unit="units", locations=locations, resources=resources, demands=demands, scenarios=scenarios)


def _distribution() -> Project:
    locations = [Location(id="west", name="West Depot"), Location(id="east", name="East Depot"), Location(id="metro", name="Metro Region")]
    resources = [Resource(id="west-fleet", name="West Fleet", type="delivery", location_id="west", capacity_unit="pallets", maximum_capacity=500, operating_cost=2.4, availability=[330, 350, 340, 360]), Resource(id="east-fleet", name="East Fleet", type="delivery", location_id="east", capacity_unit="pallets", maximum_capacity=480, operating_cost=2.2, availability=[310, 320, 320, 330], capacity_option=CapacityOption(additional_capacity=90, variable_operating_cost=1.8))]
    demands = [Demand(id=f"regional-{i}", name="Regional shipments", location_id="metro", required_resource_type="delivery", period=i, quantity=q, shortage_penalty=45) for i, q in enumerate([590, 640, 720, 610])]
    return Project(id="demo-distribution", name="Distribution Capacity", description="Depot fleet capacity and regional demand", planning_start_date=date(2026, 11, 1), time_unit="week", number_of_periods=4, currency="EUR", default_capacity_unit="pallets", locations=locations, resources=resources, demands=demands, scenarios=[Scenario(id="baseline", name="Baseline"), Scenario(id="peak", name="Peak season", demand_multiplier=1.2)])


def _service() -> Project:
    locations = [Location(id="paris", name="Paris Center"), Location(id="lyon", name="Lyon Center")]
    resources = [Resource(id="paris-team", name="Paris Service Team", type="service", location_id="paris", capacity_unit="hours", maximum_capacity=950, operating_cost=32, availability=[760, 780, 760]), Resource(id="lyon-team", name="Lyon Service Team", type="service", location_id="lyon", capacity_unit="hours", maximum_capacity=700, operating_cost=29, availability=[540, 560, 550], capacity_option=CapacityOption(additional_capacity=100, activation_cost=900, variable_operating_cost=8, fixed_cost=True))]
    demands = [Demand(id=f"tickets-{i}", name="Support workload", location_id="paris", required_resource_type="service", period=i, quantity=q, shortage_penalty=120) for i, q in enumerate([1180, 1410, 1250])]
    return Project(id="demo-service", name="Service Capacity", description="Monthly service-center workload", planning_start_date=date(2026, 11, 1), time_unit="month", number_of_periods=3, currency="EUR", default_capacity_unit="hours", locations=locations, resources=resources, demands=demands, scenarios=[Scenario(id="baseline", name="Baseline")])

