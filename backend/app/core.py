"""
Framework-free logic for the EarthScope API: queries, case payloads, scoring, players.
app/main.py (FastAPI) is a thin wrapper around these functions.
"""
import json
import sqlite3

from .config import CASES_JSON, DB_PATH

PASS_MARK = 60
BADGES = {
    "first_case": lambda p: p["cases_done"] >= 1,
    "sharp_eye": lambda p: p["hypothesis_hits"] >= 3,
    "season_stripper": lambda p: p["quiz_first_try"] >= 3,
    "detective_5": lambda p: p["cases_done"] >= 5,
    "full_board": lambda p: p["cases_done"] >= 8,
    "perfect_case": lambda p: p["best_score"] >= 100,
}


def conn():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found. Build it first: python backend/pipeline/build.py")
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def shared_content():
    """Quiz, reasoning options, twist copy and case list (backend/db/cases.json)."""
    with open(CASES_JSON, encoding="utf-8") as f:
        return json.load(f)


def level_for(xp):
    return 1 + int(xp // 150)


# ---------------------------------------------------------------- science
def list_variables_regions():
    with conn() as c:
        return dict(
            variables=[dict(r) for r in c.execute("SELECT * FROM variables")],
            regions=[dict(r) for r in c.execute("SELECT * FROM regions")],
        )


def list_series():
    with conn() as c:
        rows = c.execute(
            """SELECT s.id, s.variable, s.region, st.n_years, st.direction, st.sen_per_decade, st.p_mk, st.p_ols,
                      st.verdict, st.game_verdict, st.n_star, st.more_years_needed, st.bh_significant
               FROM series s JOIN stats st ON st.series_id = s.id AND st.period_key = 'full'
               ORDER BY s.variable, s.region"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_series(series_id, adjusted=None):
    with conn() as c:
        s = c.execute("SELECT * FROM series WHERE id = ?", (series_id,)).fetchone()
        if not s:
            return None
        v = c.execute("SELECT * FROM variables WHERE key = ?", (s["variable"],)).fetchone()
        r = c.execute("SELECT * FROM regions WHERE key = ?", (s["region"],)).fetchone()
        m = c.execute("SELECT ym, raw, anom, adj FROM monthly WHERE series_id = ? ORDER BY ym", (series_id,)).fetchall()
        a = c.execute("SELECT year, anom, raw_mean, n_months, kept FROM annual WHERE series_id = ? ORDER BY year",
                      (series_id,)).fetchall()
        st = c.execute("SELECT period_key, detail_json FROM stats WHERE series_id = ?", (series_id,)).fetchall()
    stats = {row["period_key"]: json.loads(row["detail_json"]) for row in st}
    raw = [x["raw"] for x in m if x["raw"] is not None]
    cycle = {}
    for x in m:
        if x["raw"] is not None:
            cycle.setdefault(x["ym"][5:], []).append(x["raw"])
    means = [sum(vs) / len(vs) for _, vs in sorted(cycle.items())]
    return dict(
        id=series_id, variable=dict(v), region=dict(r), first_month=s["first_month"], last_month=s["last_month"],
        monthly=dict(t=[x["ym"] for x in m], raw=[x["raw"] for x in m], adj=[x["adj"] for x in m],
                     anom=[x["anom"] for x in m]),
        annual=[dict(x) for x in a], stats=stats,
        season_amplitude=(max(means) - min(means)) if means else None,
        mean_value=(sum(raw) / len(raw)) if raw else None,
    )


def get_stats(series_id, period="full"):
    with conn() as c:
        row = c.execute("SELECT detail_json FROM stats WHERE series_id = ? AND period_key = ?",
                        (series_id, period)).fetchone()
    return json.loads(row["detail_json"]) if row else None


def compare(variable, regions):
    out = []
    for reg in regions:
        sid = f"{variable}__{reg}"
        d = get_series(sid)
        if d:
            out.append(dict(id=sid, region=d["region"], stats=d["stats"].get("full"),
                            annual=d["annual"]))
    return out


# ---------------------------------------------------------------- game content
def _case_row(c, case_id):
    return c.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()


def list_cases(device_id=None):
    with conn() as c:
        rows = c.execute("SELECT * FROM cases ORDER BY number").fetchall()
        best = {}
        if device_id:
            for a in c.execute("SELECT case_id, MAX(score) s FROM attempts WHERE device_id = ? GROUP BY case_id",
                               (device_id,)):
                best[a["case_id"]] = a["s"]
        out = []
        for r in rows:
            ct = json.loads(r["content_json"])
            sid = r["series_id"]
            var, reg = sid.split("__")
            out.append(dict(id=r["id"], number=r["number"], series_id=sid, variable=var, region=reg,
                            difficulty=r["difficulty"], context=ct["context"],
                            status="solved" if best.get(r["id"], -1) >= PASS_MARK else "open",
                            best_score=best.get(r["id"])))
        return out


def get_case(case_id):
    """Everything the 7 steps need. The correct answers are NOT sent: the server scores in submit_attempt()."""
    with conn() as c:
        r = _case_row(c, case_id)
        if not r:
            return None
        content = json.loads(r["content_json"])
    var = r["series_id"].split("__")[0]
    main_s, twist_s = get_series(r["series_id"]), get_series(r["twist_series_id"])
    shared = shared_content()

    def strip_quiz(q):  # hide `ok` flags; the client asks the server to check an answer
        return dict(question=q["question"], answers=[dict(id=a["id"], text=a["text"]) for a in q["answers"]])

    def strip_reasons(rs):
        return {k: [dict(id=x["id"], en=x["en"], ar=x["ar"]) for x in v] for k, v in rs.items()}

    return dict(
        id=case_id, number=r["number"], difficulty=r["difficulty"], context=content["context"],
        hint=content["hint"], variable_text=shared["variable_text"][var],
        series=main_s, twist_series=twist_s,
        season_quiz=strip_quiz(shared["season_quiz"]),
        hypothesis_options=shared["hypothesis_options"], verdict_options=shared["verdict_options"],
        reasons=strip_reasons(shared["reasons"]),
        twist=build_twist(main_s, twist_s, shared["twist_templates"]),
    )


def check_season_answer(answer_id):
    for a in shared_content()["season_quiz"]["answers"]:
        if a["id"] == answer_id:
            return dict(ok=a["ok"], note=a["note"])
    return None


def build_twist(a, b, templates):
    sa, sb = a["stats"]["full"], b["stats"]["full"]
    da, db_ = sa.get("direction"), sb.get("direction")
    sig_a, sig_b = sa["verdict"] == "significant", sb["verdict"] == "significant"
    if da and db_ and da != db_ and sig_a and sig_b:
        kind = "opposite"
    elif da == db_ and sig_a != sig_b:
        kind = "same_direction_different_certainty"
    else:
        kind = "same_direction_different_speed" if da == db_ else "opposite"
    ratio = None
    if sa.get("slope_per_decade") and sb.get("slope_per_decade"):
        ratio = sb["slope_per_decade"] / sa["slope_per_decade"]
    return dict(kind=kind, ratio_b_over_a=ratio, **templates[kind])


# ---------------------------------------------------------------- scoring
def truth_for(case_id):
    with conn() as c:
        r = _case_row(c, case_id)
        st = c.execute("SELECT * FROM stats WHERE series_id = ? AND period_key = 'full'", (r["series_id"],)).fetchone()
    return dict(direction=st["direction"], verdict=st["verdict"], game_verdict=st["game_verdict"],
                p_mk=st["p_mk"], p_ols=st["p_ols"], slope_per_decade=st["sen_per_decade"],
                n_star=st["n_star"], more_years_needed=st["more_years_needed"], series_id=r["series_id"])


def submit_attempt(device_id, case_id, hypothesis, why, quiz_tries, verdict, reason_ids):
    truth = truth_for(case_id)
    shared = shared_content()
    no_effect = truth["verdict"] == "no_evidence"
    hyp_ok = (hypothesis == "none") if no_effect else (hypothesis == truth["direction"])
    verdict_ok = verdict == truth["game_verdict"]
    sound = {x["id"] for x in shared["reasons"].get(verdict, []) if x["sound"]}
    reason_ok = verdict_ok and any(rid in sound for rid in (reason_ids or []))
    score = (20 if hyp_ok else 0) + (20 if quiz_tries == 1 else 10 if quiz_tries else 0) \
        + (40 if verdict_ok else 0) + (20 if reason_ok else 0)
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO players(device_id) VALUES (?)", (device_id,))
        cur = c.execute(
            """INSERT INTO attempts(device_id, case_id, hypothesis, hypothesis_why, season_quiz_tries, verdict,
                                    reasons_json, hypothesis_correct, verdict_correct, score)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (device_id, case_id, hypothesis, why, quiz_tries, verdict, json.dumps(reason_ids or []),
             int(hyp_ok), int(verdict_ok), score))
        # XP counts only the improvement over the previous best, so replaying can't farm points
        prev = c.execute("SELECT MAX(score) m FROM attempts WHERE device_id = ? AND case_id = ? AND id < ?",
                         (device_id, case_id, cur.lastrowid)).fetchone()["m"] or 0
        gain = max(0, score - prev)
        xp = c.execute("SELECT xp FROM players WHERE device_id = ?", (device_id,)).fetchone()["xp"] + gain
        c.execute("UPDATE players SET xp = ?, level = ?, updated_at = CURRENT_TIMESTAMP WHERE device_id = ?",
                  (xp, level_for(xp), device_id))
        prof = _progress(c, device_id)
        new = []
        for b, rule in BADGES.items():
            if rule(prof) and not c.execute("SELECT 1 FROM badges WHERE device_id = ? AND badge = ?",
                                            (device_id, b)).fetchone():
                c.execute("INSERT INTO badges(device_id, badge) VALUES (?,?)", (device_id, b))
                new.append(b)
    return dict(score=score, xp_gained=gain, xp=xp, level=level_for(xp), new_badges=new,
                hypothesis_correct=hyp_ok, verdict_correct=verdict_ok, reason_correct=reason_ok,
                truth=truth, stamp={"real_trend": "VERIFIED", "natural_variation": "NATURAL VARIATION",
                                    "need_more_data": "INCONCLUSIVE"}[truth["game_verdict"]])


def _progress(c, device_id):
    rows = c.execute("SELECT case_id, MAX(score) s, MAX(hypothesis_correct) h, MIN(season_quiz_tries) q "
                     "FROM attempts WHERE device_id = ? GROUP BY case_id", (device_id,)).fetchall()
    return dict(cases_done=sum(1 for r in rows if r["s"] >= PASS_MARK),
                hypothesis_hits=sum(1 for r in rows if r["h"]),
                quiz_first_try=sum(1 for r in rows if r["q"] == 1),
                best_score=max([r["s"] for r in rows] or [0]))


# ---------------------------------------------------------------- players
def get_player(device_id):
    with conn() as c:
        p = c.execute("SELECT * FROM players WHERE device_id = ?", (device_id,)).fetchone()
        if not p:
            return None
        badges = [b["badge"] for b in c.execute("SELECT badge FROM badges WHERE device_id = ?", (device_id,))]
        prog = _progress(c, device_id)
    return dict(dict(p), badges=badges, progress=prog)


def upsert_player(device_id, nickname=None):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO players(device_id, nickname) VALUES (?, ?)", (device_id, nickname))
        if nickname:
            c.execute("UPDATE players SET nickname = ?, updated_at = CURRENT_TIMESTAMP WHERE device_id = ?",
                      (nickname[:24], device_id))
    return get_player(device_id)


def leaderboard(limit=20):
    with conn() as c:
        rows = c.execute("SELECT nickname, xp, level FROM players WHERE xp > 0 ORDER BY xp DESC LIMIT ?",
                         (limit,)).fetchall()
    return [dict(r) for r in rows]
