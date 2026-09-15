from job_agent.providers.amador_county import AmadorCountyProvider
from job_agent.providers.tuolumne_county import TuolumneCountyProvider


def test_amador_provider_configuration():
    provider = AmadorCountyProvider()
    assert provider.COUNTY_NAME == "Amador County"
    assert provider.SOURCE_KEY == "amador_county"
    assert "agency=amadorgov" in provider.FEED_URL


def test_tuolumne_provider_configuration():
    provider = TuolumneCountyProvider()
    assert provider.COUNTY_NAME == "Tuolumne County"
    assert provider.SOURCE_KEY == "tuolumne_county"
    assert "agency=tuolumnecounty" in provider.FEED_URL
