import { spawn } from 'node:child_process';
const url = process.argv[2];
const chrome = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=9339', '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' });
const wait = ms => new Promise(r => setTimeout(r, ms));
await wait(1500);
const page = (await (await fetch('http://127.0.0.1:9339/json')).json()).find(t => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
let n = 0; const pending = new Map();
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
await new Promise(r => (ws.onopen = r));
const send = (method, params = {}) => new Promise(r => { const i = ++n; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expr => (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result.result.value;
const click = async sel => { const b = JSON.parse(await ev(`JSON.stringify(document.querySelector('${sel}').getBoundingClientRect())`)); const x = b.left + b.width / 2, y = b.top + b.height / 2; await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 }); await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 1 }); };
await send('Page.enable'); await send('Page.navigate', { url });
await wait(1200);
await click('#stackTog');
const snap = async label => console.log(label.padEnd(16), '| count', await ev(`document.getElementById('count').textContent`), '| tabs', JSON.stringify(await ev(`[...document.querySelectorAll('#tasks .task-tab')].map(b => b.textContent).join(' ')`)), '| frames', JSON.stringify(await ev(`[...document.querySelectorAll('#frames .fname')].map(e => e.textContent).join(' < ')`)), '| empty:', await ev(`document.getElementById('stackEmpty').hidden ? '-' : document.getElementById('stackEmpty').textContent`));
for (let t = 0; t < 8; t++) { await snap(`t=${(1.2 + t * 1.5).toFixed(1)}s`); await wait(1500); }
// stepping by hand
await click('#bPlay'); await wait(300);
for (let k = 0; k < 3; k++) { await click('#bStep'); await wait(700); await snap(`step ${k + 1}`); }
ws.close(); chrome.kill(); process.exit(0);
