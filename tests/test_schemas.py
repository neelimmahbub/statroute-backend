import pytest
from pydantic import ValidationError

from app.agent.schemas import (
    EmergencyInput,
    EmergencyRequest,
    RouteResult,
    SupplierNode,
    SupplierRoute,
)


def test_emergency_input_accepts_string():
    body = EmergencyInput(message="Need blood at St. Jude!")
    assert body.message == "Need blood at St. Jude!"


def test_emergency_input_rejects_extra_fields():
    with pytest.raises(ValidationError):
        EmergencyInput(message="alert", hospital="St. Jude")


def test_emergency_request_valid():
    req = EmergencyRequest(
        hospital="St. Jude",
        item="O-negative blood",
        quantity=10,
        urgency="Critical",
    )
    assert req.hospital == "St. Jude"
    assert req.urgency == "Critical"


def test_emergency_request_invalid_urgency():
    with pytest.raises(ValidationError):
        EmergencyRequest(
            hospital="St. Jude",
            item="O-neg",
            quantity=10,
            urgency="Extreme",
        )


def test_emergency_request_invalid_quantity_type():
    with pytest.raises(ValidationError):
        EmergencyRequest(
            hospital="St. Jude",
            item="O-neg",
            quantity="lots",
            urgency="High",
        )


def test_emergency_request_model_dump_keys():
    req = EmergencyRequest(
        hospital="Metro Health",
        item="epinephrine",
        quantity=5,
        urgency="Medium",
    )
    dumped = req.model_dump()
    assert set(dumped.keys()) == {"hospital", "item", "quantity", "urgency"}


def test_emergency_input_and_request_are_distinct_types():
    assert EmergencyInput is not EmergencyRequest
    assert "message" in EmergencyInput.model_fields
    assert "message" not in EmergencyRequest.model_fields


def test_supplier_node_id_equals_node():
    node = SupplierNode(
        id="City General",
        node="City General",
        available_qty=50,
        x=3.0,
        y=4.0,
    )
    assert node.id == node.node


def test_supplier_route_structure():
    route = SupplierRoute(
        supplier_id="City General",
        quantity_allocated=10,
        path=["St. Jude", "City General"],
        distance=5.0,
    )
    assert route.supplier_id == "City General"
    assert route.quantity_allocated == 10
    assert len(route.path) == 2


def test_route_result_single_supplier():
    route = SupplierRoute(
        supplier_id="City General",
        quantity_allocated=10,
        path=["St. Jude", "City General"],
        distance=5.0,
    )
    result = RouteResult(routes=[route], total_quantity=10, partial=False)
    assert result.partial is False
    assert result.total_quantity == 10


def test_route_result_partial():
    routes = [
        SupplierRoute(
            supplier_id="City General",
            quantity_allocated=10,
            path=["St. Jude", "City General"],
            distance=5.0,
        ),
        SupplierRoute(
            supplier_id="Metro Health",
            quantity_allocated=5,
            path=["St. Jude", "Metro Health"],
            distance=7.1,
        ),
    ]
    result = RouteResult(routes=routes, total_quantity=15, partial=True)
    assert result.partial is True
    assert len(result.routes) == 2
