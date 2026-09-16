from __future__ import annotations

from .edjoin_calaveras import EDJoinCalaverasProvider


class EDJoinAmadorProvider(EDJoinCalaverasProvider):
    """EDJOIN jobs for all listed Amador County public-school employers."""

    COUNTY_NAME = "Amador County"
    SOURCE_KEY = "edjoin_amador"
    DISTRICTS = [
        {
            "district_id": 54,
            "name": "Amador County Office Of Education",
            "portal": "https://www.edjoin.org/amadorcoe",
        },
        {
            "district_id": 53,
            "name": "Amador County Unified School District",
            "portal": "https://www.edjoin.org/acusd",
        },
    ]
