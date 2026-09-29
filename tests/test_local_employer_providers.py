from job_agent.providers.calaveras_court import CalaverasCourtProvider
from job_agent.providers.local_career_pages import AngelsCampProvider, IronstoneProvider
from job_agent.providers.mact_health import MACTHealthProvider


class Response:
    def __init__(self, text=""):
        self.text = text

    def raise_for_status(self):
        return None


def test_city_provider_parses_only_current_opportunities(monkeypatch):
    html = """
    <table aria-label="Human Resources - Current Opportunities">
      <thead><tr><th>Job Position</th><th>Details</th><th>Description</th><th>Closing Date</th><th>Application Link</th></tr></thead>
      <tbody><tr><td>Accounting Technician</td><td><a href="/details.pdf">Details</a></td><td>Job Description</td><td>Continuous</td><td><a href="https://apply.example/job">Apply</a></td></tr></tbody>
    </table>
    <table><tr><td>Not an opening</td></tr></table>
    """
    provider = AngelsCampProvider()
    monkeypatch.setattr(provider.session, "get", lambda *args, **kwargs: Response(html))

    jobs = provider.search(role="accounting", location="Angels Camp")

    assert len(jobs) == 1
    assert jobs[0].title == "Accounting Technician"
    assert jobs[0].apply_url == "https://apply.example/job"
    assert jobs[0].source == "angels_camp"


def test_ironstone_provider_deduplicates_responsive_page_sections(monkeypatch):
    html = """
    <h2>AVAILABLE POSITIONS</h2>
    <h2>Line Cook</h2><p>Prepare food for winery events.</p>
    <h2>Line Cook</h2><p>Prepare food for winery events.</p>
    <h2>Interested Applicants</h2><p>Apply below.</p>
    """
    provider = IronstoneProvider()
    monkeypatch.setattr(provider.session, "get", lambda *args, **kwargs: Response(html))

    jobs = provider.search(role="cook", location="Murphys")

    assert len(jobs) == 1
    assert jobs[0].title == "Line Cook"
    assert jobs[0].source == "ironstone"


def test_mact_provider_uses_calaveras_adp_locations():
    provider = MACTHealthProvider()

    assert provider.COMPANY_NAME == "MACT Health Board"
    assert provider.SOURCE_KEY == "mact_health"
    assert "angels camp" in provider.LOCAL_LOCATION_TERMS
    assert "sonora" not in provider.LOCAL_LOCATION_TERMS


def test_court_provider_uses_separate_neogov_agency():
    provider = CalaverasCourtProvider()

    assert "agency=calaverascourts" in provider.FEED_URL
    assert provider.SOURCE_KEY == "calaveras_court"
