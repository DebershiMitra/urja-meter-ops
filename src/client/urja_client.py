"""Asynchronous HTTP Client for Urja Meter Ops Legacy Portal."""
import asyncio
import hashlib
import hmac
import logging
import time
from typing import Any, Dict, List, Optional
import httpx

from src.client.exceptions import (
    UrjaAuthenticationError,
    UrjaNotFoundError,
    UrjaSessionExpiredError,
    UrjaUpstreamError,
)
from src.config import settings

logger = logging.getLogger("urja.client")


class UrjaClient:
    """Robust upstream client for the Urja Meter Ops portal.
    
    Handles:
    - Better-Auth cookie-based session management
    - Strict SvelteKit CSRF headers (Origin & Referer)
    - Automatic session re-authentication upon expiration
    - Cryptographic HMAC-SHA256 request signing for bulk data export
    - Exponential backoff retry logic for resilience
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or settings.portal_base_url).rstrip("/")
        self.username = username or settings.portal_username
        self.password = password or settings.portal_password
        self.timeout = timeout or settings.client_timeout_seconds

        self._session_token: Optional[str] = None
        self._session_expires_at: float = 0.0
        self._signing_secret: Optional[str] = None
        self._lock = asyncio.Lock()

        # Shared headers matching legitimate browser interaction to satisfy SvelteKit CSRF
        self._default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/login",
            "Accept": "application/json, text/plain, */*",
        }

        self._http_client: Optional[httpx.AsyncClient] = None

    async def get_http_client(self) -> httpx.AsyncClient:
        """Returns or creates the underlying httpx.AsyncClient."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._default_headers,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=False,
            )
        return self._http_client

    async def close(self) -> None:
        """Closes the underlying HTTP client session."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def authenticate(self, force: bool = False) -> str:
        """Authenticates with the portal and captures the Better-Auth session token.
        
        SvelteKit requires:
        - POST to /login
        - form data: email, password
        - Origin and Referer headers to pass CSRF validation
        """
        async with self._lock:
            # Check if current session token is still valid (give 60s margin)
            now = time.time()
            if not force and self._session_token and now < (self._session_expires_at - 60):
                return self._session_token

            client = await self.get_http_client()
            login_url = f"{self.base_url}/login"
            payload = {
                "email": self.username,
                "password": self.password,
            }

            logger.info("Authenticating with Urja Portal at %s...", login_url)
            try:
                res = await client.post(
                    "/login",
                    data=payload,
                    headers={
                        **self._default_headers,
                        "Referer": f"{self.base_url}/login",
                    },
                )
            except Exception as e:
                logger.error("Authentication network error: %s", str(e))
                raise UrjaUpstreamError(f"Failed to connect to Urja portal login: {e}") from e

            if res.status_code not in (200, 302, 303):
                body = res.text
                logger.error("Login failed with status %d: %s", res.status_code, body)
                raise UrjaAuthenticationError(f"Login failed (status {res.status_code}): {body}")

            # Extract __Secure-better-auth.session_token cookie
            token = res.cookies.get("__Secure-better-auth.session_token")
            if not token:
                # Also check client cookies
                token = client.cookies.get("__Secure-better-auth.session_token")

            if not token:
                logger.error("Session cookie not found in response headers: %s", res.headers)
                raise UrjaAuthenticationError("Authentication succeeded but session token cookie was not set")

            self._session_token = token
            # Better Auth cookie max-age is 3600 seconds
            self._session_expires_at = time.time() + 3500
            logger.info("Successfully authenticated with Urja portal (session expires in ~1 hour)")
            return self._session_token

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        retry_count: int = 0,
    ) -> httpx.Response:
        """Executes an authenticated HTTP request with automatic re-auth and backoff."""
        await self.authenticate()
        client = await self.get_http_client()

        req_headers = dict(self._default_headers)
        if headers:
            req_headers.update(headers)

        if self._session_token:
            req_headers["Cookie"] = f"__Secure-better-auth.session_token={self._session_token}"

        try:
            response = await client.request(
                method=method,
                url=path,
                params=params,
                headers=req_headers,
            )
        except httpx.RequestError as exc:
            if retry_count < settings.client_max_retries:
                backoff = 2 ** retry_count
                logger.warning("Upstream request error on %s: %s. Retrying in %ds...", path, exc, backoff)
                await asyncio.sleep(backoff)
                return await self._request_with_retry(method, path, params, headers, retry_count + 1)
            raise UrjaUpstreamError(f"Upstream request failed after {retry_count} retries: {exc}") from exc

        # Handle 401 Unauthorized / 403 Forbidden session expiration
        if response.status_code in (401, 403) and retry_count < 2:
            logger.warning("Received status %d on %s. Re-authenticating and retrying...", response.status_code, path)
            await self.authenticate(force=True)
            return await self._request_with_retry(method, path, params, headers, retry_count + 1)

        # Handle rate limiting (429) or transient server errors (500, 502, 503)
        if response.status_code in (429, 500, 502, 503) and retry_count < settings.client_max_retries:
            backoff = (2 ** retry_count) + 0.5
            logger.warning("Upstream returned %d for %s. Retrying in %.1fs...", response.status_code, path, backoff)
            await asyncio.sleep(backoff)
            return await self._request_with_retry(method, path, params, headers, retry_count + 1)

        return response

    async def get_signing_secret(self, force: bool = False) -> str:
        """Retrieves the cryptographic signing secret from /portal/keys."""
        if not force and self._signing_secret:
            return self._signing_secret

        res = await self._request_with_retry("GET", "/portal/keys")
        if res.status_code != 200:
            raise UrjaUpstreamError(f"Failed to fetch signing secret: status {res.status_code}")

        data = res.json().get("data", {})
        secret = data.get("signingSecret")
        if not secret:
            raise UrjaUpstreamError(f"Invalid response from /portal/keys: {res.text}")

        self._signing_secret = secret
        logger.info("Acquired export signing secret.")
        return self._signing_secret

    def generate_export_signature(self, method: str, path: str, query: str, secret: str) -> tuple[str, str]:
        """Calculates HMAC-SHA256 signature for export requests.
        
        Matches portal implementation in 4.2Bgc2kUI.js:
        signature = HMAC_SHA256(secret, f"{method}\n{path}\n{query}\n{timestamp}")
        """
        timestamp = str(int(time.time()))
        message = f"{method}\n{path}\n{query}\n{timestamp}".encode("utf-8")
        sig = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        return timestamp, sig

    async def export_all_meters(self, page: int = 1) -> Dict[str, Any]:
        """Fetches the comprehensive signed meter export (/portal/export).
        
        Returns the entire 403-meter dataset in one call with geo coordinates,
        specs, and 7-level hierarchy.
        """
        secret = await self.get_signing_secret()
        query = f"page={page}"
        path = "/portal/export"
        timestamp, signature = self.generate_export_signature("GET", path, query, secret)

        headers = {
            "x-timestamp": timestamp,
            "x-signature": signature,
        }

        res = await self._request_with_retry("GET", f"{path}?{query}", headers=headers)
        if res.status_code == 403:
            # Secret might have rotated, try refreshing secret once
            logger.warning("Export returned 403. Refreshing signing secret...")
            secret = await self.get_signing_secret(force=True)
            timestamp, signature = self.generate_export_signature("GET", path, query, secret)
            headers = {"x-timestamp": timestamp, "x-signature": signature}
            res = await self._request_with_retry("GET", f"{path}?{query}", headers=headers)

        if res.status_code != 200:
            raise UrjaUpstreamError(f"Export failed with status {res.status_code}: {res.text}")

        return res.json()

    async def get_transformers(self, page: int = 1) -> Dict[str, Any]:
        """Fetches paginated Distribution Transformers (/portal/dts?page=N)."""
        res = await self._request_with_retry("GET", f"/portal/dts?page={page}")
        if res.status_code != 200:
            raise UrjaUpstreamError(f"Failed to fetch DTs (page {page}): status {res.status_code}")
        return res.json()

    async def get_all_transformers(self) -> List[Dict[str, Any]]:
        """Fetches all DTs across all pages."""
        all_dts: List[Dict[str, Any]] = []
        page = 1
        while True:
            resp = await self.get_transformers(page)
            items = resp.get("data", [])
            if not items:
                break
            all_dts.extend(items)
            total = resp.get("total", len(all_dts))
            if len(all_dts) >= total:
                break
            page += 1
        return all_dts

    async def get_meter_energy(self, meter_id: str) -> List[Dict[str, Any]]:
        """Fetches 337 half-hourly energy intervals for a meter (/portal/meters/{meter_id}/energy)."""
        res = await self._request_with_retry("GET", f"/portal/meters/{meter_id}/energy")
        if res.status_code == 404:
            raise UrjaNotFoundError(f"Meter '{meter_id}' not found or has no energy data")
        if res.status_code != 200:
            raise UrjaUpstreamError(f"Failed to fetch energy data for {meter_id}: status {res.status_code}")

        data = res.json().get("data", [])
        return data

    async def get_meter_geo(self, meter_id: str) -> Dict[str, Any]:
        """Fetches geo coordinates for a meter (/portal/meters/{meter_id}/geo)."""
        res = await self._request_with_retry("GET", f"/portal/meters/{meter_id}/geo")
        if res.status_code == 404:
            raise UrjaNotFoundError(f"Meter '{meter_id}' not found")
        if res.status_code != 200:
            raise UrjaUpstreamError(f"Failed to fetch geo for {meter_id}: status {res.status_code}")

        return res.json().get("data", {})

    async def search_meters(self, query: str = "", page: int = 1) -> Dict[str, Any]:
        """Queries the portal's search endpoint (/portal/meters/search)."""
        res = await self._request_with_retry("GET", f"/portal/meters/search?q={query}&page={page}")
        if res.status_code != 200:
            raise UrjaUpstreamError(f"Search failed with status {res.status_code}")
        return res.json()
