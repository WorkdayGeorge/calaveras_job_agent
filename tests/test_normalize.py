\
from datetime import datetime, timedelta, timezone
import unittest

from job_agent.normalize import normalize_job, is_local_location
from job_agent.schemas import RawJob

SETTINGS = {
    "location": {
        "primary": "Calaveras County, CA",
        "allowed_localities": ["Murphys", "Angels Camp", "Avery", "San Andreas"]
    },
    "fresh_job_window_minutes": 60,
}

class NormalizeTests(unittest.TestCase):
    def test_local_murphys(self):
        self.assertTrue(is_local_location("Murphys, CA", SETTINGS))

    def test_nonlocal(self):
        self.assertFalse(is_local_location("Sonora, CA", SETTINGS))

    def test_fresh_job(self):
        now = datetime.now(timezone.utc)
        raw = RawJob(
            provider_job_id="1",
            title="Bookkeeper",
            company="X",
            location="Murphys, CA",
            employment_type="part_time",
            description="Excel and bookkeeping",
            posted_at=now - timedelta(minutes=20),
            apply_url="https://example.com/1",
            source="test",
        )
        j = normalize_job(raw, SETTINGS, now=now)
        self.assertEqual(j.freshness_status, "verified_fresh")
        self.assertEqual(j.posted_time_confidence, "verified")

if __name__ == "__main__":
    unittest.main()
