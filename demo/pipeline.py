"""End-to-end DPP pipeline: fetch -> build -> validate -> store -> register.
Repository and registry are the REAL services (no local mock)."""

from dpp_sdk import validate_dpp4fun
from dpp_sdk.clients import DppRegistryClient, DppRepoClient, RegisterDppRequest
from dpp_sdk.dpp4fun import Dpp4FunJsonCodec

from . import build, connector


def make_clients(repo_url: str, registry_url: str) -> tuple[DppRepoClient, DppRegistryClient]:
    """Build the real repository + registry clients. Shared by run() and the web app."""
    repo = DppRepoClient(repo_url, codec=Dpp4FunJsonCodec(), validator=validate_dpp4fun)
    registry = DppRegistryClient(registry_url)
    return repo, registry


def run(repo_url: str, registry_url: str, operator_id: str, asset_id: str, edc_host: str) -> str:
    """Run the full flow against live repository + registry. Returns the dppId."""
    asset_data = connector.fetch_asset_properties(asset_id, host=edc_host)

    dpp = build.build_dpp(asset_data)
    validate_dpp4fun(dpp)

    repo, registry = make_clients(repo_url, registry_url)
    repo.health_check()
    registry.health_check()

    dpp_id = repo.create_dpp(dpp).dppId
    registry.post_new_dpp_to_registry(
        RegisterDppRequest(
            productIdentifier=str(dpp.uniqueProductIdentifier),
            dppIdentifier=dpp_id,
            operatorIdentifier=operator_id,
            repoUrl=repo_url,
        )
    )
    return dpp_id


def run_no_connector(repo_url: str, registry_url: str, operator_id: str) -> str:
    """Same flow as run() but without the data-space connector fetch."""
    dpp = build.build_dpp({})
    validate_dpp4fun(dpp)

    repo, registry = make_clients(repo_url, registry_url)
    repo.health_check()
    registry.health_check()

    dpp_id = repo.create_dpp(dpp).dppId
    registry.post_new_dpp_to_registry(
        RegisterDppRequest(
            productIdentifier=str(dpp.uniqueProductIdentifier),
            dppIdentifier=dpp_id,
            operatorIdentifier=operator_id,
            repoUrl=repo_url,
        )
    )
    return dpp_id
