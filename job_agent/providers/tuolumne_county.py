from __future__ import annotations

from .calaveras_county import CalaverasCountyProvider


class TuolumneCountyProvider(CalaverasCountyProvider):
    """Official Tuolumne County GovernmentJobs/NEOGOV feed."""

    FEED_URL = (
        "https://www.governmentjobs.com/"
        "SearchEngine/JobsFeed?agency=tuolumnecounty"
    )
    COUNTY_NAME = "Tuolumne County"
    SOURCE_KEY = "tuolumne_county"
