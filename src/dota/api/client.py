import asyncio

import httpx

from dota.models.match import MatchDetail, RecentMatch

BASE_URL = "https://api.opendota.com/api"


class OpenDotaClient:
    def __init__(self) -> None:
        self._sync = httpx.Client()

    def close(self) -> None:
        self._sync.close()

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

    def fetch_match_details(self, match_ids: list[int]) -> dict[int, MatchDetail]:
        return asyncio.run(self._fetch_match_details_async(match_ids))

    async def _fetch_match_details_async(self, match_ids: list[int]) -> dict[int, MatchDetail]:
        results = {}
        async with httpx.AsyncClient() as client:
            tasks = [client.get(f"{BASE_URL}/matches/{mid}") for mid in match_ids]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for mid, resp in zip(match_ids, responses):
                if isinstance(resp, Exception):
                    continue
                if resp.status_code == 200:
                    results[mid] = MatchDetail(**resp.json())
        return results

    def request_parse(self, match_ids: list[int]) -> list[int]:
        return asyncio.run(self._request_parse_async(match_ids))

    async def _request_parse_async(self, match_ids: list[int]) -> list[int]:
        requested = []
        async with httpx.AsyncClient() as client:
            for mid in match_ids:
                resp = await client.post(f"{BASE_URL}/request/{mid}")
                if resp.status_code == 200:
                    requested.append(mid)
        return requested
