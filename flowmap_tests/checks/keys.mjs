// → / ← step the run wherever you last clicked (a button, the run menu, the speed menu, the slider, the box's edge);
// a grip reached with Tab resizes the box instead; in the playground's text box the arrows move the cursor.
// Real mouse, real keys. usage: node flowmap_tests/checks/keys.mjs <page url#W4>   (exit 1 on a problem)
import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const url = process.argv[2];
const port = 9900 + Math.floor(Math.random() * 90);
const profile = mkdtempSync(join(tmpdir(), 'flowmap-keys-'));
const chrome = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--disable-gpu', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' });
process.on('exit', () => chrome.kill());  // even when a check crashes, its browser closes
const close = async code => {  // the browser closes, then its storage is deleted (a leftover never fails the check)
  chrome.kill();
  if (chrome.exitCode === null && chrome.signalCode === null) await new Promise(r => chrome.once('exit', r));
  await rm(profile, { recursive: true, force: true, maxRetries: 20, retryDelay: 100 }).catch(() => {});
  process.exit(code);
};
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(1500);
const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
let n = 0; const pending = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
await new Promise(r => (ws.onopen = r));
const send = (method, params = {}) => new Promise(r => { const i = ++n; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result.result.value;
const rect = sel => ev(`JSON.stringify(document.querySelector(${JSON.stringify(sel)}).getBoundingClientRect())`).then(JSON.parse);
const click = async sel => { const r = await rect(sel), x = r.left + r.width / 2, y = r.top + r.height / 2; await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y }); await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 }); await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 }); await wait(300); };
const CODES = { ArrowRight: 39, ArrowLeft: 37, Escape: 27, Tab: 9 };
const key = async (k, shift = false) => { for (const type of ['keyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: k, code: k, windowsVirtualKeyCode: CODES[k], modifiers: shift ? 8 : 0 }); await wait(1400); };
const step = async () => +(await ev(`document.getElementById('count').textContent`)).split(' / ')[0];
const run = () => ev(`document.getElementById('runSel').value`);
const width = async () => Math.round((await rect('#insp')).width);
const bad = [], lines = [];
const expect = (ok, what) => { lines.push((ok ? 'ok ' : 'NO ') + what); if (!ok) bad.push(what); };
// → then ←: one step forward and one back, the run and the box unchanged
const arrows = async label => {
  const s0 = await step(), r0 = await run(), w0 = await width();
  await key('ArrowRight'); const s1 = await step();
  await key('ArrowLeft'); const s2 = await step();
  expect(s1 === s0 + 1 && s2 === s0 && await run() === r0 && await width() === w0, `${label}: → ${s0}→${s1}, ← back to ${s2}`);
};

await send('Page.navigate', { url }); await wait(4500);
await ev(`document.getElementById('bPlay').getAttribute('aria-label').startsWith('Pause') && document.getElementById('bPlay').click()`); await wait(500);
await key('ArrowRight');  // off step 0
await arrows('nothing clicked');
await click('#bStep'); await arrows('after the step button');
await click('#runSel'); await key('Escape'); await arrows('after the run menu');
await click('#bSpeed'); await key('Escape'); await arrows('after the speed menu');
await click('#scrub'); await arrows('after the slider');
const g = await rect('#insp .grip-w'), x = g.left + g.width / 2, y = g.top + g.height / 2;
await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 });
await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x - 60, y, buttons: 1 });
await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: x - 60, y, button: 'left' }); await wait(900);
await arrows('after dragging the box edge');
await ev(`document.querySelector('#insp .grip-w').focus()`);  // as Tab would reach it
{ const s0 = await step(), w0 = await width(); await key('ArrowLeft'); expect(await width() === w0 + 20 && await step() === s0, `a grip reached with Tab: ← widens the box by 20 (${w0}→${await width()}), the run stays`); }
if (!(await ev(`document.getElementById('playbox').hidden`))) {  // the playground: typing keeps its arrows
  await ev(`document.getElementById('playText').disabled`) || await click('#playText');
  await send('Input.insertText', { text: 'abc' });
  const s0 = await step(), c0 = await ev(`document.getElementById('playText').selectionStart`);
  await key('ArrowLeft');
  expect(await step() === s0 && await ev(`document.getElementById('playText').selectionStart`) === c0 - 1, 'in the playground text box: ← moves the cursor, the run stays');
}
console.log(lines.join('\n'));
ws.close(); await close(bad.length ? 1 : 0);
