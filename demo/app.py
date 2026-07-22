"""Step-by-step web frontend for the DPP pipeline.

Serves a single page (static/index.html) plus one JSON endpoint per pipeline
step. Run with: python -m demo.app  (then open http://localhost:8000)."""

import json
import os
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dpp_sdk import to_json, validate_dpp4fun
from dpp_sdk.clients import RegisterDppRequest
from dpp_sdk.clients.errors import DppApiClientError, DppHttpClientError

from demo import connector, build, pipeline, data_server

app = FastAPI(title="DPP pipeline demo")
_INDEX = Path(__file__).parent / "static" / "index.html"

# Serves images (e.g. the logo) under /static/*. Also incidentally exposes
# static/index.html at /static/index.html -- harmless, / still serves the page.
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# ponytail: single in-memory state, one demo user at a time
STATE: dict = {}


# Same page for both routes; the page reads the path to decide whether to show
# the data-space connector source.
@app.get("/")
@app.get("/no-connector")
def index() -> FileResponse:
    return FileResponse(_INDEX)


@app.post("/api/reset")
def reset() -> dict:
    STATE.clear()
    connector.flow_reset()
    data_server.reset()
    return {"ok": True}


@app.post("/api/connector")
def step_connector() -> dict:
    host = os.getenv("EDC_HOST", "http://localhost")
    asset_id = os.getenv("EDC_ASSET_ID", "demo-asset")
    STATE["connector"] = connector.fetch_asset_properties(asset_id, host=host)
    return {"asset_id": asset_id, "host": host, "properties": STATE["connector"]}


@app.get("/api/data-server")
def get_hosted_data() -> dict:
    return data_server.DATA


@app.post("/api/data-server")
def set_hosted_data(body: dict) -> dict:
    data_server.DATA = body
    return body


# --- Step-by-step connector flow (mirrors edc-client's examples/full_flow.py) ---
_FLOW_STEPS = {
    "create-asset": connector.flow_create_asset,
    "create-policy": connector.flow_create_policy,
    "create-contract-def": connector.flow_create_contract_definition,
    "catalog": connector.flow_fetch_catalog,
    "negotiate": connector.flow_negotiate,
    "negotiation-status": connector.flow_poll_negotiation,
    "transfer": connector.flow_start_transfer,
    "transfer-status": connector.flow_poll_transfer,
    "edr": connector.flow_get_edr,
    "pull": connector.flow_pull_data,
}


@app.get("/api/connector/asset-defaults")
def connector_asset_defaults() -> dict:
    return connector.ASSET_DEFAULTS


@app.post("/api/connector/{step}")
def step_connector_flow(step: str, body: dict | None = Body(default=None)) -> dict:
    fn = _FLOW_STEPS.get(step)
    if fn is None:
        raise HTTPException(404, f"Unknown connector flow step: {step}")
    try:
        result = fn(body) if step == "create-asset" else fn()
    except Exception as e:
        raise HTTPException(502, f"Connector step '{step}' failed: {e}")
    if step == "pull":
        STATE["connector"] = result
    return result


@app.post("/api/build")
def step_build() -> dict:
    try:
        dpp = build.build_dpp(STATE.get("connector", {}))
        validate_dpp4fun(dpp)
    except Exception as e:  # surface validation/build errors to the page
        raise HTTPException(422, f"Build/validation failed: {e}")
    STATE["dpp"] = dpp
    return json.loads(to_json(dpp))  # flattened wire JSON


@app.post("/api/store")
def step_store() -> dict:
    if "dpp" not in STATE:
        raise HTTPException(400, "Build the DPP first.")
    repo_url = _require("DPP_REPO_BASE_URL")
    repo, _ = pipeline.make_clients(repo_url, _require("DPP_REGISTRY_BASE_URL"))
    try:
        repo.health_check()
        STATE["dpp_id"] = repo.create_dpp(STATE["dpp"]).dppId
    except Exception as e:
        raise HTTPException(502, f"Repository call failed ({repo_url}): {_detail(e)}")
    # Return a browser-reachable URL (host-published port), not the in-container one.
    return {"dppId": STATE["dpp_id"], "repoUrl": os.getenv("DPP_REPO_PUBLIC_URL", repo_url)}


@app.post("/api/register")
def step_register() -> dict:
    if "dpp_id" not in STATE:
        raise HTTPException(400, "Store the DPP first.")
    repo_url = _require("DPP_REPO_BASE_URL")
    registry_url = _require("DPP_REGISTRY_BASE_URL")
    _, registry = pipeline.make_clients(repo_url, registry_url)
    try:
        registry.health_check()
        resp = registry.post_new_dpp_to_registry(
            RegisterDppRequest(
                productIdentifier=str(STATE["dpp"].uniqueProductIdentifier),
                dppIdentifier=STATE["dpp_id"],
                operatorIdentifier=_require("DPP_OPERATOR_ID"),
                repoUrl=repo_url,
            )
        )
    except Exception as e:
        raise HTTPException(502, f"Registry call failed ({registry_url}): {_detail(e)}")
    # Return a browser-reachable URL (host-published port), not the in-container one.
    return {"registryIdentifier": resp.registryIdentifier,
            "registryUrl": os.getenv("DPP_REGISTRY_PUBLIC_URL", registry_url)}


def _detail(e: Exception) -> str:
    # The SDK keeps the server's explanation off to the side, not in str(e):
    # response_body for non-2xx, messages/raw body for envelope error statuses.
    if isinstance(e, DppHttpClientError) and e.response_body:
        return f"{e} — {e.response_body}"
    if isinstance(e, DppApiClientError):
        msgs = "; ".join(m.text for m in (e.messages or []) if m.text)
        return f"{e} — {msgs or e.raw_response_body}"
    return str(e)


def _require(var: str) -> str:
    val = os.getenv(var)
    if not val:
        raise HTTPException(400, f"{var} is not set (configure it in the environment).")
    return val


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
