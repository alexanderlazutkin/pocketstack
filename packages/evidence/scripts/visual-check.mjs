import puppeteer from 'puppeteer-core';
import fs from 'node:fs';

const CHROME = process.env.HOME + '/.cache/puppeteer/chrome/linux-155.0.8059.39/chrome-linux64/chrome';
const BASE = 'http://localhost:3000';
const PAGES = ['', 'revenue', 'revenue-mov', 'top-clients', 'shipping', 'verification'];
const OUT = '/tmp/opencode/shots';
fs.mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900 });

const report = [];
for (const p of PAGES) {
  const errors = [];
  const onConsole = (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 300)); };
  const onPageErr = (e) => errors.push(String(e).slice(0, 300));
  page.on('console', onConsole);
  page.on('pageerror', onPageErr);
  try {
    await page.goto(`${BASE}/${p}`, { waitUntil: 'networkidle2', timeout: 90000 });
    await new Promise((r) => setTimeout(r, 12000)); // дать DuckDB-WASM время отработать
    const charts = await page.evaluate(
      () => document.querySelectorAll('svg, canvas, [data-testid]').length
    );
    const bodyLen = await page.evaluate(() => document.body.innerText.length);
    const shot = `${OUT}/${p || 'index'}.png`;
    await page.screenshot({ path: shot, fullPage: false });
    report.push({ page: `/${p}`, charts, bodyLen, errors: errors.slice(0, 5), shot });
  } catch (e) {
    report.push({ page: `/${p}`, fail: String(e).slice(0, 300), errors: errors.slice(0, 5) });
  }
  page.off('console', onConsole);
  page.off('pageerror', onPageErr);
}
await browser.close();
fs.writeFileSync('/tmp/opencode/evidence-check.json', JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
