"""
EarthScope API (FastAPI).
Run from the backend/ folder:   uvicorn app.main:app --reload --port 8000
Website:                        http://127.0.0.1:8000
Docs (Swagger UI):              http://127.0.0.1:8000/docs
All API routes live under /api. All logic lives in app/core.py.
"""
import json
import urllib.error
import urllib.request
from typing import List, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import core, earthdata
from .config import BASE44_URL, FRONTEND_DIR

app = FastAPI(title="EarthScope API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
api = APIRouter(prefix="/api")


class Attempt(BaseModel):
    device_id: str = Field(min_length=8, max_length=80)
    hypothesis: str = Field(pattern="^(up|down|none)$")
    why: Optional[str] = Field(default=None, max_length=500)
    season_quiz_tries: int = Field(ge=1, le=3)
    verdict: str = Field(pattern="^(real_trend|natural_variation|need_more_data)$")
    reason_ids: List[str] = []


class SeasonCheck(BaseModel):
    answer_id: str


class PlayerIn(BaseModel):
    nickname: Optional[str] = Field(default=None, max_length=24)


@api.get("/health")
def health():
    return {"ok": True}


@api.get("/catalog")
def catalog():
    return core.list_variables_regions()


@api.get("/series")
def series():
    return core.list_series()


@api.get("/series/{variable}/{region}")
def series_one(variable: str, region: str):
    d = core.get_series(f"{variable}__{region}")
    if not d:
        raise HTTPException(404, "series not found")
    return d


@api.get("/stats/{variable}/{region}")
def stats(variable: str, region: str, period: str = "full"):
    d = core.get_stats(f"{variable}__{region}", period)
    if not d:
        raise HTTPException(404, "stats not found")
    return d


@api.get("/compare")
def compare(variable: str, regions: str = Query(..., description="comma separated region keys")):
    return core.compare(variable, [r for r in regions.split(",") if r])


@api.get("/cases")
def cases(device_id: Optional[str] = None):
    return core.list_cases(device_id)


@api.get("/cases/{case_id}")
def case(case_id: str):
    d = core.get_case(case_id)
    if not d:
        raise HTTPException(404, "case not found")
    return d


@api.post("/season-check")
def season_check(body: SeasonCheck):
    r = core.check_season_answer(body.answer_id)
    if not r:
        raise HTTPException(404, "unknown answer")
    return r


@api.post("/cases/{case_id}/attempt")
def attempt(case_id: str, body: Attempt):
    if not core.get_case(case_id):
        raise HTTPException(404, "case not found")
    return core.submit_attempt(body.device_id, case_id, body.hypothesis, body.why, body.season_quiz_tries,
                               body.verdict, body.reason_ids)


@api.get("/players/{device_id}")
def player(device_id: str):
    p = core.get_player(device_id)
    if not p:
        raise HTTPException(404, "player not found")
    return p


@api.put("/players/{device_id}")
def player_put(device_id: str, body: PlayerIn):
    return core.upsert_player(device_id, body.nickname)


@api.get("/leaderboard")
def leaderboard(limit: int = 20):
    return core.leaderboard(min(limit, 100))


app.include_router(api)


# ---------------------------------------------------------------- Base44 pass-through
# The site's Explore / Compare data and the AI helper run as Base44 cloud functions
# (POST /api/apps/<id>/functions/...). Forward those calls to the live Base44 app so the
# local site behaves exactly like earth-scope-detective.base44.app. Needs internet.
SKIP_REQ = {"host", "content-length", "accept-encoding", "connection", "origin", "referer"}
SKIP_RESP = {"content-length", "content-encoding", "transfer-encoding", "connection"}


def _forward(method, url, headers, body):
    req = urllib.request.Request(url, data=body or None, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


@app.post("/api/apps/{app_id}/functions/earthData", include_in_schema=False)
async def earth_data(app_id: str, request: Request):
    """Explore / Compare data: answer from the team's own dataset when we have it, else ask Base44."""
    raw = await request.body()
    try:
        data = earthdata.answer(json.loads(raw or b"{}"))
    except Exception as e:  # never break the page: fall back to Base44
        print("earthData local answer failed:", e)
        data = None
    if data is not None:
        return JSONResponse(data)
    return await base44_proxy(f"{app_id}/functions/earthData", request)


@app.api_route("/api/apps/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
async def base44_proxy(rest: str, request: Request):
    url = f"{BASE44_URL}/api/apps/{rest}" + (f"?{request.url.query}" if request.url.query else "")
    headers = {k: v for k, v in request.headers.items() if k.lower() not in SKIP_REQ}
    try:
        status, resp_headers, content = await run_in_threadpool(
            _forward, request.method, url, headers, await request.body())
    except (urllib.error.URLError, TimeoutError) as e:
        return JSONResponse({"detail": f"Cannot reach Base44 ({e}). Check your internet connection."}, 502)
    out = {k: v for k, v in resp_headers.items() if k.lower() not in SKIP_RESP}
    return Response(content=content, status_code=status, headers=out)


# ---------------------------------------------------------------- website
# Serves frontend/ (the EarthScope site). Page routes like /explore or /game return index.html,
# and the site's own JavaScript shows the right page.
@app.get("/{path:path}", include_in_schema=False)
def website(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "not found")
    file = (FRONTEND_DIR / path).resolve()
    if path and file.is_file() and FRONTEND_DIR.resolve() in file.parents:
        return FileResponse(file)
    return FileResponse(FRONTEND_DIR / "index.html")
