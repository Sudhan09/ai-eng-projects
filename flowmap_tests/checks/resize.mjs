// Resizing the details box with a real mouse: drag its left edge, bottom edge and corner; the map re-fits with no card
// under the box; the size is remembered after a reload; reset and double-click bring back the original size.
// usage: node flowmap_tests/checks/resize.mjs file:///…/flowmap_tests/build/flowmap.html#W4   (exit 1 on a problem)
import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const url = process.argv[2];
const port = 9800 + Math.floor(Math.random() * 100);
const profile = mkdtempSync(join(tmpdir(), 'flowmap-resize-'));  // its own browser storage, so the size starts as the original
const chrome = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--disable-gpu', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' });
process.on('exit', () => chrome.kill());  // even when a check crashes, its browser closes
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(1500);
const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
let n = 0; const pending = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
await new Promise(r => (ws.onopen = r));
const send = (method, params = {}) => new Promise(r => { const i = ++n; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => { const r = (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result; if (r.exceptionDetails) throw new Error((r.exceptionDetails.exception || {}).description || r.exceptionDetails.text); return r.result.value; };
const mouse = (type, x, y, buttons = 0, clickCount = 1) => send('Input.dispatchMouseEvent', { type, x, y, button: 'left', buttons, clickCount });
const rect = sel => ev(`JSON.stringify(document.querySelector(${JSON.stringify(sel)}).getBoundingClientRect())`).then(JSON.parse);
const box = async () => { const b = await rect('#insp'), s = await rect('#stage'); return { w: Math.round(b.width), h: Math.round(b.height), top: Math.round(b.top - s.top), bottom: Math.round(s.bottom - b.bottom) }; };
const under = () => ev(`(() => { const b = document.getElementById('insp').getBoundingClientRect(); let n = 0;
  document.querySelectorAll('g.tnode .box').forEach(c => { const r = c.getBoundingClientRect(); if (r.width && r.left < b.right && b.left < r.right && r.top < b.bottom && b.top < r.bottom) n++; }); return n; })()`);
const drag = async (sel, dx, dy) => {  // press on the grip's middle, move in steps, let go
  const g = await rect(sel), x = g.left + g.width / 2, y = g.top + g.height / 2;
  await mouse('mouseMoved', x, y); await mouse('mousePressed', x, y, 1);
  for (let i = 1; i <= 8; i++) { await mouse('mouseMoved', x + dx * i / 8, y + dy * i / 8, 1); await wait(30); }
  await mouse('mouseReleased', x + dx, y + dy); await wait(900);
};
const bad = [], line = [];
const expect = (ok, what) => { line.push((ok ? 'ok ' : 'NO ') + what); if (!ok) bad.push(what); };
const near = (a, b) => Math.abs(a - b) <= 2;

await send('Page.enable');
await send('Page.navigate', { url }); await wait(4000);
await ev(`document.getElementById('bPlay').getAttribute('aria-label').startsWith('Pause') && document.getElementById('bPlay').click()`);
if (await ev(`document.getElementById('insp').hidden`)) await ev(`document.getElementById('followTog') && document.getElementById('followTog').click()`);
await wait(800);
const original = await box();
expect(near(original.w, 300), `original width 300 (${original.w})`);
await drag('#insp .grip-w', -150, 0);
const wider = await box();
expect(near(wider.w, original.w + 150) && near(wider.h, original.h), `left edge 150px out: ${wider.w} wide, height kept`);
expect(await under() === 0, 'the map re-fits: no card under the wider box');
await drag('#insp .grip-h', 0, -300);
const shorter = await box();
expect(near(shorter.h, original.h - 300) && near(shorter.w, wider.w) && near(shorter.top, original.top), `bottom edge 300px up: ${shorter.h} tall, top and width kept`);
await drag('#insp .grip-c', 50, 100);
const corner = await box();
expect(near(corner.w, shorter.w - 50) && near(corner.h, shorter.h + 100), `corner: ${corner.w} wide, ${corner.h} tall`);
await send('Page.reload'); await wait(4000);
await ev(`document.getElementById('bPlay').getAttribute('aria-label').startsWith('Pause') && document.getElementById('bPlay').click()`);
const again = await box();
expect(near(again.w, corner.w) && near(again.h, corner.h), `remembered after a reload: ${again.w} × ${again.h}`);
const reset = await rect('#boxReset');
await mouse('mouseMoved', reset.left + reset.width / 2, reset.top + reset.height / 2); await mouse('mousePressed', reset.left + reset.width / 2, reset.top + reset.height / 2, 1); await mouse('mouseReleased', reset.left + reset.width / 2, reset.top + reset.height / 2); await wait(900);
const back = await box();
expect(near(back.w, original.w) && near(back.h, original.h) && near(back.bottom, original.bottom), `reset button: back to ${back.w} × ${back.h}`);
await drag('#insp .grip-w', -100, 0);
const g = await rect('#insp .grip-w');
await mouse('mousePressed', g.left + g.width / 2, g.top + g.height / 2, 1, 1); await mouse('mouseReleased', g.left + g.width / 2, g.top + g.height / 2, 0, 1);
await mouse('mousePressed', g.left + g.width / 2, g.top + g.height / 2, 1, 2); await mouse('mouseReleased', g.left + g.width / 2, g.top + g.height / 2, 0, 2); await wait(900);
const dbl = await box();
expect(near(dbl.w, original.w) && near(dbl.h, original.h), `double-click on a grip: back to ${dbl.w} × ${dbl.h}`);
expect(await under() === 0, 'no card under the box at the original size');
console.log(line.join('\n'));
ws.close(); chrome.kill(); process.exit(bad.length ? 1 : 0);
