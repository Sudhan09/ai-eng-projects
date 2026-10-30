// The "it asks you" step on the real page: type a call that leaves out a piece nothing can make, see the row that asks
// for it, type your answer into that row and press Enter, see the run play, then press Clear.
// usage: node ask_in_page.mjs http://127.0.0.1:PORT/ W2 4 "batch.checksum()" '"abc"'   (one JSON line; exit 1 on a problem)
import { spawn } from 'node:child_process';
const [url, week, part, text, answer] = process.argv.slice(2);
const port = 9400 + Math.floor(Math.random() * 400);
const chrome = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--disable-gpu', `--remote-debugging-port=${port}`, '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' });
process.on('exit', () => chrome.kill());
const wait = ms => new Promise(r => setTimeout(r, ms));
const out = { steps: [] };
const done = bad => { if (bad) out.problem = bad; console.log(JSON.stringify(out)); ws.close(); chrome.kill(); process.exit(bad ? 1 : 0); };
await wait(1500);
const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
let n = 0; const pending = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
await new Promise(r => (ws.onopen = r));
const send = (method, params = {}) => new Promise(r => { const i = ++n; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => { const r = (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result; if (r.exceptionDetails) throw new Error((r.exceptionDetails.exception || {}).description || r.exceptionDetails.text); return r.result.value; };
const errors = [];
await send('Runtime.enable');
ws.addEventListener('message', m => { const d = JSON.parse(m.data); if (d.method === 'Runtime.exceptionThrown') errors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text); });
await send('Page.enable');
await send('Page.navigate', { url: `${url}#${week}` });
for (let t = 0; t < 60 && (await ev(`(document.getElementById('playbox') || { hidden: true }).hidden`)); t++) await wait(500);
const rect = async sel => JSON.parse(await ev(`JSON.stringify(document.querySelector(${JSON.stringify(sel)}).getBoundingClientRect())`));
const click = async r => { for (const type of ['mousePressed', 'mouseReleased']) await send('Input.dispatchMouseEvent', { type, x: r.left + Math.min(20, r.width / 2), y: r.top + r.height / 2, button: 'left', buttons: type === 'mousePressed' ? 1 : 0, clickCount: 1 }); };
const enter = async () => { for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 }); };
const runs = () => ev(`document.getElementById('runSel').options.length`);
const note = () => ev(`document.getElementById('playNote').textContent`);
const rows = () => ev(`JSON.stringify([...document.querySelectorAll('#shrinkList .srow')].map(r => ({ cls: r.className, name: r.querySelector('.sname').textContent, value: r.querySelector('input').value, why: r.querySelector('.swhy').textContent })))`).then(JSON.parse);
// the Part: a real click on its pill
const pill = JSON.parse(await ev(`JSON.stringify(([...document.querySelectorAll('.pill')].find(b => b.textContent === ${JSON.stringify(part)}) || { getBoundingClientRect: () => null }).getBoundingClientRect())`));
if (!pill) done(`no pill for Part ${part}`);
await click(pill); await wait(1500);
await ev(`(() => { const s = document.getElementById('playEntry'); s.value = 'call'; s.onchange(); })()`);
await click(await rect('#playText'));
await send('Input.insertText', { text });
const before = await runs();
await enter();
// 1. asked: a row for the missing piece
for (let t = 0; t < 120 && !(await ev(`!!document.querySelector('#shrinkList .srow')`)); t++) await wait(500);
out.steps.push({ said: await note(), rows: await rows() });
if (!out.steps[0].rows.length) done(`no row asking for the missing piece (the page says "${await note()}")`);
// 2. your answer, typed into that row, then Enter there
await click(await rect('#shrinkList .srow input'));
await send('Input.insertText', { text: answer });
await enter();
for (let t = 0; t < 120 && (await runs()) === before; t++) await wait(500);
if ((await runs()) === before) done(`no run with your answer (the page says "${await note()}")`);
await wait(1500);
await ev(`document.getElementById('bEnd').click()`); await wait(800);
out.steps.push({ run: await ev(`document.getElementById('runSel').selectedOptions[0].textContent`), said: await note(), rows: await rows(),
                 caption: await ev(`document.getElementById('ctext').textContent`) });
// 3. Clear: a real click
await click(await rect('#shrinkClear'));
await wait(1500);
out.steps.push({ rows: await rows(), clear: !(await ev(`document.getElementById('shrinkClear').hidden`)) });
done(errors.length ? 'page errors: ' + errors.join(' | ') : null);
