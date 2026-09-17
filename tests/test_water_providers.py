from job_agent.providers.amador_water import AmadorWaterAgencyProvider
from job_agent.providers.tuolumne_utilities import TuolumneUtilitiesProvider


def test_amador_water_configuration():
    provider = AmadorWaterAgencyProvider()
    assert provider.COUNTY_NAME == "Amador County"
    assert provider.COMPANY_NAME == "Amador Water Agency"
    assert provider.SOURCE_KEY == "amador_water"
    assert "agency=amadorwater" in provider.FEED_URL


def test_tuolumne_utilities_configuration():
    provider = TuolumneUtilitiesProvider()
    assert provider.COUNTY_NAME == "Tuolumne County"
    assert provider.COMPANY_NAME == "Tuolumne Utilities District"
    assert provider.SOURCE_KEY == "tuolumne_utilities"
    assert "agency=tudwater" in provider.FEED_URL


def test_tuolumne_utilities_maps_official_feed(monkeypatch):
    provider = TuolumneUtilitiesProvider()
    xml = b"""<?xml version="1.0" encoding="utf-8"?>
    <rss xmlns:job="http://www.neogov.com/namespaces/JobListing">
      <channel><item>
        <title>Engineering Services Technician</title>
        <link>https://www.governmentjobs.com/careers/tudwater/jobs/5406114</link>
        <description>&lt;p&gt;Support engineering projects.&lt;/p&gt;</description>
        <job:jobId>5406114</job:jobId>
        <job:location>Sonora</job:location>
        <job:jobType>Full-Time</job:jobType>
        <job:advertiseFromDateUTC>2026-09-10T00:00:00Z</job:advertiseFromDateUTC>
      </item></channel>
    </rss>"""

    class Response:
        content = xml

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "job_agent.providers.calaveras_county.requests.get",
        lambda *args, **kwargs: Response(),
    )

    jobs = provider.search(role="accounting", location="Tuolumne County, CA")

    assert len(jobs) == 1
    assert jobs[0].provider_job_id == "5406114"
    assert jobs[0].company == "Tuolumne Utilities District"
    assert jobs[0].location == "Sonora, Tuolumne County, CA"
    assert jobs[0].source == "tuolumne_utilities"
    assert jobs[0].posted_at is None
    assert "not verified" in jobs[0].metadata["timestamp_note"]
