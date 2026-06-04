# nginx and `season=10/11` query parameters

On the VPS, HTTPS requests go through **nginx** before Flask on `:8080`.

## Symptom

- `GET /league/get_available_seasons` → **200** (no season in query)
- `GET /league/get_available_leagues?season=08/09&database=…` → **404** on `https://www.bowlyzer.online`
- Same URL on `http://127.0.0.1:8080/...` → **200**

## Cause

Many nginx builds treat a **literal `/` inside the query string** as starting a new URI path segment. The request line is effectively split so Flask never sees `/league/get_available_leagues` as a whole path.

Encoded `%2F` is often blocked by the same proxy/WAF rules.

## App workaround (no nginx change)

- **Address bar / shared links:** `?season=10/11` (familiar display)
- **API `fetch` URLs:** `?season=10-11` via `seasonForApiQuery()` in `frontend/src/lib/api.ts`
- **Backend:** `normalize_season_query_value()` accepts both

## Verify on the VPS

```bash
# Direct to container — should be 200
curl -s -o /dev/null -w '8080 %{http_code}\n' \
  'http://127.0.0.1:8080/league/get_available_leagues?season=08-09&database=db_real_merged'

# Through nginx — dash should be 200; literal slash often 404
curl -s -o /dev/null -w 'https dash %{http_code}\n' \
  'https://www.bowlyzer.online/league/get_available_leagues?season=08-09&database=db_real_merged'
curl -s -o /dev/null -w 'https slash %{http_code}\n' \
  'https://www.bowlyzer.online/league/get_available_leagues?season=08/09&database=db_real_merged'
```

If **8080 is 404** as well, redeploy the current `bowlyzer:release` image (route missing / SPA fallback), not an nginx season issue.

If **8080 is 500** but seasons list is **200**, check container logs and:

```bash
curl -s 'http://127.0.0.1:8080/league/get_available_leagues?season=08-09&database=db_real_merged' | head -c 400
docker compose -f ~/bowlyzer/docker-compose.prod.yml logs --tail 40 bowlyzer
```

Production mounts `.cache/league` **read-only**. After a cache **miss**, the app must still return JSON (new images tolerate failed cache writes). Ship pre-warmed `get_available_seasons` + `get_available_leagues` via `warm_league_cache.py` and `deploy.ps1 -SyncCache`.
