"""Capacity-planning schema validation tests."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.capacity_planning.schemas import Demand, Location, Project, Resource


def test_rejects_availability_with_wrong_horizon():
    with pytest.raises(ValidationError, match="availability series"):
        Project(name="x", planning_start_date=date.today(), time_unit="week", number_of_periods=2, currency="EUR", default_capacity_unit="units",
                locations=[Location(id="l", name="L")], resources=[Resource(id="r", name="R", type="x", location_id="l", capacity_unit="units", maximum_capacity=10, availability=[10])], demands=[])


def test_rejects_unknown_demand_location():
    with pytest.raises(ValidationError, match="unknown location"):
        Project(name="x", planning_start_date=date.today(), time_unit="week", number_of_periods=1, currency="EUR", default_capacity_unit="units",
                locations=[Location(id="l", name="L")], resources=[], demands=[Demand(name="D", location_id="missing", required_resource_type="x", period=0, quantity=2, shortage_penalty=3)])

