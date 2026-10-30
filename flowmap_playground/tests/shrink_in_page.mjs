// Shrink on the real page: type a call that is too long, see the value that made it long with its suggestion, press
// Enter to run with it, see the changed function's card marked as yours, then press Clear.
// usage: node shrink_in_page.mjs http://127.0.0.1:PORT/ W5 "lab.main()"   (prints one JSON line; exit 1 on a problem)
import { spawn } from 'node:child_process';
const [url, week, text] = process.argv.slice(2);
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
// the page is ready when its input box shows (a busy machine can take longer than a few seconds)
for (let t = 0; t < 60 && (await ev(`(document.getElementById('playbox') || { hidden: true }).hidden`)); t++) await wait(500);
const rect = async sel => JSON.parse(await ev(`JSON.stringify(document.querySelector(${JSON.stringify(sel)}).getBoundingClientRect())`));
const click = async r => { for (const type of ['mousePressed', 'mouseReleased']) await send('Input.dispatchMouseEvent', { type, x: r.left + Math.min(20, r.width / 2), y: r.top + r.height / 2, button: 'left', buttons: type === 'mousePressed' ? 1 : 0, clickCount: 1 }); };
const enter = async () => { for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 }); };
const runs = () => ev(`document.getElementById('runSel').options.length`);
const note = () => ev(`document.getElementById('playNote').textContent`);
const rows = () => ev(`JSON.stringify([...document.querySelectorAll('#shrinkList .srow')].map(r => ({ cls: r.className, name: r.querySelector('.sname').textContent, code: (r.querySelector('.scode') || {}).textContent || '', value: r.querySelector('input').value, why: r.querySelector('.swhy').textContent })))`).then(JSON.parse);
await ev(`(() => { const s = document.getElementById('playEntry'); s.value = 'call'; s.onchange(); })()`);
await click(await rect('#playText'));
await send('Input.insertText', { text });
const before = await runs();
await enter();
// 1. too long: the Shrink row appears with the value that made it long
for (let t = 0; t < 240 && !(await ev(`!!document.querySelector('#shrinkList .srow.long')`)); t++) await wait(500);
out.steps.push({ said: await note(), rows: await rows(), shown: !(await ev(`document.getElementById('shrinkbox').hidden`)) });
if (!out.steps[0].rows.length) done('no Shrink row after the run that was too long');
// 2. Enter again (in the box): the run uses the suggestion
await click(await rect('#playText'));
await enter();
for (let t = 0; t < 240 && (await runs()) === before; t++) await wait(500);
if ((await runs()) === before) done(`no run with the suggestion (the page says "${await note()}")`);
await wait(1500);
out.steps.push({
  run: await ev(`document.getElementById('runSel').selectedOptions[0].textContent`), rows: await rows(),
  mine: JSON.parse(await ev(`JSON.stringify([...document.querySelectorAll('g.tnode.mine')].map(g => g.__data__.fn || g.__data__.key))`)),
});
// the changed function's box says so: a real click on its card
const card = JSON.parse(await ev(`JSON.stringify((document.querySelector('g.tnode.mine .box') || { getBoundingClientRect: () => null }).getBoundingClientRect())`));
if (!card) done('no card marked as yours');
await click(card);
await wait(800);
out.steps[1].box = await ev(`[...document.querySelectorAll('#inspBody .ctag.mine')].map(t => t.textContent).join(' | ')`);
// 3. Clear: a real click
await click(await rect('#shrinkClear'));
await wait(1500);
out.steps.push({ rows: await rows(), said: await ev(`document.getElementById('shrinkNote').textContent`), clear: !(await ev(`document.getElementById('shrinkClear').hidden`)) });
done(errors.length ? 'page errors: ' + errors.join(' | ') : null);
