from __future__ import annotations

from .calaveras_county import CalaverasCountyProvider


class CalaverasCourtProvider(CalaverasCountyProvider):
    """Official Calaveras Superior Court NEOGOV feed."""

    FEED_URL = (
        "https://www.governmentjobs.com/"
        "SearchEngine/JobsFeed?agency=calaverascourts"
    )
    COMPANY_NAME = "Superior Court of California, County of Calaveras"
    SOURCE_KEY = "calaveras_court"
