import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from box_packer.api.routes import MAX_PACKAGES_PER_REQUEST, get_catalogue
from box_packer.main import create_app
from box_packer.models import BoxType

SPEC_EXAMPLE = [
    {"id": 123, "width": 10, "height": 10, "length": 10, "weight": 5},
    {"id": 125, "width": 5, "height": 5, "length": 10, "weight": 10},
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def package(**overrides: Any) -> dict[str, Any]:
    return {"id": 1, "width": 10, "height": 10, "length": 10, "weight": 1} | overrides


def post_raw(client: TestClient, body: str) -> Response:
    return client.post("/packing", content=body, headers={"content-type": "application/json"})


def assert_error(response: Response, status: int, code: str) -> list[dict[str, Any]]:
    """Assert the unified error envelope and return its details."""
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"code", "message", "details"}
    assert body["code"] == code
    assert isinstance(body["message"], str)
    assert body["message"]
    for detail in body["details"]:
        assert set(detail) == {"loc", "package_id", "type", "message"}
    details: list[dict[str, Any]] = body["details"]
    return details


def test_spec_example_payload(client: TestClient) -> None:
    response = client.post("/packing", json=SPEC_EXAMPLE)

    assert response.status_code == 200
    assert response.json() == {
        "box_count": 1,
        "boxes": [{"box_type": "B", "package_ids": [123, 125]}],
    }


def test_empty_list_needs_no_boxes(client: TestClient) -> None:
    response = client.post("/packing", json=[])

    assert response.status_code == 200
    assert response.json() == {"box_count": 0, "boxes": []}


def test_accepts_decimal_dimensions(client: TestClient) -> None:
    response = client.post("/packing", json=[package(width=10.5, weight=0.25)])

    assert response.status_code == 200
    assert response.json()["box_count"] == 1


def test_lists_one_entry_per_box(client: TestClient) -> None:
    heavy = [package(id=i, weight=2000) for i in (1, 2)]

    response = client.post("/packing", json=heavy)

    assert response.json() == {
        "box_count": 2,
        "boxes": [
            {"box_type": "C", "package_ids": [1]},
            {"box_type": "C", "package_ids": [2]},
        ],
    }


def test_duplicate_ids_are_rejected(client: TestClient) -> None:
    payload = [package(id=7), package(id=8), package(id=7)]

    details = assert_error(client.post("/packing", json=payload), 422, "duplicate_package_ids")

    assert [(d["loc"], d["package_id"], d["type"]) for d in details] == [
        ([0, "id"], 7, "duplicate_id"),
        ([2, "id"], 7, "duplicate_id"),
    ]


def test_unpackable_packages_are_all_reported(client: TestClient) -> None:
    payload = [
        package(id=1),
        package(id=99, width=500),
        package(id=100, weight=5000),
        package(id=101, width=500, weight=5000),
    ]

    details = assert_error(client.post("/packing", json=payload), 422, "unpackable_packages")

    assert [(d["loc"], d["package_id"], d["type"]) for d in details] == [
        ([1], 99, "too_large"),
        ([2], 100, "too_heavy"),
        ([3], 101, "too_large_and_too_heavy"),
    ]
    assert details[0]["message"] == "Package 99 is larger than every box, in any orientation."


@pytest.mark.parametrize(
    ("payload", "loc", "error_type"),
    [
        ({}, [], "list_type"),
        ({"packages": SPEC_EXAMPLE}, [], "list_type"),
        ([42], [0], "model_attributes_type"),
        ([package(id=True)], [0, "id"], "int_type"),
        ([package(id="1")], [0, "id"], "int_type"),
        ([package(id=1.5)], [0, "id"], "int_type"),
        ([package(width=True)], [0, "width"], "float_type"),
        ([package(width="10")], [0, "width"], "float_type"),
        ([package(width=None)], [0, "width"], "float_type"),
        ([package(width=0)], [0, "width"], "greater_than"),
        ([package(height=-1)], [0, "height"], "greater_than"),
        ([package(length=-0.5)], [0, "length"], "greater_than"),
        ([package(weight=0)], [0, "weight"], "greater_than"),
        ([package(colour="red")], [0, "colour"], "extra_forbidden"),
    ],
    ids=[
        "object-body",
        "wrapped-array",
        "non-object-item",
        "bool-id",
        "string-id",
        "float-id",
        "bool-width",
        "string-width",
        "null-width",
        "zero-width",
        "negative-height",
        "negative-length",
        "zero-weight",
        "extra-field",
    ],
)
def test_invalid_payloads(
    client: TestClient, payload: Any, loc: list[str | int], error_type: str
) -> None:
    details = assert_error(client.post("/packing", json=payload), 422, "validation_error")

    assert [(d["loc"], d["type"]) for d in details] == [(loc, error_type)]


@pytest.mark.parametrize("field", ["id", "width", "height", "length", "weight"])
def test_missing_field(client: TestClient, field: str) -> None:
    item = package()
    del item[field]

    details = assert_error(client.post("/packing", json=[item]), 422, "validation_error")

    assert [(d["loc"], d["type"]) for d in details] == [([0, field], "missing")]


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_are_rejected(client: TestClient, literal: str) -> None:
    body = json.dumps([package()]).replace('"width": 10', f'"width": {literal}')

    details = assert_error(post_raw(client, body), 422, "validation_error")

    assert [(d["loc"], d["type"]) for d in details] == [([0, "width"], "finite_number")]


def test_reports_every_invalid_field(client: TestClient) -> None:
    payload = [package(width=0, weight=-1), package(id=2, height="x")]

    details = assert_error(client.post("/packing", json=payload), 422, "validation_error")

    assert sorted(tuple(map(str, d["loc"])) for d in details) == [
        ("0", "weight"),
        ("0", "width"),
        ("1", "height"),
    ]


def test_malformed_json(client: TestClient) -> None:
    details = assert_error(post_raw(client, '[{"id": 1,'), 400, "invalid_json")

    assert details[0]["type"] == "json_invalid"


def test_missing_body(client: TestClient) -> None:
    details = assert_error(post_raw(client, ""), 422, "validation_error")

    assert details[0]["type"] == "missing"


def test_request_size_is_capped(client: TestClient) -> None:
    payload = [package(id=i) for i in range(MAX_PACKAGES_PER_REQUEST + 1)]

    details = assert_error(client.post("/packing", json=payload), 422, "validation_error")

    assert details[0]["type"] == "too_long"


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    assert_error(client.get("/nope"), 404, "not_found")


def test_wrong_method_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/packing")

    assert_error(response, 405, "method_not_allowed")
    assert response.headers["allow"] == "POST"


def test_unexpected_errors_use_error_envelope_without_leaking_internals() -> None:
    def broken_catalogue() -> None:
        raise RuntimeError("secret internal detail")

    app = create_app()
    app.dependency_overrides[get_catalogue] = broken_catalogue
    response = TestClient(app, raise_server_exceptions=False).post("/packing", json=[])

    assert_error(response, 500, "internal_error")
    assert "secret" not in response.text


def test_custom_catalogue_can_be_injected() -> None:
    tube = BoxType(name="Tube", width=5, height=5, length=500, max_weight=10)
    client = TestClient(create_app(catalogue=(tube,)))

    ok = client.post("/packing", json=[package(width=4, height=4, length=450)])
    too_wide = client.post("/packing", json=[package(id=2)])

    assert ok.json() == {"box_count": 1, "boxes": [{"box_type": "Tube", "package_ids": [1]}]}
    assert assert_error(too_wide, 422, "unpackable_packages")[0]["package_id"] == 2


def test_openapi_documents_error_envelope(client: TestClient) -> None:
    responses = client.get("/openapi.json").json()["paths"]["/packing"]["post"]["responses"]

    for status in ("400", "422"):
        schema_ref = responses[status]["content"]["application/json"]["schema"]["$ref"]
        assert schema_ref.endswith("/ErrorResponse")
