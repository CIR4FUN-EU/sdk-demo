"""Covers the only real logic: build + validate, and the offline web steps.
No live service calls (store/register stay manual against real services)."""

from fastapi.testclient import TestClient
from dpp_sdk import validate_dpp4fun

from demo import build
from demo.app import app


def test_build_produces_valid_dpp():
    dpp = build.build_dpp(connector={})
    validate_dpp4fun(dpp)  # raises if invalid
    assert dpp.characteristics.productName == "Cir4Fun Oak Dining Chair"
    assert dpp.characteristics.dimensions.unit == "mm"
    assert [m.name for m in dpp.billOfMaterials.materials][0] == "Solid oak"


def test_web_build():
    client = TestClient(app)
    client.post("/api/reset")
    built = client.post("/api/build")
    assert built.status_code == 200
    assert "Cir4Fun Oak Dining Chair" in built.text


def test_detail_surfaces_server_explanation():
    from dpp_sdk.clients.errors import DppApiClientError, DppHttpClientError
    from dpp_sdk.clients.payloads import DppApiMessage, DppStatusCode

    from demo.app import _detail

    http = DppHttpClientError("non-success HTTP status 400", 400, "missing productIdentifier")
    assert "missing productIdentifier" in _detail(http)

    api = DppApiClientError(
        "error status", DppStatusCode.ClientErrorBadRequest,
        [DppApiMessage(text="repoUrl not reachable")], "{}",
    )
    assert "repoUrl not reachable" in _detail(api)

    assert _detail(ValueError("boom")) == "boom"
