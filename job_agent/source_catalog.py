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
        "key": "remotive",
        "name": "Remotive",
        "type": "Remote job aggregator",
        "description": (
            "Remote openings filtered to positions that accept applicants "
            "living in California."
        ),
        "links": [
            {"label": "Remotive Remote Jobs", "url": "https://remotive.com/remote-jobs"}
        ],
    },
    {
        "key": "golden_san_andreas",
        "name": "Golden San Andreas Care Center",
        "type": "Healthcare",
        "description": "Official local care-center openings published through Apploi.",
        "links": [
            {
                "label": "Golden San Andreas Careers",
                "url": "https://evergreenhcg.com/locations/golden-sanandreas-care-center/",
            }
        ],
    },
    {
        "key": "chips_forestry",
        "name": "CHIPS Forestry",
        "type": "Forestry / nonprofit",
        "description": (
            "Official CHIPS hiring page. Monitored without creating a job record "
            "until CHIPS publishes a specific opening."
        ),
        "links": [
            {"label": "CHIPS Forestry", "url": "https://www.chipsforestry.org/"}
        ],
    },
    {
        "key": "resource_connection",
        "name": "The Resource Connection",
        "type": "Local nonprofit",
        "description": "Official Calaveras and Amador County openings from ApplicantPro.",
        "links": [
            {
                "label": "The Resource Connection Jobs",
                "url": "https://trcac.applicantpro.com/jobs/",
            }
        ],
    },
    {
        "key": "insight_manufacturing",
        "name": "Insight Manufacturing",
        "type": "Manufacturing",
        "description": "Official manufacturing openings in Murphys published through ADP.",
        "links": [
            {
                "label": "Insight Manufacturing Careers",
                "url": "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?ccId=19000101_000001&cid=824005bc-0b5e-446f-847a-33863ec245d7&lang=en_US&type=MP",
            }
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
        "description": "Official public-school jobs for all five Calaveras County EDJOIN employers.",
        "links": [
            {"label": "Calaveras County Office of Education", "url": "https://www.edjoin.org/calaverascoe"},
            {"label": "Calaveras Unified School District", "url": "https://www.edjoin.org/calaverasusd"},
            {"label": "Bret Harte Union", "url": "https://www.edjoin.org/bhuhsd"},
            {"label": "Mark Twain Union", "url": "https://www.edjoin.org/mtwain"},
            {"label": "Vallecito Union", "url": "https://www.edjoin.org/vallecito"},
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
    {
        "key": "angels_camp",
        "name": "City of Angels Camp",
        "type": "Local government",
        "description": "Official City of Angels Camp recruitment listings and application links.",
        "links": [
            {"label": "City Careers", "url": "https://angelscamp.gov/city-hall/human-resources-2/"}
        ],
    },
    {
        "key": "calaveras_court",
        "name": "Calaveras County Superior Court",
        "type": "Judicial branch",
        "description": "Official Superior Court job postings hosted by GovernmentJobs/NEOGOV.",
        "links": [
            {"label": "Court Careers", "url": "https://www.governmentjobs.com/careers/calaverascourts"}
        ],
    },
    {
        "key": "mact_health",
        "name": "MACT Health Board",
        "type": "Healthcare",
        "description": "Official MACT Health openings filtered to Calaveras County locations.",
        "links": [
            {"label": "MACT Careers", "url": "https://www.macthealth.org/careers"}
        ],
    },
    {
        "key": "ironstone",
        "name": "Ironstone Vineyards",
        "type": "Hospitality / winery",
        "description": "Official Ironstone employment openings in Murphys.",
        "links": [
            {"label": "Ironstone Employment", "url": "https://ironstonevineyards.com/employment/"}
        ],
    },
    {
        "key": "greenhorn_creek",
        "name": "Greenhorn Creek Resort",
        "type": "Hospitality / golf resort",
        "description": "Greenhorn Creek Resort openings in Angels Camp hosted by Harri.",
        "links": [
            {"label": "Greenhorn Creek Careers", "url": "https://harri.com/Yad-BmDiBaycxfQT"}
        ],
    },
    {
        "key": "calaveras_lumber",
        "name": "Calaveras & Sonora Lumber",
        "type": "Retail / building supply",
        "description": "Official Calaveras and Sonora Lumber openings hosted by Paycom.",
        "links": [
            {"label": "Calaveras Lumber Careers", "url": "https://www.paycomonline.net/v4/ats/web.php/portal/11C30BF2C8590F32D1D813EA44A4CC1A/career-page"}
        ],
    },
]


# Countywide employer coverage audit. This is intentionally separate from
# JOB_SOURCES: a provider can cover several employers, and some employers are
# useful watch-list candidates even when they do not expose a stable job feed.
EMPLOYER_COVERAGE = [
    {
        "name": "Calaveras County Government",
        "sector": "Government",
        "area": "Countywide",
        "status": "integrated",
        "method": "Direct NEOGOV provider",
        "priority": "Covered",
        "url": "https://www.governmentjobs.com/careers/calaverascounty",
        "notes": "County departments, public works, sheriff support, health and human services.",
    },
    {
        "name": "City of Angels Camp",
        "sector": "Government",
        "area": "Angels Camp",
        "status": "integrated",
        "method": "Direct official-page provider",
        "priority": "Covered",
        "url": "https://angelscamp.gov/city-hall/human-resources-2/",
        "notes": "Official recruitment rows and application links are monitored directly.",
    },
    {
        "name": "Calaveras County Superior Court",
        "sector": "Government",
        "area": "San Andreas",
        "status": "integrated",
        "method": "Direct NEOGOV provider",
        "priority": "Covered",
        "url": "https://www.calaveras.courts.ca.gov/general-information/career-opportunities",
        "notes": "Separate court NEOGOV feed is monitored directly.",
    },
    {
        "name": "California State Parks / Calaveras Big Trees",
        "sector": "Government",
        "area": "Arnold",
        "status": "covered",
        "method": "CalCareers provider",
        "priority": "Covered",
        "url": "https://www.parks.ca.gov/jobs",
        "notes": "State and seasonal park roles are covered through CalCareers.",
    },
    {
        "name": "Calaveras County Office of Education & Calaveras USD",
        "sector": "Education",
        "area": "Countywide",
        "status": "integrated",
        "method": "Direct EDJOIN provider",
        "priority": "Covered",
        "url": "https://www.edjoin.org/Home/Jobs?countyID=5",
        "notes": "The school provider directly monitors these two employers.",
    },
    {
        "name": "Bret Harte Union High School District",
        "sector": "Education",
        "area": "Angels Camp",
        "status": "integrated",
        "method": "Direct EDJOIN provider",
        "priority": "Covered",
        "url": "https://www.edjoin.org/Home/Jobs?countyID=5",
        "notes": "Official EDJOIN postings are monitored by the Calaveras school provider.",
    },
    {
        "name": "Mark Twain Union Elementary School District",
        "sector": "Education",
        "area": "Angels Camp / Copperopolis",
        "status": "integrated",
        "method": "Direct EDJOIN provider",
        "priority": "Covered",
        "url": "https://www.edjoin.org/mtwain",
        "notes": "Official EDJOIN postings are monitored by the Calaveras school provider.",
    },
    {
        "name": "Vallecito Union School District",
        "sector": "Education",
        "area": "Avery / Murphys / Vallecito",
        "status": "integrated",
        "method": "Direct EDJOIN provider",
        "priority": "Covered",
        "url": "https://www.edjoin.org/vallecito",
        "notes": "Official EDJOIN postings are monitored by the Calaveras school provider.",
    },
    {
        "name": "Mark Twain Medical Center / CommonSpirit",
        "sector": "Healthcare",
        "area": "San Andreas",
        "status": "integrated",
        "method": "Direct CommonSpirit provider",
        "priority": "Covered",
        "url": "https://www.commonspirit.careers/",
        "notes": "Local hospital and related CommonSpirit openings.",
    },
    {
        "name": "MACT Health Board",
        "sector": "Healthcare",
        "area": "Angels Camp / San Andreas",
        "status": "integrated",
        "method": "Direct ADP provider",
        "priority": "Covered",
        "url": "https://www.macthealth.org/careers",
        "notes": "Official ADP openings are filtered to Calaveras clinic locations.",
    },
    {
        "name": "Calaveras County Water District",
        "sector": "Utility",
        "area": "Countywide",
        "status": "integrated",
        "method": "Direct employer provider",
        "priority": "Covered",
        "url": "https://www.ccwd.org/job-opportunities",
        "notes": "Official CCWD opportunities are already monitored.",
    },
    {
        "name": "Pacific Gas and Electric",
        "sector": "Utility",
        "area": "Countywide / foothills",
        "status": "integrated",
        "method": "Direct PG&E provider",
        "priority": "Covered",
        "url": "https://jobs.pge.com/",
        "notes": "Location-filtered utility roles are already monitored.",
    },
    {
        "name": "Bear Valley Mountain Resort",
        "sector": "Hospitality",
        "area": "Bear Valley",
        "status": "integrated",
        "method": "Direct ADP provider",
        "priority": "Covered",
        "url": "https://www.bearvalley.com/employment/",
        "notes": "Resort and seasonal jobs are already monitored.",
    },
    {
        "name": "WorldMark Angels Camp",
        "sector": "Hospitality",
        "area": "Angels Camp",
        "status": "integrated",
        "method": "Direct employer provider",
        "priority": "Covered",
        "url": "https://careers.travelandleisureco.com/jobs/search?query=Angels+Camp",
        "notes": "Travel + Leisure Co. openings are already monitored.",
    },
    {
        "name": "Ironstone Vineyards",
        "sector": "Hospitality / winery",
        "area": "Murphys",
        "status": "integrated",
        "method": "Direct official-page provider",
        "priority": "Covered",
        "url": "https://ironstonevineyards.com/employment/",
        "notes": "Official employment-page titles and descriptions are monitored directly.",
    },
    {
        "name": "Greenhorn Creek Resort",
        "sector": "Hospitality",
        "area": "Angels Camp",
        "status": "integrated",
        "method": "Direct Harri employer-page provider",
        "priority": "Covered",
        "url": "https://harri.com/Yad-BmDiBaycxfQT",
        "notes": "Harri openings are monitored directly; expired postings are excluded.",
    },
    {
        "name": "Big Trees Market",
        "sector": "Retail / grocery",
        "area": "Arnold",
        "status": "manual",
        "method": "Aggregator/manual watch",
        "priority": "Medium",
        "url": "https://www.bigtreesmarket.com/",
        "notes": "Major local employer without a verified structured career feed.",
    },
    {
        "name": "Calaveras Lumber",
        "sector": "Retail / building supply",
        "area": "Angels Camp",
        "status": "integrated",
        "method": "Direct Paycom provider",
        "priority": "Covered",
        "url": "https://www.paycomonline.net/v4/ats/web.php/portal/11C30BF2C8590F32D1D813EA44A4CC1A/career-page",
        "notes": "Official Calaveras and Sonora Lumber openings are monitored directly.",
    },
    {
        "name": "Mar-Val Food Stores",
        "sector": "Retail / grocery",
        "area": "Valley Springs",
        "status": "manual",
        "method": "Aggregator/manual watch",
        "priority": "Medium",
        "url": "https://marvalfoodstores.org/",
        "notes": "Local store hiring may be advertised in-store or through third-party boards.",
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


def get_employer_coverage() -> tuple[list[dict], dict[str, int]]:
    employers = [dict(item) for item in EMPLOYER_COVERAGE]
    counts = {
        "total": len(employers),
        "automated": sum(
            item["status"] in {"integrated", "covered"} for item in employers
        ),
        "high_priority": sum(
            item["priority"] == "High" and item["status"] not in {"integrated", "covered"}
            for item in employers
        ),
        "manual": sum(item["status"] == "manual" for item in employers),
    }
    return employers, counts
