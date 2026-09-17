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
        "key": "amador_water",
        "name": "Amador Water Agency",
        "type": "Local public agency",
        "description": "Official Amador Water Agency employment openings for Amador County.",
        "links": [
            {"label": "Amador Water Agency Careers", "url": "https://amadorwater.gov/careers/current-job-openings/"},
            {"label": "Amador Water Agency GovernmentJobs", "url": "https://www.governmentjobs.com/careers/amadorwater"},
        ],
    },
    {
        "key": "tuolumne_utilities",
        "name": "Tuolumne Utilities District",
        "type": "Local public agency",
        "description": "Official Tuolumne Utilities District water and wastewater employment openings for Tuolumne County.",
        "links": [
            {"label": "TUD Job Openings", "url": "https://tudwater.com/careers/job-openings/"},
            {"label": "TUD GovernmentJobs", "url": "https://www.governmentjobs.com/careers/tudwater"},
        ],
    },
    {
        "key": "edjoin_calaveras",
        "name": "EDJOIN - Calaveras County Public Schools",
        "type": "Education",
        "description": "Official public-school jobs for Calaveras County Office of Education and Calaveras Unified School District.",
        "links": [
            {"label": "Calaveras County Office of Education", "url": "https://www.edjoin.org/calaverascoe"},
            {"label": "Calaveras Unified School District", "url": "https://www.edjoin.org/calaverasusd"}
        ],
    },
    {
        "key": "edjoin_amador",
        "name": "EDJOIN - Amador County Public Schools",
        "type": "Education",
        "description": "Official public-school jobs for Amador County Office of Education and Amador County Unified School District.",
        "links": [
            {"label": "Amador County Office of Education", "url": "https://www.edjoin.org/amadorcoe"},
            {"label": "Amador County Unified School District", "url": "https://www.edjoin.org/acusd"},
        ],
    },
    {
        "key": "edjoin_tuolumne",
        "name": "EDJOIN - Tuolumne County Public Schools",
        "type": "Education",
        "description": "Official public-school jobs for all 11 Tuolumne County employers listed in EDJOIN's county directory, including the county office, district, and charter-school postings.",
        "links": [
            {"label": "Tuolumne County Superintendent of Schools", "url": "https://www.edjoin.org/tcsos"},
            {"label": "EDJOIN Tuolumne County Search", "url": "https://www.edjoin.org/Home/Jobs?countyID=56"},
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
    {
        "key": "worldmark_angels_camp",
        "name": "WorldMark Angels Camp",
        "type": "Hospitality",
        "description": "Official Travel + Leisure Co. careers for WorldMark and related Angels Camp openings.",
        "links": [
            {"label": "Travel + Leisure Co. Careers", "url": "https://careers.travelandleisureco.com/jobs/search?query=Angels+Camp"}
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
