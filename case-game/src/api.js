// EarthScope client. Tries the FastAPI backend first; if it is unreachable, falls back to the
// static JSON exported by backend/pipeline/export_static.py and scores locally (offline demo mode).
//
// Configure with a frontend/.env file (see .env.example) or, at runtime, window overrides:
//   VITE_API_URL    / window.EARTHSCOPE_API     (default "/api"    -> proxied to :8000 by Vite)
//   VITE_STATIC_URL / window.EARTHSCOPE_STATIC  (default "/static" -> frontend/public/static)

const env = (import.meta && import.meta.env) || {};
const apiBase = () => (typeof window !== "undefined" && window.EARTHSCOPE_API) || env.VITE_API_URL || "/api";
const staticBase = () => (typeof window !== "undefined" && window.EARTHSCOPE_STATIC) || env.VITE_STATIC_URL || "/static";

async function j(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(url + " -> " + r.status);
  return r.json();
}

export function deviceId() {
  const K = "earthscope_device_id";
  try {
    let id = localStorage.getItem(K);
    if (!id) {
      id = (crypto.randomUUID && crypto.randomUUID()) || "dev-" + Date.now() + "-" + Math.random().toString(16).slice(2);
      localStorage.setItem(K, id);
    }
    return id;
  } catch {
    return "dev-session-" + Math.random().toString(16).slice(2);
  }
}

let answersCache = null;
const answers = async () => (answersCache ||= await j(staticBase() + "/answers.json"));

export async function listCases() {
  try { return await j(`${apiBase()}/cases?device_id=${deviceId()}`); }
  catch { return j(staticBase() + "/cases.json"); }
}

export async function getCase(id) {
  try { return await j(`${apiBase()}/cases/${id}`); }
  catch { return j(`${staticBase()}/case/${id}.json`); }
}

export async function checkSeason(answerId) {
  try {
    return await j(apiBase() + "/season-check", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answer_id: answerId }),
    });
  } catch { return (await answers()).season[answerId]; }
}

const STAMP = { real_trend: "VERIFIED", natural_variation: "NATURAL VARIATION", need_more_data: "INCONCLUSIVE" };

export async function submitAttempt(caseId, a) {
  const body = {
    device_id: deviceId(), hypothesis: a.hypothesis, why: a.why || null,
    season_quiz_tries: Math.min(3, Math.max(1, a.quizTries || 1)), verdict: a.verdict, reason_ids: a.reasonIds || [],
  };
  try {
    return await j(`${apiBase()}/cases/${caseId}/attempt`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  } catch {
    const A = await answers(), truth = A.truth[caseId];
    const noEffect = truth.verdict === "no_evidence";
    const hyp = noEffect ? a.hypothesis === "none" : a.hypothesis === truth.direction;
    const ver = a.verdict === truth.game_verdict;
    const rea = ver && (a.reasonIds || []).some((id) => (A.sound[a.verdict] || []).includes(id));
    const score = (hyp ? 20 : 0) + (body.season_quiz_tries === 1 ? 20 : 10) + (ver ? 40 : 0) + (rea ? 20 : 0);
    let xp = 0;
    try { xp = +localStorage.getItem("earthscope_xp") || 0; xp += score; localStorage.setItem("earthscope_xp", xp); } catch {}
    return { score, xp_gained: score, xp, level: 1 + Math.floor(xp / 150), new_badges: [],
      hypothesis_correct: hyp, verdict_correct: ver, reason_correct: rea, truth, stamp: STAMP[truth.game_verdict] };
  }
}
