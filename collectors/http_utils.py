import requests

DEFAULT_TIMEOUT = 15
USER_AGENT = "JobSearchPortal/1.0 (personal job-search tool; contact via GitHub HarshithR7)"


def get_json(url: str, timeout: float = DEFAULT_TIMEOUT, **kwargs) -> dict | list | None:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, **kwargs)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def get_html(url: str, timeout: float = DEFAULT_TIMEOUT, **kwargs) -> str | None:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, **kwargs)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


def slugify(name: str) -> str:
    """Best-effort company-name -> ATS-slug guess (lowercase, alnum, hyphens)."""
    cleaned = "".join(c.lower() if c.isalnum() else " " for c in name)
    return "-".join(cleaned.split())
