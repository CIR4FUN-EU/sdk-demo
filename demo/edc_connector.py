"""
A single config-driven EDC connector client. The demo helpers are methods; the
two flavors (EDC samples vs construct-x) are produced by the `samples()` /
`construct_x()` classmethod presets — same code, different config, no inheritance.

    provider = Connector.samples(PROVIDER_MGMT, PROVIDER_ID, PROVIDER_PROTOCOL)
    consumer = Connector.samples(CONSUMER_MGMT, CONSUMER_ID, CONSUMER_PROTOCOL)
    provider.create_asset("asset-1", "https://example.org/data")
    catalog = consumer.fetch_catalog(provider)            # counterparty = a Connector
"""

import json
import os
import time

import httpx
import edc_client
from dotenv import load_dotenv
from edc_client.api_client import ApiClient
from edc_client.rest import ApiException  # noqa: F401 — re-exported for callers

_EDC_CTX = {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"}


class Connector:
    def __init__(
        self,
        management_url: str,
        *,
        participant_id: str,
        protocol_address: str,
        dsp_protocol: str = "dataspace-protocol-http:2025-1",
        api_key: str = None,
        asset_auth: dict = None,
        edr_remap: dict = None,
    ):
        cfg = edc_client.Configuration(host=management_url)
        if api_key:
            self.client = ApiClient(cfg, header_name="x-api-key", header_value=api_key)
        else:
            self.client = ApiClient(cfg)
        self.participant_id = participant_id          # DSP id others use to reach us
        self.protocol_address = protocol_address      # DSP address others use to reach us
        self.dsp_protocol = dsp_protocol
        self.asset_auth = asset_auth or {}            # extra dataAddress fields
        self.edr_remap = edr_remap or {}              # docker->host endpoint substitutions

    # --- presets ---

    @classmethod
    def samples(cls, management_url, participant_id, protocol_address):
        """EDC samples connector: DSP 2025-1, no management auth, no remap."""
        return cls(
            management_url,
            participant_id=participant_id,
            protocol_address=protocol_address,
            dsp_protocol="dataspace-protocol-http:2025-1",
        )

    @classmethod
    def construct_x(cls, management_url, participant_id, protocol_address, api_key):
        """construct-x testbed: DSP v08, x-api-key auth, authed assets, EDR docker remap."""
        return cls(
            management_url,
            participant_id=participant_id,
            protocol_address=protocol_address,
            dsp_protocol="dataspace-protocol-http",
            api_key=api_key,
            asset_auth={
                "proxyMethod": "true",
                "proxyBody": "true",
                "authKey": "x-api-key",
                "authCode": "someAuthCode",
            },
            edr_remap={"provider-dataplane:9500": "localhost:9500"},
        )

    # --- provider-side ---

    def create_asset(self, asset_id, base_url, *, name="Test asset", content_type="application/json", proxy_path=True):
        """Register an HttpData asset. Returns the created asset as a dict."""
        body = edc_client.AssetInputV3.from_dict({
            "@context": _EDC_CTX,
            "@id": asset_id,
            "properties": {"name": name, "contenttype": content_type},
            "dataAddress": {
                "type": "HttpData",
                "name": name,
                "baseUrl": base_url,
                "proxyPath": str(proxy_path).lower(),
                **self.asset_auth,
            },
        })
        raw = edc_client.AssetV3Api(self.client).create_asset_v3_without_preload_content(asset_input_v3=body)
        return json.loads(raw.data)

    def create_policy(self, policy_id, *, permissions=None, prohibitions=None, obligations=None):
        """Create an ODRL policy definition. Empty lists = permissive (no constraints)."""
        body = edc_client.PolicyDefinitionInputV3.from_dict({
            "@context": _EDC_CTX,
            "@id": policy_id,
            "policy": {
                "@context": "http://www.w3.org/ns/odrl.jsonld",
                "@type": "Set",
                "permission": permissions or [],
                "prohibition": prohibitions or [],
                "obligation": obligations or [],
            },
        })
        raw = edc_client.PolicyDefinitionV3Api(self.client).create_policy_definition_v3_without_preload_content(
            policy_definition_input_v3=body)
        return json.loads(raw.data)

    def create_contract_definition(self, contract_definition_id, access_policy_id, contract_policy_id, *, assets_selector=None):
        """
        Link a policy to assets via a contract definition.
        assets_selector filters which assets this applies to — empty matches all.
        Target a specific asset: [{"operandLeft": "https://w3id.org/edc/v0.0.1/ns/id", "operator": "=", "operandRight": "<asset-id>"}]
        """
        body = edc_client.ContractDefinitionInputV3.from_dict({
            "@context": _EDC_CTX,
            "@id": contract_definition_id,
            "accessPolicyId": access_policy_id,
            "contractPolicyId": contract_policy_id,
            "assetsSelector": assets_selector or [],
        })
        raw = edc_client.ContractDefinitionV3Api(self.client).create_contract_definition_v3_without_preload_content(
            contract_definition_input_v3=body)
        return json.loads(raw.data)

    def list_assets(self):
        """Return all assets registered on this connector."""
        raw = edc_client.AssetV3Api(self.client).request_assets_v3_without_preload_content()
        return json.loads(raw.data)

    def remove_asset(self, asset_id):
        """Delete an asset. Fails with 409 if referenced by an agreement or active negotiation."""
        edc_client.AssetV3Api(self.client).remove_asset_v3(asset_id)

    # --- consumer-side (counterparty passed as a provider Connector) ---

    def fetch_catalog(self, provider):
        """Fetch the provider's catalog. Returns raw JSON-LD — datasets under 'dcat:dataset'."""
        body = edc_client.CatalogRequestV3.from_dict({
            "@context": _EDC_CTX,
            "counterPartyId": provider.participant_id,
            "counterPartyAddress": provider.protocol_address,
            "protocol": self.dsp_protocol,
        })
        resp = edc_client.CatalogV3Api(self.client).request_catalog_v3_with_http_info(catalog_request_v3=body)
        return json.loads(resp.raw_data)

    def negotiate(self, provider, offer_id, asset_id):
        """
        Initiate a contract negotiation for a specific offer.
        offer_id comes from the catalog: dataset['odrl:hasPolicy'][0]['@id'].
        Returns the raw HTTP response — json.loads(raw.data)['@id'] is the negotiation ID.
        Poll get_negotiation(neg_id).state until 'FINALIZED', then read .contract_agreement_id.
        """
        body = edc_client.ContractRequestV3.from_dict({
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
                "odrl": "http://www.w3.org/ns/odrl/2/",
                # declare assigner/target as @id terms so a plain string value
                # expands to a node reference (what the connector requires),
                # while still satisfying OfferV3's string typing.
                "assigner": {"@id": "http://www.w3.org/ns/odrl/2/assigner", "@type": "@id"},
                "target":   {"@id": "http://www.w3.org/ns/odrl/2/target",   "@type": "@id"},
            },
            "@type": "ContractRequest",
            "counterPartyId": provider.participant_id,
            "counterPartyAddress": provider.protocol_address,
            "protocol": self.dsp_protocol,
            "policy": {
                "@id": offer_id,
                "@type": "http://www.w3.org/ns/odrl/2/Offer",
                "assigner": provider.participant_id,
                "target": asset_id,
            },
        })
        return edc_client.ContractNegotiationV3Api(self.client).initiate_contract_negotiation_v3_without_preload_content(
            contract_request_v3=body)

    def get_negotiation(self, negotiation_id):
        """Return the full negotiation model. Check .state and .contract_agreement_id."""
        return edc_client.ContractNegotiationV3Api(self.client).get_negotiation_v3(negotiation_id)

    def start_pull(self, provider, agreement_id, *, transfer_type="HttpData-PULL"):
        """
        Start an HttpData-PULL transfer. agreement_id comes from a finalized negotiation.
        Returns the created transfer process dict — ['@id'] is the transfer process ID.
        Poll get_transfer_state() until 'STARTED', then call get_edr().
        """
        body = edc_client.TransferRequestV3.from_dict({
            "@context": _EDC_CTX,
            "@type": "TransferRequestDto",
            "connectorId": provider.participant_id,
            "counterPartyAddress": provider.protocol_address,
            "contractId": agreement_id,
            "protocol": self.dsp_protocol,
            "transferType": transfer_type,
        })
        raw = edc_client.TransferProcessV3Api(self.client).initiate_transfer_process_v3_without_preload_content(
            transfer_request_v3=body)
        return json.loads(raw.data)

    def start_push(self, provider, agreement_id, push_destination_url):
        """Start an HttpData-PUSH transfer. The provider POSTs data to push_destination_url."""
        body = edc_client.TransferRequestV3.from_dict({
            "@context": _EDC_CTX,
            "@type": "TransferRequestDto",
            "connectorId": provider.participant_id,
            "counterPartyAddress": provider.protocol_address,
            "contractId": agreement_id,
            "protocol": self.dsp_protocol,
            "transferType": "HttpData-PUSH",
            "dataDestination": {"type": "HttpData", "baseUrl": push_destination_url},
        })
        return edc_client.TransferProcessV3Api(self.client).initiate_transfer_process_v3(transfer_request_v3=body)

    def get_transfer_state(self, transfer_process_id):
        """Return the full transfer process as a dict. Check ['state'] (e.g. 'STARTED')."""
        raw = edc_client.TransferProcessV3Api(self.client).get_transfer_process_v3_without_preload_content(
            transfer_process_id)
        return json.loads(raw.data)

    def get_edr(self, transfer_process_id):
        """
        Fetch the EDR (Endpoint Data Reference) for a PULL transfer (once 'STARTED').
        Returns a DataAddress model; use edr_endpoint_auth() to extract endpoint + token.
        """
        return edc_client.EDRCacheV3Api(self.client).get_edr_entry_data_address_v3(transfer_process_id)

    def edr_endpoint_auth(self, edr):
        """Pull endpoint + authorization from an EDR (plain or namespaced keys), applying edr_remap."""
        props = edr.model_dump()
        extra = props.get("additional_properties", {}) or {}
        ns = "https://w3id.org/edc/v0.0.1/ns/"
        endpoint = props.get("endpoint") or extra.get("endpoint") or extra.get(ns + "endpoint")
        authorization = props.get("authorization") or extra.get("authorization") or extra.get(ns + "authorization")
        for docker_host, local_host in self.edr_remap.items():
            if endpoint:
                endpoint = endpoint.replace(docker_host, local_host)
        return endpoint, authorization

    @staticmethod
    def pull_data(endpoint, authorization):
        """GET data from the EDR endpoint. Raises on non-2xx."""
        resp = httpx.get(endpoint, headers={"Authorization": authorization})
        resp.raise_for_status()
        return resp

    # --- end-to-end composite ---

    def negotiate_and_transfer(self, provider, asset_id, *, poll_interval=2, poll_timeout=16):
        """
        Full PULL flow: catalog → negotiate → poll agreement → transfer → poll STARTED → fetch data.
        Returns the httpx.Response from the data plane.
        Raises ValueError if asset_id not in catalog, TimeoutError if polling exceeds poll_timeout.
        """
        catalog = self.fetch_catalog(provider)
        datasets = catalog.get("dcat:dataset") or catalog.get("dataset", [])
        if isinstance(datasets, dict):
            datasets = [datasets]
        dataset = next((d for d in datasets if d.get("@id") == asset_id), None)
        if not dataset:
            raise ValueError(f"Asset '{asset_id}' not in catalog. Available: {[d.get('@id') for d in datasets]}")
        policies = dataset.get("odrl:hasPolicy") or dataset.get("hasPolicy", [])
        if isinstance(policies, dict):
            policies = [policies]
        offer_id = policies[0]["@id"]

        neg_id = json.loads(self.negotiate(provider, offer_id, asset_id).data)["@id"]

        deadline = time.time() + poll_timeout
        agreement_id = None
        while time.time() < deadline:
            neg = self.get_negotiation(neg_id)
            if neg.state == "FINALIZED":
                agreement_id = neg.contract_agreement_id
                break
            time.sleep(poll_interval)
        else:
            raise TimeoutError("Timed out waiting for negotiation to finalize.")

        tp_id = self.start_pull(provider, agreement_id)["@id"]

        deadline = time.time() + poll_timeout
        while time.time() < deadline:
            if self.get_transfer_state(tp_id)["state"] == "STARTED":
                endpoint, authorization = self.edr_endpoint_auth(self.get_edr(tp_id))
                return self.pull_data(endpoint, authorization)
            time.sleep(poll_interval)
        raise TimeoutError("Timed out waiting for transfer to start.")


# --- flavor switching: set FLAVOR=samples|construct_x (default samples) ---

def active_flavor() -> str:
    return os.getenv("FLAVOR", "samples")


def load_env() -> str:
    """Load demo/.env.<FLAVOR> if it exists, else demo/.env. Returns the active flavor."""
    flavor = active_flavor()
    base = os.path.dirname(os.path.abspath(__file__))
    specific = os.path.join(base, f".env.{flavor}")
    load_dotenv(specific if os.path.exists(specific) else os.path.join(base, ".env"))
    return flavor


def example_connector(role: str) -> "Connector":
    """Build a Connector for role 'PROVIDER' or 'CONSUMER' from env + the active flavor."""
    mgmt = os.environ[f"{role}_MANAGEMENT"]
    participant_id = os.environ[f"{role}_ID"]
    protocol_address = os.getenv(f"{role}_PROTOCOL", "")
    if active_flavor() == "construct_x":
        return Connector.construct_x(mgmt, participant_id, protocol_address, os.environ[f"{role}_API_KEY"])
    return Connector.samples(mgmt, participant_id, protocol_address)

