\
import os
import tempfile
import unittest

class V2SmokeTests(unittest.TestCase):
    def test_notification_buckets(self):
        from job_agent.notify import notification_bucket
        settings = {
            "immediate_alert_score": 75,
            "minimum_fit_score": 60,
            "timestamp_policy": {"allow_unverified_current_jobs_in_digest": True},
        }
        self.assertEqual(
            notification_bucket(
                {"freshness_status": "verified_fresh"},
                {"fit_score": 80},
                settings,
            ),
            "immediate",
        )
        self.assertEqual(
            notification_bucket(
                {"freshness_status": "unverified"},
                {"fit_score": 80},
                settings,
            ),
            "high_priority_digest",
        )

if __name__ == "__main__":
    unittest.main()
