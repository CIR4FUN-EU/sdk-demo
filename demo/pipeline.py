"""Repository + registry client construction for the DPP web app.
Repository and registry are the REAL services (no local mock)."""

from dpp_sdk import validate_dpp4fun
from dpp_sdk.clients import DppRegistryClient, DppRepoClient
from dpp_sdk.dpp4fun import Dpp4FunJsonCodec


def make_clients(repo_url: str, registry_url: str) -> tuple[DppRepoClient, DppRegistryClient]:
    """Build the real repository + registry clients used by the web app."""
    repo = DppRepoClient(repo_url, codec=Dpp4FunJsonCodec(), validator=validate_dpp4fun)
    registry = DppRegistryClient(registry_url)
    return repo, registry
