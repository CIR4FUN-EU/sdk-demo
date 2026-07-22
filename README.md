# data-space-dpp-demo

## Demo scope

End-to-end Digital Product Passport (DPP) flow against **real components and real
clients** — no mocks. Five steps:

1. **Pull asset** — fetch product data across the data space via the real EDC
   connectors (provider ↔ consumer).
2. **Build** — assemble a `Dpp4Fun` passport from the asset plus baked-in master
   data, using the `dpp-sdk` models.
3. **Validate** — check the passport against the `dpp-sdk` schema.
4. **Store** — persist it in the real **DPP repository** via the `dpp-sdk`
   repository client.
5. **Register** — announce it at the real **DPP registry** via the `dpp-sdk`
   registry client.

The diagram below shows the demo app's three clients (EDC, repository, registry),
the running components each talks to, and where every piece is pulled from.

```mermaid
flowchart LR
    subgraph app["demo-app"]
        edc["edc-client"]
        repoc["dpp-sdk<br/>repository client"]
        regc["dpp-sdk<br/>registry client"]
    end

    edc -->|pull asset| conn["EDC connectors<br/>(provider / consumer)"]
    repoc -->|store DPP| repo["dpp-repo-api"]
    regc -->|register DPP| reg["dpp-registry-api"]

    edcgh(["github.com/CIR4FUN-EU/<br/>python-edc-client"]) -.-> edc
    pypi(["PyPI · dpp-sdk"]) -.-> repoc
    pypi -.-> regc
    ghcr(["ghcr.io/cir4fun-eu"]) -.image.-> repo
    ghcr -.image.-> reg
    samples(["Eclipse EDC Samples<br/>edc-samples-connector.jar"]) -.jar.-> conn

    classDef src fill:#eef,stroke:#88a,stroke-dasharray:3;
    class edcgh,pypi,ghcr,samples src;
```

## Ports

| Component | Host port | Container port |
|-----------|-----------|----------------|
| `demo-app` (web UI) | 8000 | 8000 |
| `dpp-repo-api` | 18080 | 8080 |
| `dpp-registry-api` | 18081 | 8081 |
| `dpp-repo-db` (Postgres) | 5433 | 5432 |
| `dpp-registry-db` (Postgres) | 5434 | 5432 |
| `provider` connector | 19191–19195, 19291 | same |
| `consumer` connector | 29191–29195, 29291 | same |

## Run (Docker, one click)

**Prerequisite:** Docker Desktop (or the Docker daemon) must be installed and
**running**. The repo/registry images are public on
[ghcr.io/cir4fun-eu](https://github.com/orgs/CIR4FUN-EU/packages) — no login needed.

Build and start everything:

```bash
docker compose -f docker-compose.all.yml up -d --build
```

Stop the containers:

```bash
docker compose -f docker-compose.all.yml stop
```

Stop and delete containers + volumes:

```bash
docker compose -f docker-compose.all.yml down -v
```

Then open <http://localhost:8000>.
