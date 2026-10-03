import json

from job_agent.providers.mother_lode_employers import (
    CHIPSForestryProvider,
    GoldenSanAndreasProvider,
    InsightManufacturingProvider,
    ResourceConnectionProvider,
)


class Response:
    def __init__(self, *, text="", payload=None):
        self.text = text
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_resource_connection_maps_applicantpro_job(monkeypatch):
    listing = {
        "success": True,
        "data": {
            "jobs": [
                {
                    "id": 42,
                    "title": "Accounting Assistant",
                    "jobUrl": "https://trcac.applicantpro.com/jobs/42",
                    "jobLocation": "San Andreas, CA, USA",
                    "employmentType": "Full Time",
                    "startDateRef": "Sep 29, 2026",
                    "endDateRef": "Nov 28, 2026",
                    "orgTitle": "Administration",
                    "minSalary": "20.00",
                    "maxSalary": "24.00",
                    "payTypeFrame": "per hour",
                }
            ]
        },
    }
    detail = {
        "success": True,
        "data": {
            "advertisingDescriptionHtml": "<p>Maintain accounts payable.</p>",
            "startDateRef": "29-Sep-2026",
            "endDateRef": "28-Nov-2026",
        },
    }
    provider = ResourceConnectionProvider()

    def get(url, **kwargs):
        return Response(payload=detail if "job-details" in url else listing)

    monkeypatch.setattr(provider.session, "get", get)
    jobs = provider.search(role="accounting", location="Calaveras")

    assert len(jobs) == 1
    assert jobs[0].source == "resource_connection"
    assert jobs[0].description == "Maintain accounts payable."
    assert jobs[0].metadata["salary"] == "$20.00 - $24.00 per hour"


def test_golden_san_andreas_uses_apploi_json_ld(monkeypatch):
    snippet = '''document.write('<div class="jobs-card" data-jobtype="PartTime">
      <a class="job-link" href="https://apply-jobs.apploi.com/job/1932911?src=test">Medical Records Assistant</a>
    </div>')'''
    posting = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": "Medical Records Assistant",
        "description": "<p>Maintain resident records and protect confidentiality.</p>",
        "datePosted": "2026-09-22",
        "employmentType": "PART_TIME",
        "jobLocation": {
            "address": {"addressLocality": "San Andreas", "addressRegion": "CA"}
        },
    }
    provider = GoldenSanAndreasProvider()

    def get(url, **kwargs):
        if "apploi.click" in url:
            return Response(text=snippet)
        return Response(
            text=f'<script type="application/ld+json">{json.dumps(posting)}</script>'
        )

    monkeypatch.setattr(provider.session, "get", get)
    jobs = provider.search(role="medical records", location="Calaveras")

    assert len(jobs) == 1
    assert jobs[0].provider_job_id == "1932911"
    assert jobs[0].source == "golden_san_andreas"
    assert jobs[0].location == "San Andreas, CA"


def test_golden_san_andreas_normalizes_multiple_employment_types(monkeypatch):
    snippet = '''document.write('<div class="jobs-card" data-jobtype="PartTime">
      <a class="job-link" href="https://apply-jobs.apploi.com/job/1932911">Assistant</a>
    </div>')'''
    posting = {
        "@type": "JobPosting",
        "title": "Assistant",
        "employmentType": ["FULL_TIME", "PART_TIME"],
    }
    provider = GoldenSanAndreasProvider()

    def get(url, **kwargs):
        if "apploi.click" in url:
            return Response(text=snippet)
        return Response(
            text=f'<script type="application/ld+json">{json.dumps(posting)}</script>'
        )

    monkeypatch.setattr(provider.session, "get", get)
    job = provider.search(role="", location="", results_per_page=1)[0]
    assert job.employment_type == "FULL_TIME, PART_TIME"


def test_insight_manufacturing_uses_local_adp_configuration():
    provider = InsightManufacturingProvider()

    assert provider.COMPANY_NAME == "Insight Manufacturing"
    assert provider.SOURCE_KEY == "insight_manufacturing"
    assert provider.CID == "824005bc-0b5e-446f-847a-33863ec245d7"
    assert "murphys" in provider.LOCAL_LOCATION_TERMS


def test_chips_does_not_invent_a_generic_opening(monkeypatch):
    provider = CHIPSForestryProvider()
    monkeypatch.setattr(
        provider.session,
        "get",
        lambda *args, **kwargs: Response(text="NOW HIRING! APPLY NOW"),
    )

    assert provider.search(role="forestry", location="West Point") == []
