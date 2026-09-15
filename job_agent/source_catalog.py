from __future__ import annotations

from .config import env

JOB_SOURCES = [
    {
        "key": "adzuna",
        "name": "Adzuna",
        "type": "Job aggregator",
        "description": "Broad job search source used to find additional local openings.",
        "links": [
            {"label": "Adzuna", "url": "https://www.adzuna.com/"}
        ],
    },
    {
        "key": "calaveras_county",
        "name": "Calaveras County Government Jobs",
        "type": "Local government",
        "description": "Official Calaveras County job postings hosted by GovernmentJobs/NEOGOV.",
        "links": [
            {"label": "GovernmentJobs", "url": "https://www.governmentjobs.com/"}
        ],
    },
    {
        "key": "amador_county",
        "name": "Amador County Government Jobs",
        "type": "Local government",
        "description": "Official Amador County job postings hosted by GovernmentJobs/NEOGOV.",
        "links": [
            {"label": "Amador County Careers", "url": "https://www.governmentjobs.com/careers/amadorgov"}
        ],
    },
    {
        "key": "tuolumne_county",
        "name": "Tuolumne County Government Jobs",
        "type": "Local government",
        "description": "Official Tuolumne County job postings hosted by GovernmentJobs/NEOGOV.",
        "links": [
            {"label": "Tuolumne County Careers", "url": "https://www.governmentjobs.com/careers/tuolumnecounty"}
        ],
    },
    {
        "key": "calcareers",
        "name": "CalCareers",
        "type": "State government",
        "description": "California state job openings through the official CalCareers site.",
        "links": [
            {"label": "CalCareers", "url": "https://calcareers.ca.gov/"}
        ],
    },
    {
        "key": "commonspirit",
        "name": "CommonSpirit Health / Mark Twain Medical Center",
        "type": "Healthcare",
        "description": "CommonSpirit Health careers, including local healthcare openings.",
        "links": [
            {"label": "CommonSpirit Careers", "url": "https://www.commonspirit.careers/"}
        ],
    },
    {
        "key": "bear_valley",
        "name": "Bear Valley Mountain Resort",
        "type": "Local employer",
        "description": "Bear Valley Mountain Resort career openings hosted through ADP Workforce Now.",
        "links": [
            {"label": "Bear Valley Careers", "url": "https://workforcenow.adp.com/mascsr/default/"}
        ],
    },
    {
        "key": "ccwd",
        "name": "Calaveras County Water District",
        "type": "Local public agency",
        "description": "Official CCWD job opportunities.",
        "links": [
            {"label": "CCWD Job Opportunities", "url": "https://www.ccwd.org/job-opportunities"}
        ],
    },
    {
        "key": "edjoin_calaveras",
        "name": "EDJOIN - Calaveras Schools",
        "type": "Education",
        "description": "Public school jobs from Calaveras County Office of Education and Calaveras Unified School District.",
        "links": [
            {"label": "Calaveras County Office of Education", "url": "https://www.edjoin.org/calaverascoe"},
            {"label": "Calaveras Unified School District", "url": "https://www.edjoin.org/calaverasusd"}
        ],
    },
    {
        "key": "adventist_health",
        "name": "Adventist Health",
        "type": "Healthcare",
        "description": "Official Adventist Health careers for Sonora and nearby foothill locations.",
        "links": [
            {"label": "Adventist Health Careers", "url": "https://careers.adventisthealth.org/"}
        ],
    },
    {
        "key": "pge",
        "name": "Pacific Gas and Electric Company (PG&E)",
        "type": "Utility",
        "description": "Official PG&E careers for Calaveras County and the surrounding Sierra foothills.",
        "links": [
            {"label": "PG&E Careers", "url": "https://jobs.pge.com/"}
        ],
    },
    {
        "key": "usajobs",
        "name": "USAJOBS / U.S. Forest Service",
        "type": "Federal government",
        "description": "Official USAJOBS listings, initially configured for public U.S. Forest Service opportunities in the surrounding foothills.",
        "links": [
            {"label": "USAJOBS", "url": "https://www.usajobs.gov/"}
        ],
    },
]


def get_job_sources() -> list[dict]:
    raw = env("JOB_PROVIDERS") or env("JOB_PROVIDER", "demo") or "demo"
    enabled = {name.strip().lower() for name in raw.split(",") if name.strip()}

    result = []
    for source in JOB_SOURCES:
        item = dict(source)
        item["enabled"] = item["key"] in enabled
        result.append(item)
    return result
