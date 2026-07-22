"""CLI entry point: python -m demo

Config is loaded from a .env file (see .env.example): DPP_REPO_BASE_URL,
DPP_REGISTRY_BASE_URL, DPP_OPERATOR_ID, EDC_HOST, EDC_ASSET_ID. CLI args
override the file."""

import argparse
import os

from dotenv import load_dotenv

from . import pipeline


def main() -> None:
    load_dotenv()  # populate os.environ from .env
    p = argparse.ArgumentParser(description="Create, store and register a DPP end-to-end.")
    p.add_argument("--repo-url", default=os.getenv("DPP_REPO_BASE_URL"))
    p.add_argument("--registry-url", default=os.getenv("DPP_REGISTRY_BASE_URL"))
    p.add_argument("--operator-id", default=os.getenv("DPP_OPERATOR_ID"))
    p.add_argument("--edc-host", default=os.getenv("EDC_HOST", "http://localhost"))
    p.add_argument("--asset-id", default=os.getenv("EDC_ASSET_ID", "demo-asset"))
    args = p.parse_args()

    if not args.repo_url or not args.registry_url or not args.operator_id:
        p.error("repo/registry URLs and operator id required (--repo-url/--registry-url/--operator-id or env vars)")

    dpp_id = pipeline.run(
        args.repo_url, args.registry_url, args.operator_id, args.asset_id, args.edc_host
    )
    print(f"DPP stored and registered. dppId={dpp_id}")


if __name__ == "__main__":
    main()
