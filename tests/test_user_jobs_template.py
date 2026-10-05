from pathlib import Path
from types import SimpleNamespace

from starlette.datastructures import URL

from web.app import templates


def test_user_jobs_apply_action_routes_through_application_prep():
    template = Path("web/templates/jobs.html").read_text()

    assert 'href="/jobs/{{ job.id }}/application">Apply</a>' in template
    assert '>Build Resume</a>' not in template
    assert 'href="{{ job.apply_url }}" target="_blank" rel="noopener">Open</a>' not in template
    assert '<th>Status</th>' not in template
    assert 'action="/jobs/{{ job.id }}/status"' not in template
    assert 'name="q" type="search"' in template
    assert "Job title, employer, or location" in template
    assert "Clear category and search" in template
    assert 'name="category"' in template
    assert "All job categories" in template
    assert 'name="arrangement"' in template
    assert 'aria-label="Work arrangements"' in template
    assert 'role="tablist"' in template
    assert 'role="tabpanel"' in template
    assert ">All</a>" in template
    assert '"On-site" if option == "onsite"' in template
    assert 'request.url.include_query_params(arrangement=option)' in template
    assert 'request.url.remove_query_params(\'arrangement\')' in template
    assert template.index('class="work-tabs"') < template.index('id="category"')
    assert template.index('class="work-tabs"') < template.index('id="sort"')
    assert "job.category" in template
    assert "job.work_arrangement" in template


def test_administrator_can_still_view_source_job_posting():
    template = Path("web/templates/jobs.html").read_text()

    assert '>View Job</a>' in template


def test_selected_category_page_renders_clear_link_without_server_error():
    request = SimpleNamespace(
        query_params={},
        url=URL(
            "https://example.test/jobs?arrangement=remote"
            "&category=Accounting%20%26%20Bookkeeping&q=clerk"
        ),
        session={},
    )
    html = templates.env.get_template("jobs.html").render(
        request=request,
        rows=[],
        status_filter=None,
        sort_by="newest_posted",
        search_query="clerk",
        category_options=(
            "Accounting & Bookkeeping",
            "Remote Jobs",
        ),
        selected_category="Accounting & Bookkeeping",
        arrangement_options=("onsite", "hybrid", "remote"),
        selected_arrangement="remote",
        administrator_view=False,
    )

    assert "Clear category and search" in html
    assert "arrangement=remote" in html
