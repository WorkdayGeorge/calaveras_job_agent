from __future__ import annotations

from .calaveras_county import CalaverasCountyProvider


class AmadorWaterAgencyProvider(CalaverasCountyProvider):
    """Official Amador Water Agency GovernmentJobs/NEOGOV feed."""

    FEED_URL = (
        "https://www.governmentjobs.com/"
        "SearchEngine/JobsFeed?agency=amadorwater"
    )
    COUNTY_NAME = "Amador County"
    COMPANY_NAME = "Amador Water Agency"
    SOURCE_KEY = "amador_water"
    CAREERS_URL = "https://amadorwater.gov/careers/current-job-openings/"

    def search(
        self,
        *,
        role: str,
        location: str,
        results_per_page: int = 25,
    ):
        # The agency's pool is small. Let the existing evaluator score every
        # opening rather than dropping transferable work by keyword.
        if self._cached_jobs is None:
            self._cached_jobs = self._load_feed()
        return self._cached_jobs[:results_per_page]
