from __future__ import annotations

from .edjoin_calaveras import EDJoinCalaverasProvider


class EDJoinTuolumneProvider(EDJoinCalaverasProvider):
    """EDJOIN jobs for all listed Tuolumne County public-school employers."""

    COUNTY_NAME = "Tuolumne County"
    SOURCE_KEY = "edjoin_tuolumne"
    DISTRICTS = [
        {"district_id": 1052, "name": "Columbia Union School District", "portal": "https://www.edjoin.org/ColumbiaUnion"},
        {"district_id": 1051, "name": "Curtis Creek School District", "portal": "https://www.edjoin.org/CurtisCreek"},
        {"district_id": 5063, "name": "Gold Rush Charter School", "portal": "https://www.edjoin.org/Home/Jobs?districtID=5063"},
        {"district_id": 1050, "name": "Jamestown School District", "portal": "https://www.edjoin.org/jsd"},
        {"district_id": 1056, "name": "Sonora Elementary School District", "portal": "https://www.edjoin.org/SonoraElementary"},
        {"district_id": 1045, "name": "Sonora Union High School District", "portal": "https://www.edjoin.org/sonorahs"},
        {"district_id": 1049, "name": "Soulsbyville School District", "portal": "https://www.edjoin.org/soulsbyvilleschool"},
        {"district_id": 1048, "name": "Summerville Elementary School District", "portal": "https://www.edjoin.org/SummervilleElementary"},
        {"district_id": 1046, "name": "Summerville Union High School", "portal": "https://www.edjoin.org/summbears"},
        {"district_id": 1055, "name": "Tuolumne County Superintendent of Schools", "portal": "https://www.edjoin.org/tcsos"},
        {"district_id": 1047, "name": "Twain Harte School District", "portal": "https://www.edjoin.org/twainharte"},
    ]
