"""Put the map data into the page (and, for local checks only, a test hook)."""
import re, sys
src, data, out = sys.argv[1:4]
smoke = len(sys.argv) > 4 and sys.argv[4] in ("--smoke", "--hook")
live = len(sys.argv) > 4 and sys.argv[4] == "--hook-live"  # a hook, but the page keeps its own autoplay
page = open(src).read()
js = open(data).read().replace("</", "<\\/")
assert page.count("/*__W3_DATA__*/") == 1 and page.count("/*__DEBUG_HOOK__*/") == 1
page = page.replace("/*__W3_DATA__*/", js)
if live:
    page = page.replace("/*__DEBUG_HOOK__*/", open(sys.argv[5]).read())
HOOK = r"""
window.__smoke = async () => {
  const errs = [], notes = [];
  const log = (m, e) => errs.push(m + ': ' + e.message + ' @ ' + ((e.stack || '').split('\n')[1] || '').trim());
  try {
    for (let r = 0; r < RUNS.length; r++) {
      loadRun(r); stop();
      const all = [...TREE.nodes.values()];
      notes.push(`${RUN.key}: tree ${all.length} nodes (${all.filter(t => t.core).length} main, ${all.filter(t => !t.core && !t.dormant).length} helpers, ${all.filter(t => t.dormant).length} did-not-run), depth ${d3.max(all, t => t.depth)}`);
      notes.push('  MAIN: ' + all.filter(t => t.core).map(t => t.depth + ':' + labelOf(t.fn)).join('  '));
      for (let i = 0; i < EV.length; i++) {
        try { await stepForward(false); } catch (e) { log(`run${r} ev${i} ${EV[i].k}`, e); }
        if (i % 5 === 0) { try { const e = EV[i]; if (e.id && RUN.calls.has(e.id)) selectCall(e.id); } catch (e) { log(`call-insp run${r} ev${i}`, e); } }
        if (i === Math.floor(EV.length * 0.45)) notes.push('  HELPERS OPEN @45%: ' + [...shownNow].map(k => TREE.nodes.get(k)).filter(t => !t.core).map(t => labelOf(t.fn) + (t.cond ? ' [' + t.cond + ']' : '')).join(', '));
      }
      try { TREE.nodes.forEach(t => selectT(t.key)); } catch (e) { log(`node-insp run${r}`, e); }
      try { jump(EV.length); } catch (e) { log(`final run${r}`, e); }
      notes.push('  FINAL: ' + document.getElementById('final').innerText.slice(0, 160).replace(/\s+/g, ' '));
      try { await stepBack(false); jump(3); await stepBack(false); } catch (e) { log(`back run${r}`, e); }
      try { allBranches = true; renderState(); notes.push(`  all branches: ${shownNow.size}/${TREE.nodes.size} shown`); allBranches = false; renderState(); } catch (e) { log(`branches run${r}`, e); }
      try { TREE.nodes.forEach(t => { if (t.children.some(c => !c.core)) togglePin(t); }); TREE.nodes.forEach(t => { if (pinned.has(t.key)) togglePin(t); }); } catch (e) { log(`pins run${r}`, e); }
      const rows = d3.group(all.filter(t => !t.dormant), t => t.depth);
      let ov = 0;
      rows.forEach(list => { list.sort((a, b) => a.x - b.x); for (let i = 1; i < list.length; i++) { const a = list[i - 1], b = list[i]; if (a.x + boxW(a) / 2 > b.x - boxW(b) / 2 + 1) ov++; } });
      // every word on screen with every branch open: count pairs of text boxes that touch
      allBranches = true; renderState();
      const boxes = [];
      document.querySelectorAll('g.tnode:not(.off)').forEach((g, gi) => g.querySelectorAll('text').forEach(el => { if (!el.textContent) return; const b = el.getBBox(); const w0 = world.node().getCTM().inverse().multiply(el.getCTM()); boxes.push({ g: gi, x: b.x + w0.e, y: b.y + w0.f + 2, w: b.width, h: b.height - 4, s: el.textContent }); }));
      let hits = 0; const ex = [];
      for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) { const a = boxes[i], b = boxes[j]; if (a.g === b.g) continue; if (a.x < b.x + b.w - 1 && b.x < a.x + a.w - 1 && a.y < b.y + b.h - 1 && b.y < a.y + a.h - 1) { hits++; if (ex.length < 6) ex.push(a.s + ' / ' + b.s); } }
      allBranches = false; renderState();
      notes.push(`  text overlaps with all branches open: ${hits}${ex.length ? ' e.g. ' + ex.join(' | ') : ''}`);
      notes.push(`  layout: overlapping labels ${ov}, width ${Math.round(d3.max(all, t => t.x) - d3.min(all, t => t.x))}px, conds: ${all.filter(t => t.cond).map(t => labelOf(t.fn) + '=' + t.cond).join('; ')}`);
    }
    for (let p = 0; p < PARTS.length; p++) { try { setPart(p); notes.push(`part ${PARTS[p].label}: ${shownNow.size} shown, ${document.querySelectorAll('g.bp').length} bypass, note: ${document.getElementById('partNote').innerText.slice(0, 140).replace(/\s+/g, ' ')}`); } catch (e) { log(`part${p}`, e); } }
    setPart(LAST);
    loadRun(0);
  } catch (e) { log('fatal', e); }
  const out = document.createElement('pre'); out.id = 'smoke';
  out.textContent = 'SMOKE ' + (errs.length ? 'FAIL\n' + errs.slice(0, 15).join('\n') : 'OK') + '\n' + notes.join('\n');
  document.body.appendChild(out);
};
window.addEventListener('load', () => setTimeout(() => window.__smoke(), 300));
"""
if smoke:
    if sys.argv[4] == "--hook":
        HOOK = open(sys.argv[5]).read()
    page = page.replace("/*__DEBUG_HOOK__*/", HOOK)
    auto = re.search(r"if \(!reduceMotion[^)]*\) setTimeout\(\(\) => \{ if \(!playing && idx [^)]*\)?\) play\(\); \}, [^;]+\);", page).group(0)
    assert page.count(auto) == 1
    page = page.replace(auto, "")
    page = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body>' + page + "</body></html>"
else:
    page = page.replace("/*__DEBUG_HOOK__*/", "")
open(out, "w").write(page)
scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
open(out + ".app.js", "w").write(scripts[-1])
print(len(page), "bytes;", len(scripts), "inline scripts")
