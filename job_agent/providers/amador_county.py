from __future__ import annotations

from .calaveras_county import CalaverasCountyProvider


class AmadorCountyProvider(CalaverasCountyProvider):
    """Official Amador County GovernmentJobs/NEOGOV feed."""

    FEED_URL = (
        "https://www.governmentjobs.com/"
        "SearchEngine/JobsFeed?agency=amadorgov"
    )
    COUNTY_NAME = "Amador County"
    SOURCE_KEY = "amador_county"
