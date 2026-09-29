from __future__ import annotations

from .bear_valley import BearValleyProvider


class MACTHealthProvider(BearValleyProvider):
    """Official MACT Health ADP openings limited to Calaveras locations."""

    CID = "42ad6968-0b79-403e-b041-4c894400916b"
    CCID = "19000101_000001"
    COMPANY_NAME = "MACT Health Board"
    SOURCE_KEY = "mact_health"
    DEFAULT_LOCATION = "Calaveras County, CA"
    LOCAL_LOCATION_TERMS = (
        "angels camp",
        "san andreas",
        "valley springs",
        "calaveras",
    )
