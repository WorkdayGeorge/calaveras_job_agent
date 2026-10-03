from __future__ import annotations

import ipaddress
import json
import socket
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

MAX_RESPONSE_BYTES = 2_000_000
MAX_DESCRIPTION_CHARS = 100_000
MAX_REDIRECTS = 5


class JobDetailError(ValueError):
    pass


def _validate_public_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise JobDetailError("The employer link is not a valid web address.")
    if parsed.username or parsed.password:
        raise JobDetailError("The employer link contains unsupported credentials.")
    if parsed.port not in {None, 80, 443}:
        raise JobDetailError("The employer link uses an unsupported port.")

    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except OSError as exc:
        raise JobDetailError("The employer website could not be located.") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise JobDetailError("The employer link does not resolve to a public website.")
    return url


def _description_from_json_ld(soup: BeautifulSoup) -> str:
    def candidates(value):
        if isinstance(value, list):
            for item in value:
                yield from candidates(item)
        elif isinstance(value, dict):
            if value.get("@type") == "JobPosting" and value.get("description"):
                yield value["description"]
            for item in value.values():
                if isinstance(item, (dict, list)):
                    yield from candidates(item)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        for description in candidates(payload):
            text = BeautifulSoup(str(description), "html.parser").get_text("\n", strip=True)
            if len(text) >= 200:
                return text
    return ""


def extract_job_description(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = _description_from_json_ld(soup)
    if not text:
        selectors = (
            '[data-automation-id="jobPostingDescription"]',
            '[data-testid="job-description"]',
            "#job-description",
            ".job-description",
            ".jobDescription",
            "article",
            "main",
        )
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                candidate = element.get_text("\n", strip=True)
                if len(candidate) >= 200:
                    text = candidate
                    break
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) < 200:
        raise JobDetailError("A complete description could not be extracted from this posting.")
    return text[:MAX_DESCRIPTION_CHARS]


def fetch_job_description(url: str) -> str:
    current_url = _validate_public_url(url)
    headers = {"User-Agent": "CalaverasJobAgent/1.0 (+job-detail-request)"}
    for _ in range(MAX_REDIRECTS + 1):
        response = requests.get(
            current_url,
            headers=headers,
            timeout=20,
            allow_redirects=False,
            stream=True,
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("location")
            if not location:
                raise JobDetailError("The employer website returned an invalid redirect.")
            current_url = _validate_public_url(urljoin(current_url, location))
            continue
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type:
            raise JobDetailError("The employer posting is not an HTML page.")
        data = bytearray()
        for chunk in response.iter_content(64 * 1024):
            data.extend(chunk)
            if len(data) > MAX_RESPONSE_BYTES:
                raise JobDetailError("The employer posting is too large to import safely.")
        encoding = response.encoding or "utf-8"
        return extract_job_description(data.decode(encoding, errors="replace"))
    raise JobDetailError("The employer website redirected too many times.")
