// Throwaway: does the details box follow the run after a card was clicked? Real mouse, real play button.
import { spawn } from 'node:child_process';
const url = process.argv[2];
const chrome = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=9336', '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' });
process.on('exit', () => chrome.kill());  // even when a check crashes, its browser closes
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(1500);
const page = (await (await fetch('http://127.0.0.1:9336/json')).json()).find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
let n = 0; const pending = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
await new Promise(r => (ws.onopen = r));
const send = (method, params = {}) => new Promise(r => { const i = ++n; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result.result.value;
const click = async (x, y) => { await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y }); await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 }); await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 1 }); };
const pos = sel => ev(`(() => { const b = document.querySelector(${JSON.stringify(sel)}).getBoundingClientRect(); return JSON.stringify({ x: b.left + b.width / 2, y: b.top + b.height / 2 }); })()`).then(JSON.parse);
const title = () => ev(`document.getElementById('insp').hidden ? '(closed)' : document.getElementById('inspTitle').textContent`);
await send('Page.enable');
await send('Page.navigate', { url });
await wait(1200);
console.log('on load: open columns', await ev(`__app.tree().cols.filter(c => c.open).length + '/' + __app.tree().cols.filter(c => !c.single).length`), '| START says:', await ev(`document.querySelector('g.mhead.single .ftext').textContent`), '| caption:', await ev(`document.getElementById('ctext').textContent`));
await wait(4500);
const t1 = await title(); await wait(1500); const t2 = await title();
console.log('autoplay box:', t1, '→', t2, '| playing:', await ev(`document.getElementById('bPlay').getAttribute('aria-label')`));
// while it plays, click a card: the run pauses and the box shows that card; then ▶: the box follows the run again
const pb = await pos('#bPlay');
const card = await pos('g.mhead:not(.single) .box'); await click(card.x, card.y - 30); await wait(800);
console.log('clicked a card while playing → run now:', await ev(`document.getElementById('bPlay').getAttribute('aria-label')`));
const manual = await title();
await click(pb.x, pb.y); await wait(2500); const a = await title(); await wait(2000); const b = await title();
console.log('after a card click:', manual, '| after ▶:', a, '→', b, '| follow on:', await ev(`document.getElementById('followTog').getAttribute('aria-pressed')`));
// step button too
await click(pb.x, pb.y); await wait(300); await click(card.x, card.y - 30); await wait(600);
const st = await pos('#bStep'); const before = await title(); await click(st.x, st.y); await wait(900); const s1 = await title(); await click(st.x, st.y); await wait(900);
console.log('step after a card click:', before, '→', s1, '→', await title());
ws.close(); chrome.kill(); process.exit(0);
