from job_agent.source_catalog import get_employer_coverage


def test_employer_coverage_summary_matches_inventory():
    employers, summary = get_employer_coverage()

    assert summary["total"] == len(employers)
    assert summary["automated"] == sum(
        employer["status"] in {"integrated", "covered"}
        for employer in employers
    )
    assert summary["high_priority"] == sum(
        employer["priority"] == "High"
        and employer["status"] not in {"integrated", "covered"}
        for employer in employers
    )
    assert summary["manual"] > 0


def test_employer_coverage_has_unique_names_and_official_links():
    employers, _ = get_employer_coverage()
    names = [employer["name"] for employer in employers]

    assert len(names) == len(set(names))
    assert all(employer["url"].startswith("https://") for employer in employers)
    assert {employer["status"] for employer in employers} <= {
        "integrated",
        "covered",
        "candidate",
        "gap",
        "manual",
    }
