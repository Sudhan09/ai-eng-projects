// Real mouse clicks on the map through Chrome DevTools: each column's head and one card in it must open the details
// box for what was clicked. usage: node checks/clicks.mjs file:///…/build/flowmap.html#W4
import { spawn } from 'node:child_process';
const url = process.argv[2];
const chrome = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=9335', '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(1500);
const page = (await (await fetch('http://127.0.0.1:9335/json')).json()).find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
let n = 0; const pending = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
await new Promise(r => (ws.onopen = r));
const send = (method, params = {}) => new Promise(r => { const i = ++n; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => { const r = (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result; if (r.exceptionDetails) throw new Error((r.exceptionDetails.exception || {}).description || r.exceptionDetails.text); return r.result.value; };
const click = async (x, y) => { await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y }); await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 }); await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 1 }); };
await send('Page.enable');
await send('Page.navigate', { url });
await wait(4000);
await ev(`document.getElementById('bPlay').getAttribute('aria-label').startsWith('Pause') && document.getElementById('bPlay').click()`);
// one target per column: its head, and its first card that is on the map in this Part
const targets = JSON.parse(await ev(`JSON.stringify((() => {
  const out = [], seen = new Set();
  document.querySelectorAll('g.tnode').forEach(g => {
    const c = g.__data__; if (!c || c.start || c.end || c.helper) return;  // a helper card is folded into its column
    const col = c.col.spec.name, kind = c.isCol ? 'head' : 'card';
    if (seen.has(col + kind) || !g.querySelector('.box').getBoundingClientRect().width) return;
    seen.add(col + kind); out.push({ key: c.key, kind, label: g.querySelector('.lbl').textContent });
  });
  return out.sort((a, b) => (a.kind === 'head') - (b.kind === 'head'));  // cards first: a click on a head folds its column
})())`));
let ok = 0; const bad = [];
for (const t of targets) {
  await ev(`document.getElementById('inspClose').click(); document.getElementById('zFit').click()`); await wait(900);
  const p = JSON.parse(await ev(`JSON.stringify((() => { const g = [...document.querySelectorAll('g.tnode')].find(g => g.__data__ && g.__data__.key === ${JSON.stringify(t.key)}); const b = g.querySelector('.box').getBoundingClientRect(); return { x: b.left + b.width * 0.6, y: b.top + Math.min(12, b.height / 2) }; })())`));
  await click(p.x, p.y); await wait(500);
  const title = await ev(`document.getElementById('insp').hidden ? '(closed)' : document.getElementById('inspTitle').textContent`);
  const want = t.label.replace(/^\./, '').replace(/\(\)$/, '');
  if (title.toLowerCase().includes(want.toLowerCase())) ok++; else bad.push(`${t.kind} ${t.label} -> ${title}`);
}
console.log(`real clicks: ${ok}/${targets.length} opened the right details${bad.length ? '; problems: ' + bad.join(' | ') : ''}`);
ws.close(); chrome.kill(); process.exit(bad.length || !targets.length ? 1 : 0);
