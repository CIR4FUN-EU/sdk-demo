"""Assemble a dpp_sdk.Dpp4Fun model from the demo's static product data.

Product master data + bill of materials are baked in here (a real integration
would fetch them from ERP/PLM). The data-space connector, when present, adds
the shared links."""

import random
from datetime import date
from uuid import uuid4

from dpp_sdk import (
    BillOfMaterials,
    Characteristics,
    Component,
    Dimensions,
    Dpp4Fun,
    DppCore,
    Material,
    Nameplate,
    Organization,
    OrganizationRole,
    Part,
    PassportMetadata,
    ProductClassification,
)


def _random_gtin13() -> str:
    """A valid GTIN-13: 12 random digits + mod-10 check digit.
    Fresh each run so re-stores don't 409 against the repo."""
    body = [random.randint(0, 9) for _ in range(12)]
    check = (10 - sum(d * (3 if i % 2 else 1) for i, d in enumerate(body)) % 10) % 10
    return "".join(map(str, body + [check]))


def build_dpp(connector: dict) -> Dpp4Fun:
    """Consolidate the demo product data into one passport.

    The data-space connector (optional) supplies shared links. GTIN/article
    number are randomized per run: the repo keys the DPP on them, so fixed ones
    would 409 on the second store."""
    return Dpp4Fun(
        coreDpp=DppCore(
            passportMetadata=PassportMetadata(
                uniqueProductIdentifier=uuid4(),
                passportUpdateDates=[date.today()],
                externalDocumentationLink=connector.get("uri"),
            ),
            nameplate=Nameplate(
                gtinCode=_random_gtin13(),
                internalArticleNumber=f"CHR-{random.randint(1000, 9999)}",
                uriOfTheProduct=connector.get("uri"),
                manufacturer=Organization(
                    name="Cir4Fun Furniture Co.",
                    role=OrganizationRole.MANUFACTURER,
                ),
            ),
        ),
        classification=ProductClassification(sector="Furniture", category="Seating"),
        characteristics=Characteristics(
            productName="Cir4Fun Oak Dining Chair",
            description="A solid oak dining chair with a water-based lacquer finish, "
                        "designed for circular disassembly and material recovery.",
            brand="Cir4Fun",
            weight=6.8,
            dimensions=Dimensions(width=450.0, height=900.0, depth=520.0, unit="mm"),
        ),
        billOfMaterials=BillOfMaterials(
            materials=[
                Material(name="Solid oak", portion=0.70, mandatory=True),
                Material(name="Water-based lacquer", portion=0.05, mandatory=True),
                Material(name="Woven cane webbing", portion=0.20, mandatory=False),
                Material(name="Steel fixings", portion=0.05, mandatory=False),
            ],
            components=[
                Component(name="Seat frame", reference="SEAT-FRM-04"),
                Component(name="Backrest", reference="BACK-002"),
            ],
            parts=[
                Part(name="M6 hex bolt", mandatory=True),
                Part(name="Felt floor glide", mandatory=False),
            ],
        ),
    )
