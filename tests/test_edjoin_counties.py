from job_agent.providers.edjoin_amador import EDJoinAmadorProvider
from job_agent.providers.edjoin_calaveras import EDJoinCalaverasProvider
from job_agent.providers.edjoin_tuolumne import EDJoinTuolumneProvider


class Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_existing_calaveras_configuration_is_preserved():
    provider = EDJoinCalaverasProvider()
    assert provider.COUNTY_NAME == "Calaveras County"
    assert provider.SOURCE_KEY == "edjoin_calaveras"
    assert {item["district_id"] for item in provider.DISTRICTS} == {73, 74}


def test_amador_provider_covers_office_and_unified_district():
    provider = EDJoinAmadorProvider()
    assert provider.COUNTY_NAME == "Amador County"
    assert provider.SOURCE_KEY == "edjoin_amador"
    assert {item["district_id"] for item in provider.DISTRICTS} == {53, 54}


def test_tuolumne_provider_covers_official_edjoin_directory():
    provider = EDJoinTuolumneProvider()
    assert provider.COUNTY_NAME == "Tuolumne County"
    assert provider.SOURCE_KEY == "edjoin_tuolumne"
    assert {item["district_id"] for item in provider.DISTRICTS} == {
        1045, 1046, 1047, 1048, 1049, 1050, 1051, 1052, 1055, 1056, 5063
    }


def test_subclass_maps_county_source_and_unverified_timestamp(monkeypatch):
    provider = EDJoinAmadorProvider()
    payload = {
        "totalPages": 1,
        "data": [
            {
                "postingID": 12345,
                "positionTitle": "Accounting Technician",
                "districtName": "Amador County Unified School District",
                "city": "Jackson",
                "stateName": "California",
                "CreationDate": "/Date(1789516800000)/",
                "postingDate": "9/16/2026",
            }
        ],
    }
    monkeypatch.setattr(provider.session, "get", lambda *args, **kwargs: Response(payload))

    jobs = provider.search(role="accounting", location="Amador County, CA")

    assert len(jobs) == 1
    assert jobs[0].source == "edjoin_amador"
    assert jobs[0].location == "Jackson, CA / Amador County, CA"
    assert jobs[0].posted_at is None
    assert jobs[0].metadata["creation_date_ms"] == 1789516800000
