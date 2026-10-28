// The playground page in a real browser: pick the week and entry, type an input, press Enter, watch it play to END.
// usage: node run_in_page.mjs http://127.0.0.1:8765/ W4 main "/v2/items/7"   (prints one line; exit 1 on a problem)
import { spawn } from 'node:child_process';
const [url, week, entry, text] = process.argv.slice(2);
const port = 9400 + Math.floor(Math.random() * 400);
const chrome = spawn('google-chrome', ['--headless=new', '--no-sandbox', '--disable-gpu', `--remote-debugging-port=${port}`, '--window-size=1440,900', 'about:blank'], { stdio: 'ignore' });
const wait = ms => new Promise(r => setTimeout(r, ms));
const done = (line, bad) => { console.log(line); ws.close(); chrome.kill(); process.exit(bad ? 1 : 0); };
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
await wait(4000);
if (await ev(`document.getElementById('playbox').hidden`)) done(`${week}: no input box on the page`, true);
const before = await ev(`document.getElementById('runSel').options.length`);
// a real click into the box and real typing, then Enter
const box = JSON.parse(await ev(`JSON.stringify(document.getElementById('playText').getBoundingClientRect())`));
await ev(`(() => { const s = document.getElementById('playEntry'); s.value = ${JSON.stringify(entry)}; s.onchange(); })()`);
for (const type of ['mousePressed', 'mouseReleased']) await send('Input.dispatchMouseEvent', { type, x: box.left + 20, y: box.top + box.height / 2, button: 'left', buttons: type === 'mousePressed' ? 1 : 0, clickCount: 1 });
await send('Input.insertText', { text });
await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
let label = '', note = '';
for (let t = 0; t < 120 && !label; t++) {
  await wait(500);
  note = await ev(`document.getElementById('playNote').textContent`);
  if (/error|refused|too long|takes|never ran/i.test(note) && note !== 'recording…') done(`${week} ${entry} "${text}": the page says "${note}"`, true);
  const now = await ev(`document.getElementById('runSel').options.length`);
  if (now > before) label = await ev(`document.getElementById('runSel').selectedOptions[0].textContent`);
}
if (!label) done(`${week} ${entry} "${text}": no new run after 60 s (note: "${note}")`, true);
const playing = await ev(`document.getElementById('bPlay').getAttribute('aria-label')`);
await ev(`document.getElementById('bEnd').click()`); await wait(800);
const count = await ev(`document.getElementById('count').textContent`);
const caption = await ev(`document.getElementById('ctext').textContent`);
const noEnd = !/END\s+\S/.test(caption);
done(`${week} ${entry} "${text}": menu "${label}" | ${playing.startsWith('Pause') ? 'playing' : 'not playing'} | at the end ${count} | caption "${caption}"${noEnd ? ' | NO END' : ''}${errors.length ? ' | PAGE ERRORS: ' + errors.join(' / ') : ''}`, errors.length > 0 || noEnd || !playing.startsWith('Pause'));
