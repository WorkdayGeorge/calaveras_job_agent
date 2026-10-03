from __future__ import annotations

import ipaddress
import json
import socket
from time import monotonic
from urllib.parse import urljoin, urlsplit

import requests
from lxml import html as lxml_html

MAX_RESPONSE_BYTES = 2_000_000
MAX_DESCRIPTION_CHARS = 100_000
MAX_REDIRECTS = 3
TOTAL_TIMEOUT_SECONDS = 20


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


def _plain_text(fragment: str) -> str:
    try:
        return lxml_html.fromstring(fragment).text_content().strip()
    except (ValueError, TypeError):
        return str(fragment).strip()


def _description_from_json_ld(document) -> str:
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

    for script in document.xpath('//script[@type="application/ld+json"]'):
        try:
            payload = json.loads(script.text or "")
        except (TypeError, json.JSONDecodeError):
            continue
        for description in candidates(payload):
            text = _plain_text(str(description))
            if len(text) >= 200:
                return text
    return ""


def extract_job_description(html: str) -> str:
    try:
        document = lxml_html.fromstring(html)
    except (ValueError, TypeError) as exc:
        raise JobDetailError("The employer posting contained invalid HTML.") from exc
    text = _description_from_json_ld(document)
    if not text:
        selectors = (
            '//*[@data-automation-id="jobPostingDescription"]',
            '//*[@data-testid="job-description"]',
            '//*[@id="job-description"]',
            '//*[contains(concat(" ", normalize-space(@class), " "), " job-description ")]',
            '//*[contains(concat(" ", normalize-space(@class), " "), " jobDescription ")]',
            "//article",
            "//main",
        )
        for selector in selectors:
            elements = document.xpath(selector)
            if elements:
                candidate = elements[0].text_content().strip()
                if len(candidate) >= 200:
                    text = candidate
                    break
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(text) < 200:
        raise JobDetailError("A complete description could not be extracted from this posting.")
    return text[:MAX_DESCRIPTION_CHARS]


def fetch_job_description(url: str) -> str:
    deadline = monotonic() + TOTAL_TIMEOUT_SECONDS
    current_url = _validate_public_url(url)
    headers = {"User-Agent": "CalaverasJobAgent/1.0 (+job-detail-request)"}
    for _ in range(MAX_REDIRECTS + 1):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise JobDetailError("The employer website took too long to respond.")
        response = requests.get(
            current_url,
            headers=headers,
            timeout=(min(5, remaining), min(8, remaining)),
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
            if monotonic() >= deadline:
                raise JobDetailError("The employer website took too long to respond.")
            data.extend(chunk)
            if len(data) > MAX_RESPONSE_BYTES:
                raise JobDetailError("The employer posting is too large to import safely.")
        encoding = response.encoding or "utf-8"
        return extract_job_description(data.decode(encoding, errors="replace"))
    raise JobDetailError("The employer website redirected too many times.")
