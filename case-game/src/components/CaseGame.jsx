import React, { useEffect, useMemo, useRef, useState } from "react";
import { getCase, listCases, checkSeason, submitAttempt } from "../api.js";

/* ---------- copy ---------- */
const T = {
  en: {
    open: "Open", solved: "Solved", case: "Case", back: "Back", next: "Next", start: "Start investigation",
    unit: "Unit", period: "Period", why: "Why this matters", expect: "What do you expect happened?",
    whyOpt: "Why? (optional)", lock: "Lock hypothesis", yours: "Your hypothesis", increased: "Increased",
    decreased: "Decreased", none: "No real change", look: "Look at the evidence. Does your first impression hold?",
    hint: "Hint", raw: "Raw", adj: "Seasonally adjusted", window: "Time window", windowSlope: "Trend in this window",
    windowWarn: "Pick a different window and the story can change. Cherry-picking is how charts mislead.",
    amp: "The yearly swing here is", biggerThan: "much bigger than the change you are looking for.",
    retry: "Try again", rate: "Rate of change", ci: "95% confidence", p: "p-value", perDecade: "per decade",
    pExplain: "Below 0.05 means a gap this big would be unlikely by chance.", chance: "Likely just chance.",
    nstar: "Years needed to detect this", have: "years of data", more: "more years needed",
    verdictQ: "What is your verdict?", reasonQ: "Why? Pick what supports your verdict.", submit: "Submit verdict",
    dataSays: "What the data says", cont: "Continue", close: "Close the case", nextCase: "Next case",
    review: "Review evidence", board: "Back to board", score: "Score", loading: "Loading case...",
    hypOk: "Your hypothesis matched the data.", hypNo: "The data disagreed with your hypothesis.",
    evA: "EVIDENCE A", evB: "EVIDENCE B", evC: "EVIDENCE C", sci: "Scientific result", you: "Your result",
    verdict: "Verdict", pending: "Hidden until you lock your hypothesis", cases: "Cases",
    bh: "Passes the multiple-testing check", bhNo: "Does not pass the multiple-testing check",
  },
  ar: {
    open: "مفتوحة", solved: "محلولة", case: "قضية", back: "رجوع", next: "التالي", start: "ابدأ التحقيق",
    unit: "الوحدة", period: "الفترة", why: "لماذا يهم؟", expect: "ماذا تتوقع أنه حدث؟",
    whyOpt: "لماذا؟ (اختياري)", lock: "ثبّت فرضيتك", yours: "فرضيتك", increased: "زاد", decreased: "قل",
    none: "لا تغير حقيقي", look: "انظر إلى الدليل. هل ما زال انطباعك الأول صحيحا؟", hint: "تلميح",
    raw: "خام", adj: "معدل موسميا", window: "النافذة الزمنية", windowSlope: "الاتجاه في هذه النافذة",
    windowWarn: "اختر نافذة أخرى وقد تتغير القصة. انتقاء الفترة هو طريقة تضليل الرسوم.",
    amp: "التذبذب السنوي هنا", biggerThan: "أكبر بكثير من التغير الذي تبحث عنه.", retry: "حاول مرة أخرى",
    rate: "معدل التغير", ci: "ثقة 95%", p: "قيمة p", perDecade: "لكل عقد",
    pExplain: "أقل من 0.05 يعني أن فجوة بهذا الحجم غير مرجحة بالصدفة.", chance: "غالبا صدفة.",
    nstar: "السنين اللازمة لكشف هذا", have: "سنة من البيانات", more: "سنة إضافية مطلوبة",
    verdictQ: "ما حكمك؟", reasonQ: "لماذا؟ اختر ما يدعم حكمك.", submit: "أرسل الحكم",
    dataSays: "ما تقوله البيانات", cont: "متابعة", close: "أغلق القضية", nextCase: "القضية التالية",
    review: "راجع الأدلة", board: "العودة إلى اللوحة", score: "النتيجة", loading: "جار تحميل القضية...",
    hypOk: "فرضيتك طابقت البيانات.", hypNo: "البيانات خالفت فرضيتك.", evA: "الدليل أ", evB: "الدليل ب",
    evC: "الدليل ج", sci: "النتيجة العلمية", you: "نتيجتك", verdict: "الحكم",
    pending: "مخفي حتى تثبّت فرضيتك", cases: "القضايا",
    bh: "ينجح في فحص الاختبارات المتعددة", bhNo: "لا ينجح في فحص الاختبارات المتعددة",
  },
};
const STAMPS = { VERIFIED: { en: "VERIFIED", ar: "تم التحقق", c: "var(--amber)" },
  INCONCLUSIVE: { en: "INCONCLUSIVE", ar: "غير حاسم", c: "var(--gray)" },
  "NATURAL VARIATION": { en: "NATURAL VARIATION", ar: "تغير طبيعي", c: "var(--gray)" } };

/* ---------- helpers ---------- */
const fmt = (v, d = 2) => (v == null || Number.isNaN(v) ? "n/a" : Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(d));
const fmtP = (p) => (p == null ? "n/a" : p < 0.001 ? "<0.001" : p.toFixed(3));
const arrow = (d) => (d === "up" ? "↑" : d === "down" ? "↓" : "＝");
const dirColor = (d) => (d === "up" ? "var(--up)" : d === "down" ? "var(--down)" : "var(--gray)");
const decYear = (ym) => +ym.slice(0, 4) + (+ym.slice(5, 7) - 0.5) / 12;

function olsSlope(xs, ys) {
  const n = xs.length; if (n < 3) return null;
  const xb = xs.reduce((a, b) => a + b, 0) / n, yb = ys.reduce((a, b) => a + b, 0) / n;
  let sxy = 0, sxx = 0;
  xs.forEach((x, i) => { sxy += (x - xb) * (ys[i] - yb); sxx += (x - xb) ** 2; });
  return sxy / sxx;
}

function useTween(target, ms = 500) {
  const [v, setV] = useState(target);
  const ref = useRef(target);
  useEffect(() => {
    const from = ref.current, t0 = performance.now();
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) { ref.current = target; setV(target); return; }
    let raf;
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / ms), e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
      ref.current = from + (target - from) * e; setV(ref.current);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

/* ---------- chart ---------- */
function Chart({ t, y, domain, color = "var(--gray)", trend, band, unit, h = 300, xr, small }) {
  const W = 640, m = { l: small ? 8 : 52, r: 10, t: 10, b: small ? 8 : 26 };
  const [x0, x1] = xr || [t[0], t[t.length - 1]];
  const [y0, y1] = domain;
  const X = (v) => m.l + ((v - x0) / (x1 - x0 || 1)) * (W - m.l - m.r);
  const Y = (v) => h - m.b - ((v - y0) / (y1 - y0 || 1)) * (h - m.t - m.b);
  let d = "", pen = false;
  t.forEach((tt, i) => {
    if (tt < x0 || tt > x1 || y[i] == null) { pen = false; return; }
    d += (pen ? "L" : "M") + X(tt).toFixed(1) + " " + Y(y[i]).toFixed(1); pen = true;
  });
  const yt = [0, 1, 2, 3, 4].map((i) => y0 + ((y1 - y0) * i) / 4);
  const span = x1 - x0, step = span > 30 ? 10 : span > 12 ? 5 : 2;
  const xt = []; for (let v = Math.ceil(x0 / step) * step; v <= x1; v += step) xt.push(v);
  const line = trend && [x0, x1].map((x) => [X(x), Y(trend(x))]);
  const bandPath = band && (() => {
    const xs = Array.from({ length: 41 }, (_, i) => x0 + ((x1 - x0) * i) / 40);
    const up = xs.map((x) => `${X(x)},${Y(band(x)[1])}`), dn = xs.slice().reverse().map((x) => `${X(x)},${Y(band(x)[0])}`);
    return "M" + up.join("L") + "L" + dn.join("L") + "Z";
  })();
  return (
    <svg viewBox={`0 0 ${W} ${h}`} role="img" className="chart" aria-label="time series chart">
      {!small && yt.map((v, i) => (
        <g key={i}><line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} className="grid" />
          <text x={m.l - 6} y={Y(v) + 4} className="axis" textAnchor="end">{fmt(v, Math.abs(y1 - y0) < 1 ? 3 : 1)}</text></g>))}
      {!small && xt.map((v) => <text key={v} x={X(v)} y={h - 8} className="axis" textAnchor="middle">{v}</text>)}
      {!small && unit && <text x={m.l} y={m.t + 2} className="axis">{unit}</text>}
      {bandPath && <path d={bandPath} className="band" style={{ fill: color }} />}
      <path d={d} fill="none" stroke={color} strokeWidth={small ? 2 : 1.6} strokeLinejoin="round" />
      {line && <line x1={line[0][0]} y1={line[0][1]} x2={line[1][0]} y2={line[1][1]} className="trend" style={{ stroke: color }} />}
    </svg>
  );
}

/* ---------- main game ---------- */
export default function CaseGame({ caseId, lang = "en", onNextCase, onBoard }) {
  const L = T[lang], tr = (o) => (o ? o[lang] || o.en : "");
  const [c, setC] = useState(null), [err, setErr] = useState(null);
  const [step, setStep] = useState(0);
  const [hyp, setHyp] = useState(null), [why, setWhy] = useState(""), [locked, setLocked] = useState(false);
  const [win, setWin] = useState(null), [hintOn, setHintOn] = useState(false);
  const [adjusted, setAdjusted] = useState(false), [quiz, setQuiz] = useState({ tries: 0, ok: false, pick: null, note: null });
  const [verdict, setVerdict] = useState(null), [reasons, setReasons] = useState([]), [result, setResult] = useState(null);

  useEffect(() => {
    setC(null); setStep(0); setHyp(null); setLocked(false); setAdjusted(false); setResult(null); setVerdict(null);
    setReasons([]); setQuiz({ tries: 0, ok: false, pick: null, note: null }); setHintOn(false); setErr(null);
    getCase(caseId).then((d) => { setC(d); const ts = d.series.monthly.t; setWin([Math.floor(decYear(ts[0])), Math.ceil(decYear(ts[ts.length - 1]))]); })
      .catch((e) => setErr(String(e)));
  }, [caseId]);

  const S = c && c.series, st = S && S.stats.full;
  const t = useMemo(() => (S ? S.monthly.t.map(decYear) : []), [S]);
  const k = useTween(adjusted ? 1 : 0, 500);
  const rawDomain = useMemo(() => {
    if (!S) return [0, 1]; const v = S.monthly.raw.filter((x) => x != null), lo = Math.min(...v), hi = Math.max(...v), p = (hi - lo) * 0.06;
    return [lo - p, hi + p];
  }, [S]);
  const adjDomain = useMemo(() => {
    if (!S) return [0, 1]; const v = S.monthly.adj.filter((x) => x != null), lo = Math.min(...v), hi = Math.max(...v), p = (hi - lo) * 0.08;
    return [lo - p, hi + p];
  }, [S]);

  if (err) return <div className="es-wrap"><Styles lang={lang} /><p className="es-err">{err}</p></div>;
  if (!c) return <div className="es-wrap"><Styles lang={lang} /><p className="muted">{L.loading}</p></div>;

  const reg = tr({ en: S.region.name_en, ar: S.region.name_ar }), vname = tr({ en: S.variable.name_en, ar: S.variable.name_ar });
  const unit = S.variable.unit, dir = st.direction;
  const hypLabel = { up: L.increased, down: L.decreased, none: L.none }[hyp];
  const morph = S.monthly.raw.map((r, i) => (r == null ? null : r + (S.monthly.adj[i] - r) * k));
  const winAnn = S.annual.filter((a) => a.kept && a.year >= win[0] && a.year <= win[1]);
  const winSlope = olsSlope(winAnn.map((a) => a.year), winAnn.map((a) => a.anom));
  const fit = st.fit, grand = S.mean_value;
  const trendFn = (x) => grand + fit.ybar + fit.slope * (x - 0.5 - fit.xbar);
  const bandFn = (x) => { const c0 = trendFn(x), hw = fit.tcrit * fit.resid_se * Math.sqrt(1 / fit.n + ((x - 0.5 - fit.xbar) ** 2) / fit.sxx); return [c0 - hw, c0 + hw]; };
  const trendColor = dirColor(dir);
  const pMax = Math.max(st.p_mk, st.p_ols), wh = st.weatherhead || {};

  const answerQuiz = async (a) => {
    const r = await checkSeason(a.id);
    setQuiz((q) => ({ tries: q.tries + 1, ok: r.ok, pick: a.id, note: r.note }));
  };
  const doSubmit = async () => {
    const r = await submitAttempt(caseId, { hypothesis: hyp, why, quizTries: quiz.tries, verdict, reasonIds: reasons });
    setResult(r);
  };
  const toggleReason = (id) => setReasons((rs) => (rs.includes(id) ? rs.filter((x) => x !== id) : [...rs, id]));

  const canNext = [true, locked, true, quiz.ok, true, !!result, true][step];
  const nextLabel = [L.start, L.next, L.next, L.next, L.next, L.cont, L.close][step];

  /* ----- notes (right) + evidence (left) per step ----- */
  let evidence, notes;
  if (step === 0) {
    evidence = (<div className="card"><div className="badge">{L.case} {String(c.number).padStart(2, "0")}</div>
      <div className={lang === "ar" ? "big" : "mono big"}>{vname}</div>
      <div className="mapbox" aria-hidden="true"><div className="pin" />
        <span>{reg} · [{S.region.west}, {S.region.south}, {S.region.east}, {S.region.north}]</span></div></div>);
    notes = (<><h2>{L.case} {String(c.number).padStart(2, "0")}: {reg}</h2>
      <p>{tr(c.variable_text.def)}</p>
      <dl><dt>{L.unit}</dt><dd className="mono">{unit}</dd><dt>{L.period}</dt><dd className="mono">{S.first_month} – {S.last_month}</dd></dl>
      <p className="muted"><b>{L.why}:</b> {tr(c.variable_text.why)}</p><p>{tr(c.context)}</p></>);
  } else if (step === 1) {
    evidence = <div className="card ghost" aria-hidden="true"><div className="qmark">?</div><p className="muted">{L.pending}</p></div>;
    notes = (<><h2>{L.expect}</h2>
      <div className="opts">{c.hypothesis_options.map((o) => (
        <button key={o.id} disabled={locked} aria-pressed={hyp === o.id} className={`opt ${o.id} ${hyp === o.id ? "on" : ""}`}
          onClick={() => setHyp(o.id)}>{o.id === "up" ? "↑ " : o.id === "down" ? "↓ " : "＝ "}{tr(o)}</button>))}</div>
      <label className="muted" htmlFor="why">{L.whyOpt}</label>
      <textarea id="why" value={why} disabled={locked} maxLength={300} onChange={(e) => setWhy(e.target.value)} />
      <button className="btn amber" disabled={!hyp || locked} onClick={() => setLocked(true)}>{L.lock}</button></>);
  } else if (step === 2) {
    const yrs = [Math.floor(t[0]), Math.ceil(t[t.length - 1])];
    evidence = (<div className="card"><div className="badge">{L.evA}</div>
      <Chart t={t} y={S.monthly.raw} domain={rawDomain} unit={unit} xr={win} />
      <div className="dual"><label>{L.window}: <span className="mono">{win[0]}–{win[1]}</span></label>
        <input type="range" min={yrs[0]} max={yrs[1] - 3} value={win[0]} aria-label="start year"
          onChange={(e) => setWin([Math.min(+e.target.value, win[1] - 3), win[1]])} />
        <input type="range" min={yrs[0] + 3} max={yrs[1]} value={win[1]} aria-label="end year"
          onChange={(e) => setWin([win[0], Math.max(+e.target.value, win[0] + 3)])} /></div></div>);
    notes = (<><h2>{L.look}</h2><button className="btn ghost" onClick={() => setHintOn(!hintOn)}>{L.hint}</button>
      {hintOn && <p className="hint">{tr(c.hint)}</p>}
      <p className="mono">{L.windowSlope}: {winSlope == null ? "n/a" : (winSlope >= 0 ? "+" : "") + fmt(winSlope * 10, 3)} {unit} {L.perDecade}</p>
      <p className="muted">{L.windowWarn}</p></>);
  } else if (step === 3) {
    evidence = (<div className="card"><div className="badge">{L.evB}</div>
      <Chart t={t} y={morph} domain={rawDomain} unit={unit} color={adjusted ? "var(--amber)" : "var(--gray)"} />
      <div className="switch" role="group"><span className={!adjusted ? "on" : ""}>{L.raw}</span>
        <button role="switch" aria-checked={adjusted} aria-label={L.adj} className={`tog ${adjusted ? "on" : ""}`} onClick={() => setAdjusted(!adjusted)}><i /></button>
        <span className={adjusted ? "on" : ""}>{L.adj}</span></div></div>);
    notes = (<><p>{L.amp} <b className="mono">{fmt(S.season_amplitude)} {unit}</b>, {L.biggerThan}</p>
      <h3>{tr(c.season_quiz.question)}</h3>
      {c.season_quiz.answers.map((a) => (
        <button key={a.id} disabled={quiz.ok} className={`ans ${quiz.pick === a.id ? (quiz.ok ? "good" : "bad") : ""}`} onClick={() => answerQuiz(a)}>{tr(a.text)}</button>))}
      {quiz.note && <p className={quiz.ok ? "good-note" : "bad-note"} role="status">{tr(quiz.note)}{!quiz.ok && " " + L.retry}</p>}</>);
  } else if (step === 4) {
    evidence = (<div className="card"><div className="badge">{L.evC}</div>
      <Chart t={t} y={S.monthly.adj} domain={adjDomain} unit={unit} color={trendColor} trend={trendFn} band={bandFn} /></div>);
    const pPos = Math.min(pMax, 0.2) / 0.2 * 100;
    notes = (<><div className="metric"><span className="lbl">{L.rate}</span>
      <b className="mono big" style={{ color: trendColor }}>{arrow(dir)} {st.slope_per_decade >= 0 ? "+" : ""}{fmt(st.slope_per_decade, 3)}</b>
      <span className="muted">{unit} {L.perDecade}{st.pct_change_over_period != null && ` · ${fmt(st.pct_change_over_period, 0)}%`}</span></div>
      <div className="metric"><span className="lbl">{L.ci}</span>
        <b className="mono big">[{fmt(st.ci95_per_decade[0], 3)}, {fmt(st.ci95_per_decade[1], 3)}]</b>
        <span className="muted">{st.ci95_per_decade[0] * st.ci95_per_decade[1] > 0 ? "" : "↔ 0"}</span></div>
      <div className="metric"><span className="lbl">{L.p}</span><b className="mono big">{fmtP(pMax)}</b>
        <div className="pbar" aria-hidden="true"><i className="mark" style={{ left: "25%" }} /><i className="dot" style={{ left: pPos + "%" }} /></div>
        <span className="muted">{pMax < 0.05 ? L.pExplain : L.chance} (MK {fmtP(st.p_mk)}, OLS {fmtP(st.p_ols)})</span></div>
      {wh.n_star_years != null && <p className="muted mono">{L.nstar}: {fmt(wh.n_star_years, 0)} · {st.n_years} {L.have}{wh.more_years_needed > 0 ? ` · +${wh.more_years_needed} ${L.more}` : ""}</p>}
      <p className="muted">{st.bh_significant ? L.bh : L.bhNo}</p></>);
  } else if (step === 5) {
    evidence = (<div className="card small"><div className="badge">{L.evC}</div>
      <Chart t={t} y={S.monthly.adj} domain={adjDomain} color={trendColor} trend={trendFn} band={bandFn} small h={150} />
      {result && <div className="stamp" style={{ color: STAMPS[result.stamp].c, borderColor: STAMPS[result.stamp].c }}>{STAMPS[result.stamp][lang]}</div>}</div>);
    notes = result ? (<><h2>{L.dataSays}</h2>
      <div className="vs"><div><span className="lbl">{L.yours}</span><b>{hypLabel}</b></div>
        <div><span className="lbl">{L.dataSays}</span><b style={{ color: dirColor(dir) }}>{arrow(dir)} {fmt(st.slope_per_decade, 3)} {unit} {L.perDecade}</b></div></div>
      <p>{result.hypothesis_correct ? L.hypOk : L.hypNo}</p>
      <p className="mono">{L.score}: {result.score}/100 · XP +{result.xp_gained}</p>
      {result.new_badges && result.new_badges.length > 0 && <p className="mono">🏅 {result.new_badges.join(", ")}</p>}</>) :
      (<><h2>{L.verdictQ}</h2>
        <div className="vcards">{c.verdict_options.map((o) => (
          <button key={o.id} aria-pressed={verdict === o.id} className={`vcard ${verdict === o.id ? "on" : ""}`}
            onClick={() => { setVerdict(o.id); setReasons([]); }}>{tr(o)}</button>))}</div>
        {verdict && <><p className="muted">{L.reasonQ}</p>{c.reasons[verdict].map((r) => (
          <label key={r.id} className={`reason ${reasons.includes(r.id) ? "on" : ""}`}>
            <input type="checkbox" checked={reasons.includes(r.id)} onChange={() => toggleReason(r.id)} /> {tr(r)}</label>))}
          <button className="btn amber" disabled={!reasons.length} onClick={doSubmit}>{L.submit}</button></>}</>);
  } else if (step === 6) {
    const B = c.twist_series, bs = B.stats.full, ann = (s) => s.annual.filter((a) => a.kept);
    const mini = (s, stt) => (<div className="half"><h3>{tr({ en: s.region.name_en, ar: s.region.name_ar })}</h3>
      <Chart t={ann(s).map((a) => a.year)} y={ann(s).map((a) => a.anom)} domain={(() => { const v = ann(s).map((a) => a.anom); const lo = Math.min(...v), hi = Math.max(...v); return [lo, hi]; })()}
        color={dirColor(stt.direction)} small h={120} />
      <b className="mono" style={{ color: dirColor(stt.direction) }}>{arrow(stt.direction)} {fmt(stt.slope_per_decade, 3)}</b>
      <span className="muted"> {S.variable.unit} {L.perDecade}</span></div>);
    evidence = <div className="card split">{mini(S, st)}{mini(B, bs)}</div>;
    notes = (<><h2 className="twist">{tr(c.twist.headline)}</h2><p>{tr(c.twist.body)}</p></>);
  }

  return (
    <div className="es-wrap" dir={lang === "ar" ? "rtl" : "ltr"}>
      <Styles lang={lang} />
      <ol className="rail" aria-label="progress">{[0, 1, 2, 3, 4, 5, 6].map((i) => <li key={i} className={i < step ? "done" : i === step ? "cur" : ""} />)}</ol>
      {locked && step > 1 && <div className="hypbar">{L.yours}: <b>{hypLabel}</b></div>}
      <div className="grid"><section className="ev">{evidence}</section><aside className="notes">{notes}</aside></div>
      <div className="nav">
        <button className="btn ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>{L.back}</button>
        <button className="btn amber lg" disabled={!canNext} onClick={() => (step === 6 ? setStep(7) : setStep(step + 1))}>{nextLabel}</button>
      </div>
      {step === 7 && <Summary {...{ c, S, st, result, hypLabel, L, lang, tr, unit, vname, reg, onNextCase, onBoard, setStep }} />}
    </div>
  );
}

function Summary({ c, st, result, hypLabel, L, lang, tr, unit, reg, vname, onNextCase, onBoard, setStep }) {
  const stamp = STAMPS[result.stamp];
  return (
    <div className="overlay" role="dialog" aria-label="summary">
      <div className="sum"><div className="stamp" style={{ color: stamp.c, borderColor: stamp.c }}>{stamp[lang]}</div>
        <p className="muted">{L.case} {String(c.number).padStart(2, "0")} · {reg} · {vname}</p>
        <div className="vs"><div className="card"><span className="lbl">{L.you}</span><b>{hypLabel}</b><span className="mono">{result.score}/100</span></div>
          <div className="card"><span className="lbl">{L.sci}</span><b style={{ color: dirColor(st.direction) }}>{arrow(st.direction)} {st.verdict}</b></div></div>
        <div className="vs three"><div><span className="lbl">{L.rate}</span><b className="mono">{fmt(st.slope_per_decade, 3)} {unit}</b></div>
          <div><span className="lbl">{L.p}</span><b className="mono">{fmtP(Math.max(st.p_mk, st.p_ols))}</b></div>
          <div><span className="lbl">{L.verdict}</span><b>{stamp[lang]}</b></div></div>
        <div className="nav"><button className="btn ghost" onClick={() => setStep(2)}>{L.review}</button>
          <button className="btn ghost" onClick={onBoard}>{L.board}</button>
          <button className="btn amber lg" onClick={onNextCase}>{L.nextCase}</button></div></div></div>
  );
}

/* ---------- cases board ---------- */
export function CasesBoard({ lang = "en", onOpen }) {
  const L = T[lang], [cases, setCases] = useState(null);
  useEffect(() => { listCases().then(setCases); }, []);
  return (
    <div className="es-wrap" dir={lang === "ar" ? "rtl" : "ltr"}><Styles lang={lang} />
      <h2>{L.cases}</h2>
      <div className="board">{(cases || []).map((x) => (
        <button key={x.id} className="folder" onClick={() => onOpen(x.id)}>
          <span className="tab">{L.case} {String(x.number).padStart(2, "0")}</span>
          <b className="reg">{x.region.replace(/_/g, " ")}</b><span className="muted mono">{x.variable}</span>
          <span className="dots" aria-label={"difficulty " + x.difficulty}>{"●".repeat(Math.min(3, Math.ceil(x.difficulty * 0.75)))}{"○".repeat(3 - Math.min(3, Math.ceil(x.difficulty * 0.75)))}</span>
          <span className={x.status === "solved" ? "solved" : "muted"}>{x.status === "solved" ? L.solved : L.open}</span></button>))}</div>
    </div>
  );
}

/* ---------- styles (scoped under .es-wrap) ---------- */
function Styles({ lang }) {
  return <style>{`
.es-wrap{--bg:#081020;--card:#0e1a33;--line:#223357;--amber:#f5a524;--up:#ff8a3d;--down:#4da3ff;--gray:#8a97b3;--tx:#e6ecf8;
 background:var(--bg);color:var(--tx);font-family:${lang === "ar" ? "Cairo" : "Inter"},system-ui,sans-serif;min-height:100%;padding:16px 20px 28px;position:relative}
.es-wrap h2,.es-wrap h3{font-family:${lang === "ar" ? "Cairo" : "'Space Grotesk'"},system-ui,sans-serif;margin:.2em 0 .6em}
.es-wrap .mono{font-family:ui-monospace,'JetBrains Mono',Menlo,monospace}.big{font-size:1.9rem;display:block}.muted{color:var(--gray)}
.rail{display:flex;gap:0;list-style:none;padding:0;margin:0 auto 18px;max-width:420px;align-items:center}
.rail li{width:14px;height:14px;border:2px solid var(--line);border-radius:50%;background:transparent;flex:none;position:relative}
.rail li+li{margin-inline-start:34px}.rail li+li:before{content:"";position:absolute;inset-inline-end:100%;top:4px;width:30px;height:2px;background:var(--line)}
.rail li.done{background:var(--tx);border-color:var(--tx)}.rail li.cur{background:var(--amber);border-color:var(--amber)}
.hypbar{position:sticky;top:0;background:#0b1630;border:1px solid var(--line);padding:6px 12px;border-radius:6px;margin-bottom:12px;z-index:2}
.grid{display:grid;grid-template-columns:65fr 35fr;gap:20px}@media(max-width:820px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;position:relative}.card.ghost{min-height:300px;display:grid;place-items:center;text-align:center}
.qmark{font-size:9rem;opacity:.08;font-family:'Space Grotesk',sans-serif}.notes{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
.badge{display:inline-block;border:1px solid var(--amber);color:var(--amber);padding:2px 8px;border-radius:4px;font-size:.78rem;margin-bottom:8px}
.chart{width:100%;height:auto;display:block}.grid line.grid,.chart .grid{stroke:var(--line);stroke-width:1}.chart .axis{fill:var(--gray);font-size:11px}
.chart .band{opacity:.18}.chart .trend{stroke-width:2.2;stroke-dasharray:7 6;animation:dash 1.2s linear infinite}@keyframes dash{to{stroke-dashoffset:-26}}
.mapbox{margin-top:14px;height:120px;border:1px dashed var(--line);border-radius:8px;display:grid;place-items:center;position:relative;color:var(--gray);font-size:.85rem}
.pin{position:absolute;width:12px;height:12px;border-radius:50%;background:var(--amber);box-shadow:0 0 18px var(--amber);top:34%;left:50%}
.opts{display:grid;gap:8px;margin:8px 0}.opt,.ans,.vcard,.reason{background:#0b1630;color:var(--tx);border:1px solid var(--line);padding:12px;border-radius:8px;cursor:pointer;text-align:start;font:inherit;display:block;width:100%}
.opt.up.on{background:var(--up);color:#1a0d00;border-color:var(--up)}.opt.down.on{background:var(--down);color:#00122a;border-color:var(--down)}.opt.none.on{background:var(--gray);color:#0a1020}
.vcard.on,.reason.on{border-color:var(--amber);box-shadow:inset 0 0 0 1px var(--amber)}.vcards{display:grid;gap:8px;margin:8px 0}.reason{margin:6px 0}
textarea{width:100%;min-height:60px;background:#0b1630;color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:8px;margin:4px 0 10px;font:inherit}
.btn{border-radius:8px;padding:10px 16px;font:inherit;cursor:pointer;border:1px solid var(--line);background:transparent;color:var(--tx)}
.btn.amber{background:var(--amber);color:#201400;border-color:var(--amber);font-weight:700}.btn.lg{padding:14px 28px;font-size:1.05rem}.btn:disabled{opacity:.4;cursor:not-allowed}.btn.ghost{color:var(--gray)}
.btn:focus-visible,.opt:focus-visible,.ans:focus-visible,.vcard:focus-visible,.tog:focus-visible{outline:2px solid var(--amber);outline-offset:2px}
.nav{display:flex;justify-content:space-between;align-items:center;margin-top:18px;gap:10px}
.dual{margin-top:10px;display:grid;gap:4px}.dual input{width:100%;accent-color:var(--amber)}
.switch{display:flex;align-items:center;gap:12px;justify-content:center;margin-top:12px;color:var(--gray)}.switch .on{color:var(--tx);font-weight:600}
.tog{width:60px;height:30px;border-radius:15px;border:1px solid var(--line);background:#0b1630;position:relative;cursor:pointer}
.tog i{position:absolute;top:3px;inset-inline-start:3px;width:22px;height:22px;border-radius:50%;background:var(--gray);transition:all .5s}
.tog.on i{inset-inline-start:33px;background:var(--amber)}.ans.good{border-color:#5fd39a;background:#0f2a22}.ans.bad{border-color:#e05a5a}
.good-note{color:#7fe0b0}.bad-note{color:#ff9a9a}.hint{border-inline-start:3px solid var(--amber);padding-inline-start:10px}
.metric{border-bottom:1px solid var(--line);padding:10px 0}.lbl{display:block;color:var(--gray);font-size:.85rem}
.pbar{position:relative;height:6px;background:var(--line);border-radius:3px;margin:10px 0}.pbar .mark{position:absolute;top:-4px;width:2px;height:14px;background:var(--amber)}
.pbar .dot{position:absolute;top:-3px;width:12px;height:12px;border-radius:50%;background:var(--tx);transform:translateX(-50%)}
.vs{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0}.vs.three{grid-template-columns:repeat(3,1fr)}.vs b{display:block;font-size:1.1rem}
.stamp{display:inline-block;border:4px solid;border-radius:50%;padding:22px 18px;font-family:'Space Grotesk',sans-serif;font-weight:700;text-align:center;max-width:190px;
 animation:slam .7s cubic-bezier(.2,1.4,.4,1) both;transform:rotate(-12deg);line-height:1.1}
@keyframes slam{0%{transform:scale(2.4) rotate(-30deg);opacity:0}60%{transform:scale(.92) rotate(-10deg);opacity:1}100%{transform:scale(1) rotate(-12deg)}}
.card.split{display:grid;grid-template-columns:1fr 1fr;gap:12px}.twist{font-size:1.6rem;color:var(--amber)}
.overlay{position:fixed;inset:0;background:rgba(5,10,22,.94);display:grid;place-items:center;z-index:20;padding:20px;overflow:auto}.sum{max-width:640px;width:100%;text-align:center}
.board{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}@media(max-width:820px){.board{grid-template-columns:1fr}}
.folder{background:var(--card);border:1px solid var(--line);border-radius:4px 10px 10px 10px;padding:26px 16px 14px;text-align:start;display:grid;gap:6px;color:var(--tx);font:inherit;cursor:pointer;position:relative;transition:transform .15s,border-color .15s}
.folder:hover,.folder:focus-visible{transform:translateY(-3px);border-color:var(--amber);outline:none}.folder .tab{position:absolute;top:-1px;inset-inline-start:12px;background:var(--line);padding:2px 10px;font-size:.75rem;border-radius:0 0 6px 6px}
.folder .reg{text-transform:capitalize;font-size:1.25rem}.solved{color:var(--amber)}
@media (prefers-reduced-motion:reduce){.stamp,.chart .trend{animation:none}.tog i{transition:none}}
`}</style>;
}
