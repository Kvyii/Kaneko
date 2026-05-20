import asyncio
import logging

import httpx

from dota.cache import MatchCache
from dota.models.match import MatchDetail, RecentMatch

log = logging.getLogger("dota.api")

BASE_URL = "https://api.opendota.com/api"


class OpenDotaClient:
    def __init__(self) -> None:
        self._sync = httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._sync.close()

    # --- Async methods (for use inside an existing event loop, e.g. Discord bot) ---

    async def fetch_player_async(self, player_id: int) -> dict:
        log.info("GET %s/players/%d", BASE_URL, player_id)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{BASE_URL}/players/{player_id}")
            log.info("GET /players/%d — %d", player_id, resp.status_code)
            resp.raise_for_status()
            return resp.json()

    async def fetch_recent_matches_async(self, player_id: int, limit: int = 5) -> list[RecentMatch]:
        log.info("GET %s/players/%d/recentMatches?limit=%d", BASE_URL, player_id, limit)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{BASE_URL}/players/{player_id}/recentMatches",
                params={"limit": limit},
            )
            log.info("GET /players/%d/recentMatches — %d", player_id, resp.status_code)
            resp.raise_for_status()
            matches = [RecentMatch(**m) for m in resp.json()]
            log.info("Parsed %d recent matches", len(matches))
            return matches

    async def fetch_match_details_async(
        self, match_ids: list[int], cache: MatchCache | None = None
    ) -> dict[int, MatchDetail]:
        results = {}
        to_fetch = []

        if cache:
            for mid in match_ids:
                cached = cache.get(mid)
                if cached:
                    log.debug("Cache hit — match_id=%d", mid)
                    results[mid] = cached
                else:
                    to_fetch.append(mid)
        else:
            to_fetch = match_ids

        if to_fetch:
            log.info("Fetching %d match details (cached=%d) — %s", len(to_fetch), len(results), to_fetch)
            fetched = await self._fetch_match_details_async(to_fetch, cache)
            results.update(fetched)
        else:
            log.info("All %d match details served from cache", len(results))

        return results

    async def fetch_wl_async(self, player_id: int, date: int | None = None) -> dict:
        """Fetch win/loss counts. date = number of days to look back."""
        params = {"significant": 0}  # include all modes (turbo etc.)
        if date is not None:
            params["date"] = date
        log.info("GET %s/players/%d/wl date=%s significant=0", BASE_URL, player_id, date)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{BASE_URL}/players/{player_id}/wl",
                params=params,
            )
            log.info("GET /players/%d/wl — %d", player_id, resp.status_code)
            resp.raise_for_status()
            return resp.json()

    async def fetch_peers_async(self, player_id: int, date: int = 30) -> list[dict]:
        """Fetch peers (players queued with). date = number of days to look back."""
        params = {"significant": 0, "date": date}
        log.info("GET %s/players/%d/peers date=%d significant=0", BASE_URL, player_id, date)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{BASE_URL}/players/{player_id}/peers",
                params=params,
            )
            log.info("GET /players/%d/peers — %d", player_id, resp.status_code)
            resp.raise_for_status()
            return resp.json()

    async def fetch_player_matches_async(
        self, player_id: int, included_account_id: int, date: int = 365,
    ) -> list[dict]:
        """Fetch a player's matches filtered to games with a specific opponent."""
        params = {
            "included_account_id": included_account_id,
            "date": date,
            "significant": 0,
        }
        log.info(
            "GET %s/players/%d/matches included=%d date=%d",
            BASE_URL, player_id, included_account_id, date,
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{BASE_URL}/players/{player_id}/matches",
                params=params,
            )
            log.info("GET /players/%d/matches — %d", player_id, resp.status_code)
            resp.raise_for_status()
            return resp.json()

    async def request_parse_async(self, match_ids: list[int]) -> list[int]:
        log.info("Requesting parse for %d matches — %s", len(match_ids), match_ids)
        result = await self._request_parse_async(match_ids)
        log.info("Parse requested successfully for %d/%d matches", len(result), len(match_ids))
        return result

    # --- Sync methods (for CLI use) ---

    def fetch_player(self, player_id: int) -> dict:
        resp = self._sync.get(f"{BASE_URL}/players/{player_id}")
        resp.raise_for_status()
        return resp.json()

    def fetch_recent_matches(self, player_id: int, limit: int = 5) -> list[RecentMatch]:
        resp = self._sync.get(
            f"{BASE_URL}/players/{player_id}/recentMatches",
            params={"limit": limit},
        )
        resp.raise_for_status()
        return [RecentMatch(**m) for m in resp.json()]

    def fetch_match_details(self, match_ids: list[int], cache: MatchCache | None = None) -> dict[int, MatchDetail]:
        results = {}
        to_fetch = []

        if cache:
            for mid in match_ids:
                cached = cache.get(mid)
                if cached:
                    results[mid] = cached
                else:
                    to_fetch.append(mid)
        else:
            to_fetch = match_ids

        if to_fetch:
            fetched = asyncio.run(self._fetch_match_details_async(to_fetch, cache))
            for mid, detail in fetched.items():
                results[mid] = detail

        return results

    async def _fetch_match_details_async(
        self, match_ids: list[int], cache: MatchCache | None = None
    ) -> dict[int, MatchDetail]:
        results = {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = [client.get(f"{BASE_URL}/matches/{mid}") for mid in match_ids]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for mid, resp in zip(match_ids, responses):
                if isinstance(resp, Exception):
                    log.warning("GET /matches/%d failed — %s", mid, resp)
                    continue
                log.info("GET /matches/%d — %d", mid, resp.status_code)
                if resp.status_code == 200:
                    raw = resp.json()
                    if cache:
                        cache.put_raw(mid, raw)
                    results[mid] = MatchDetail(**raw)
        return results

    def request_parse(self, match_ids: list[int]) -> list[int]:
        return asyncio.run(self._request_parse_async(match_ids))

    async def _request_parse_async(self, match_ids: list[int]) -> list[int]:
        requested = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for mid in match_ids:
                try:
                    log.info("POST %s/request/%d", BASE_URL, mid)
                    resp = await client.post(f"{BASE_URL}/request/{mid}")
                    log.info("POST /request/%d — %d", mid, resp.status_code)
                    if resp.status_code == 200:
                        requested.append(mid)
                except httpx.TimeoutException:
                    log.warning("POST /request/%d timed out", mid)
                    continue
        return requested
