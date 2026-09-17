from __future__ import annotations

from .calaveras_county import CalaverasCountyProvider


class TuolumneUtilitiesProvider(CalaverasCountyProvider):
    """Official Tuolumne Utilities District GovernmentJobs/NEOGOV feed."""

    FEED_URL = (
        "https://www.governmentjobs.com/"
        "SearchEngine/JobsFeed?agency=tudwater"
    )
    COUNTY_NAME = "Tuolumne County"
    COMPANY_NAME = "Tuolumne Utilities District"
    SOURCE_KEY = "tuolumne_utilities"
    CAREERS_URL = "https://tudwater.com/careers/job-openings/"

    def search(
        self,
        *,
        role: str,
        location: str,
        results_per_page: int = 25,
    ):
        # The district's pool is small. Let the existing evaluator score every
        # opening rather than dropping transferable work by keyword.
        if self._cached_jobs is None:
            self._cached_jobs = self._load_feed()
        return self._cached_jobs[:results_per_page]
