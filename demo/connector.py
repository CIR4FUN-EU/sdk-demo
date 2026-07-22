"""Data-space connector source for the DPP demo.

Thin adapter over the edc-client Connector class (installed editable as edc_demo):
provider-set up an asset, then consumer-pull it across the data space.
"""

import json
import os
import time

from examples.connector import example_connector

from . import data_server

ASSET_ID = "asset-1"
POLICY_ID = "policy-1"
CONTRACT_DEF_ID = "contract-def-1"

# Where the provider fetches the asset backend. In the all-container stack it's the
# demo-app service (set via env); host runs fall back to Docker's host alias.
DATA_SERVER_URL = os.getenv("DATA_SERVER_URL", "http://host.docker.internal:4000")

ASSET_DEFAULTS = {
    "asset_id": ASSET_ID,
    "base_url": DATA_SERVER_URL,
    "name": "Test asset",
    "content_type": "application/json",
    "proxy_path": True,
}


def fetch_asset_properties(asset_id: str = ASSET_ID, host: str = None) -> dict:
    """Set up an asset on the provider, then pull it as the consumer.
    Returns the pulled data (parsed JSON). `host` is unused — endpoints come from env."""
    provider = example_connector("PROVIDER")
    consumer = example_connector("CONSUMER")

    # Provider setup is idempotent across runs; a 409 just means it already exists.
    print("\n[0] Provider setup...")
    data_server.start()
    try:
        provider.create_asset(asset_id, DATA_SERVER_URL)
        provider.create_policy(POLICY_ID)
        provider.create_contract_definition(CONTRACT_DEF_ID, POLICY_ID, POLICY_ID)
        print("    asset + policy + contract-definition created")
    except Exception as e:
        print(f"    setup skipped/partial ({e}) — assuming already created")

    print("\n[1] Negotiating + pulling asset...")
    resp = consumer.negotiate_and_transfer(provider, asset_id)
    return resp.json()


# --- Step-by-step flow (mirrors edc-client's examples/full_flow.py) ---
# ponytail: single in-memory flow state, one demo user at a time (matches app.py's STATE)
_FLOW: dict = {}


def flow_reset() -> None:
    _FLOW.clear()


def _create_or_existing(fn) -> dict:
    """Run a provider-setup call, returning its full response body (or the error, on 409/already-exists).
    The underlying edc_client calls use the "_without_preload_content" API variant, which doesn't raise
    on non-2xx — a conflict comes back as the raw error body (a list), not an exception."""
    try:
        result = fn()
    except Exception as e:
        return {"error": f"{e} — assuming already created"}
    if isinstance(result, list):
        return {"error": f"{result} — assuming already created"}
    return result


def flow_create_asset(asset: dict | None = None) -> dict:
    """Step 1: create the asset on the provider. `asset` overrides ASSET_DEFAULTS;
    missing keys fall back to the default."""
    cfg = {**ASSET_DEFAULTS, **(asset or {})}
    asset_id = cfg["asset_id"]
    data_server.start()
    provider = example_connector("PROVIDER")
    consumer = example_connector("CONSUMER")
    _FLOW.update(provider=provider, consumer=consumer, asset_id=asset_id)
    return _create_or_existing(lambda: provider.create_asset(
        asset_id, cfg["base_url"],
        name=cfg["name"], content_type=cfg["content_type"], proxy_path=cfg["proxy_path"],
    ))


def flow_create_policy() -> dict:
    """Step 2: create the ODRL policy on the provider."""
    return _create_or_existing(lambda: _FLOW["provider"].create_policy(POLICY_ID))


def flow_create_contract_definition() -> dict:
    """Step 3: link the policy to assets via a contract definition."""
    provider = _FLOW["provider"]
    return _create_or_existing(
        lambda: provider.create_contract_definition(CONTRACT_DEF_ID, POLICY_ID, POLICY_ID)
    )


def flow_fetch_catalog() -> dict:
    """Step 4: fetch the provider's catalog and pick the offer for our asset. Returns the full catalog."""
    consumer, provider, asset_id = _FLOW["consumer"], _FLOW["provider"], _FLOW["asset_id"]
    catalog = consumer.fetch_catalog(provider)
    datasets = catalog.get("dcat:dataset") or catalog.get("dataset", [])
    if isinstance(datasets, dict):
        datasets = [datasets]
    dataset = next(d for d in datasets if d.get("@id") == asset_id)
    policies = dataset.get("odrl:hasPolicy") or dataset.get("hasPolicy", [])
    if isinstance(policies, dict):
        policies = [policies]
    _FLOW["offer_id"] = policies[0]["@id"]
    return catalog


def flow_negotiate() -> dict:
    """Step 5: initiate the contract negotiation. Returns the full negotiation response."""
    consumer, provider = _FLOW["consumer"], _FLOW["provider"]
    body = json.loads(consumer.negotiate(provider, _FLOW["offer_id"], _FLOW["asset_id"]).data)
    _FLOW["negotiation_id"] = body["@id"]
    return body


def flow_poll_negotiation(*, poll_interval: float = 2, poll_timeout: float = 30) -> dict:
    """Step 6: poll until the negotiation is finalized. Returns the full negotiation model."""
    consumer = _FLOW["consumer"]
    deadline = time.time() + poll_timeout
    while time.time() < deadline:
        neg = consumer.get_negotiation(_FLOW["negotiation_id"])
        if neg.state == "FINALIZED":
            _FLOW["agreement_id"] = neg.contract_agreement_id
            return neg.model_dump()
        time.sleep(poll_interval)
    raise TimeoutError("Timed out waiting for negotiation to finalize.")


def flow_start_transfer() -> dict:
    """Step 7: start the HttpData-PULL transfer for the finalized agreement. Returns the full transfer process."""
    consumer, provider = _FLOW["consumer"], _FLOW["provider"]
    tp = consumer.start_pull(provider, _FLOW["agreement_id"])
    _FLOW["transfer_id"] = tp["@id"]
    return tp


def flow_poll_transfer(*, poll_interval: float = 2, poll_timeout: float = 30) -> dict:
    """Step 8: poll until the transfer reaches STARTED. Returns the full transfer process."""
    consumer = _FLOW["consumer"]
    deadline = time.time() + poll_timeout
    while time.time() < deadline:
        transfer = consumer.get_transfer_state(_FLOW["transfer_id"])
        if transfer["state"] == "STARTED":
            return transfer
        time.sleep(poll_interval)
    raise TimeoutError("Timed out waiting for transfer to start.")


def flow_get_edr() -> dict:
    """Step 9: fetch the Endpoint Data Reference for the started transfer."""
    edr = _FLOW["consumer"].get_edr(_FLOW["transfer_id"])
    _FLOW["edr"] = edr
    return edr.model_dump()


def flow_pull_data() -> dict:
    """Step 10: pull the data through the EDR endpoint."""
    consumer = _FLOW["consumer"]
    endpoint, authorization = consumer.edr_endpoint_auth(_FLOW["edr"])
    return consumer.pull_data(endpoint, authorization).json()