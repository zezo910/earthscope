// End-to-end walk through one full case, the Arabic board and a mobile view.
// 1) start the site:  cd case-game && npm run dev
// 2) run:             cd case-game && npx playwright install chromium   (first time only)
//                     npm run test:e2e
// Screenshots go to tests/e2e/screenshots/.  Override the URL with BASE_URL=http://...
const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");

const BASE = process.env.BASE_URL || "http://localhost:5173";
const OUT = path.join(__dirname, "screenshots");
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1200, height: 800 } });
  const errs = [];
  p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text()); });
  p.on("pageerror", (e) => errs.push("PAGEERR " + e.message));
  const shot = (n) => p.screenshot({ path: path.join(OUT, `step${n}.png`) });

  await p.goto(`${BASE}/?case=case02`); await p.waitForSelector(".grid"); await shot(0);
  await p.click("text=Start investigation");                                   // -> hypothesis
  await p.click(".opt.down"); await p.click("text=Lock hypothesis"); await shot(1);
  await p.click(".btn.amber.lg");                                              // -> evidence A
  await p.waitForSelector(".dual"); await shot(2);
  await p.click(".btn.amber.lg");                                              // -> strip season
  await p.click(".tog"); await p.waitForTimeout(700); await shot(3);
  await p.click(".ans >> nth=0"); await p.waitForTimeout(200);                 // wrong first
  console.log("next disabled after wrong answer:", await p.isDisabled(".btn.amber.lg"));
  await p.click(".ans >> nth=1"); await p.waitForTimeout(200);
  console.log("next enabled after right answer:", !(await p.isDisabled(".btn.amber.lg")));
  await p.click(".btn.amber.lg"); await p.waitForTimeout(400); await shot(4);  // testing
  console.log("metrics:", (await p.innerText(".notes")).replace(/\n+/g, " | ").slice(0, 330));
  await p.click(".btn.amber.lg");                                              // verdict
  await p.click(".vcard >> nth=0"); await p.click(".reason >> nth=0"); await p.click("text=Submit verdict");
  await p.waitForSelector(".stamp"); await p.waitForTimeout(900); await shot(5);
  console.log("verdict panel:", (await p.innerText(".notes")).replace(/\n+/g, " | ").slice(0, 260));
  await p.click(".btn.amber.lg"); await p.waitForTimeout(300); await shot(6);  // twist
  console.log("twist:", (await p.innerText(".notes")).replace(/\n+/g, " | "));
  await p.click(".btn.amber.lg"); await p.waitForSelector(".overlay"); await p.waitForTimeout(900); await shot(7);

  await p.goto(`${BASE}/?lang=ar`); await p.waitForSelector(".folder");
  await p.screenshot({ path: path.join(OUT, "board_ar.png") });
  await p.goto(`${BASE}/?case=case06&lang=ar`); await p.waitForSelector(".grid");
  await p.screenshot({ path: path.join(OUT, "case06_ar.png") });
  await p.setViewportSize({ width: 390, height: 800 });
  await p.goto(`${BASE}/?case=case01`); await p.waitForSelector(".grid");
  await p.screenshot({ path: path.join(OUT, "mobile.png") });

  console.log("console errors:", errs.length ? errs : "none");
  await b.close();
  process.exit(errs.length ? 1 : 0);
})();
