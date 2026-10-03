import json
from datetime import datetime, timezone
from types import SimpleNamespace

import openai
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from job_agent.db import Base
from job_agent.models import User, UserSearchTerm
from job_agent.resume_search_terms import (
    normalize_resume_search_terms,
    propose_search_terms_from_resume,
)
from job_agent.user_search import add_resume_search_terms


def test_resume_search_term_proposal_returns_clean_job_phrases(monkeypatch):
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_text=json.dumps([
            " Bookkeeper ",
            "Accounts Payable Specialist",
            "bookkeeper",
            "this phrase has far too many words to be useful as a search term",
        ]))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda api_key: SimpleNamespace(responses=SimpleNamespace(create=create)),
    )

    result = propose_search_terms_from_resume(
        "Processed invoices and reconciled accounts.",
        ["Accounting Clerk"],
    )

    assert result == ["Bookkeeper", "Accounts Payable Specialist"]
    payload = json.loads(captured["input"])
    assert payload["existing_terms"] == ["Accounting Clerk"]


def test_resume_terms_are_additive_and_preserve_existing_state():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    now = datetime.now(timezone.utc)
    with Session() as session:
        user = User(
            id="user-1",
            email="user@example.com",
            display_name="Test User",
            password_hash="hash",
            role="user",
            status="active",
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.add(UserSearchTerm(
            user_id=user.id,
            term="Bookkeeper",
            enabled=False,
            created_at=now,
        ))
        session.commit()

        added = add_resume_search_terms(
            session,
            user.id,
            ["bookkeeper", "Accounts Payable Specialist", "Accounting Clerk"],
        )

        terms = session.scalars(
            select(UserSearchTerm).where(UserSearchTerm.user_id == user.id)
        ).all()
        by_name = {term.term: term for term in terms}
        assert added == ["Accounts Payable Specialist", "Accounting Clerk"]
        assert by_name["Bookkeeper"].enabled is False
        assert len(terms) == 3


def test_normalize_resume_search_terms_limits_length_and_duplicates():
    result = normalize_resume_search_terms([
        "Customer Service Representative",
        "customer service representative",
        123,
        "x" * 101,
    ])
    assert result == ["Customer Service Representative"]
