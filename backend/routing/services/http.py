"""Small HTTP helper shared by all upstream providers: one session, cached JSON."""

import hashlib
import json
import logging

import requests
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)

_session = requests.Session()


class UpstreamError(Exception):
    """An external API failed or returned something we cannot use."""


def _cache_key(method, url, params, body):
    raw = json.dumps([method, url, params, body], sort_keys=True, default=str)
    return "http:" + hashlib.sha256(raw.encode()).hexdigest()


def fetch_json(url, *, params=None, body=None, method="GET", cache_seconds=None):
    key = _cache_key(method, url, params, body)
    cached = cache.get(key)
    if cached is not None:
        return cached

    headers = {"User-Agent": settings.HTTP_USER_AGENT, "Accept": "application/json"}
    try:
        resp = _session.request(
            method,
            url,
            params=params,
            json=body,
            headers=headers,
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise UpstreamError(f"{url}: {exc}") from exc

    if resp.status_code >= 400:
        log.warning("Upstream %s returned %s: %s", url, resp.status_code, resp.text[:300])
        raise UpstreamError(f"{url} returned HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise UpstreamError(f"{url} returned non-JSON") from exc

    cache.set(key, data, cache_seconds)
    return data
