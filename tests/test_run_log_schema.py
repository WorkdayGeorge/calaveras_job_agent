from sqlalchemy import Text

from job_agent.models import RunLog


def test_run_log_provider_label_has_no_fixed_length():
    assert isinstance(RunLog.__table__.c.provider.type, Text)
