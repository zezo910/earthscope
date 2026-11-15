import React, { useEffect, useState } from "react";
import CaseGame, { CasesBoard } from "./components/CaseGame.jsx";

const CASE_IDS = Array.from({ length: 8 }, (_, i) => `case${String(i + 1).padStart(2, "0")}`);

// URL state, so a case can be linked directly:  /?case=case02&lang=ar   or   /?board=1
function readUrl() {
  const q = new URLSearchParams(window.location.search);
  const lang = q.get("lang") === "ar" ? "ar" : "en";
  const caseId = CASE_IDS.includes(q.get("case")) ? q.get("case") : null;
  return { lang, caseId };
}

function writeUrl({ lang, caseId }) {
  const q = new URLSearchParams();
  if (caseId) q.set("case", caseId);
  if (lang !== "en") q.set("lang", lang);
  const s = q.toString();
  window.history.replaceState(null, "", s ? `?${s}` : window.location.pathname);
}

export default function App() {
  const [{ lang, caseId }, setState] = useState(readUrl);

  useEffect(() => {
    writeUrl({ lang, caseId });
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang, caseId]);

  const openCase = (id) => setState((s) => ({ ...s, caseId: id }));
  const toBoard = () => setState((s) => ({ ...s, caseId: null }));
  const nextCase = () => {
    const i = CASE_IDS.indexOf(caseId);
    setState((s) => ({ ...s, caseId: i >= 0 && i < CASE_IDS.length - 1 ? CASE_IDS[i + 1] : null }));
  };
  const toggleLang = () => setState((s) => ({ ...s, lang: s.lang === "en" ? "ar" : "en" }));

  return (
    <>
      <header className="topbar">
        <button className="brand" onClick={toBoard} aria-label="EarthScope home">
          <img src="/logo.png" alt="" />
          <b>EarthScope</b>
          <span>{lang === "ar" ? "محقق اتجاهات أنظمة الأرض" : "Earth Systems Trend Detective"}</span>
        </button>
        <div className="actions">
          {caseId && <button className="pill" onClick={toBoard}>{lang === "ar" ? "القضايا" : "Cases"}</button>}
          <button className="pill" onClick={toggleLang}>{lang === "ar" ? "English" : "العربية"}</button>
        </div>
      </header>
      <main>
        {caseId
          ? <CaseGame key={caseId + lang} caseId={caseId} lang={lang} onNextCase={nextCase} onBoard={toBoard} />
          : <CasesBoard key={lang} lang={lang} onOpen={openCase} />}
      </main>
    </>
  );
}
