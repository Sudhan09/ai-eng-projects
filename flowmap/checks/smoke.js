window.__smoke = async () => {
  const errs = [], notes = [], problems = [];
  // a short summary of every week's map (Parts, cards, lines, each run's START, END, steps and the calls it shows):
  // flowmap.py saves it as the expected map, so a rebuild that changes an old week unexpectedly is flagged
  const summary = {};
  const log = (m, e) => errs.push(m + ': ' + e.message + ' @ ' + ((e.stack || '').split('\n')[1] || '').trim());
  // a guard that failed: one line each in build/check.txt and the commit note
  const bad = (where, what) => problems.push(`PROBLEM ${where}: ${what}`);
  const check = () => {
    drawMap(false); renderState();
    const boxes = [];
    document.querySelectorAll('g.tnode').forEach((g, gi) => g.querySelectorAll('text').forEach(el => { if (!el.textContent) return; const r = el.getBoundingClientRect(); if (!r.width) return; boxes.push({ g: gi, x: r.left, y: r.top + 1, w: r.width, h: r.height - 2, s: el.textContent }); }));
    let hits = 0; const ex = [];
    for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) { const a = boxes[i], b = boxes[j]; if (a.g === b.g) continue; if (a.x < b.x + b.w - 1 && b.x < a.x + a.w - 1 && a.y < b.y + b.h - 1 && b.y < a.y + a.h - 1) { hits++; if (ex.length < 4) ex.push(a.s + ' / ' + b.s); } }
    const cards = tSel.data();
    let thru = 0; const tex = [];
    lSel.each(function (g) { if (g.quiet) return; const L = this.getTotalLength(); for (let s = 4; s < L - 4; s += 4) { const p = this.getPointAtLength(s); const c = cards.find(c => c !== g.a && c !== g.b && p.x > c.x - c.w / 2 + 2 && p.x < c.x + c.w / 2 - 2 && p.y > c.y - c.h / 2 + 2 && p.y < c.y + c.h / 2 - 2); if (c) { thru++; if (tex.length < 4) tex.push(g.key + ' through ' + c.key); break; } } });
    return { cols: TREE.cols.filter(c => c.present).map(c => c.spec.name), cards: cards.length, lines: lSel.filter(g => !g.quiet).size(), isnew: tSel.filter('.isnew').size(), changed: tSel.filter('.edited').size(), hits, ex, thru, tex };
  };
  // cards a docked panel covers (the details box, the waiting list, the legend, the zoom buttons). A map taller than
  // the screen keeps its readable size and scrolls (fit() never goes below 0.62), so then only the side panels count
  const underPanel = () => {
    const legend = document.getElementById('mlegend'), k = d3.zoomTransform(svg.node()).k;
    const tall = (TREE.bounds.y1 - TREE.bounds.y0) * k > stageSize()[1] - 18 - (legend.offsetHeight + 26);
    const panels = (tall ? ['#stack', '#insp'] : ['#stack', '#insp', '#mlegend', '.zoomctl']).map(s => [s, document.querySelector(s)]).filter(([, e]) => e && !e.hidden && e.offsetParent).map(([s, e]) => [s, e.getBoundingClientRect()]);
    const under = [];
    tSel.each(function (c) { const r = this.querySelector('.box').getBoundingClientRect(), p = r.width && panels.find(([, p]) => r.left < p.right && p.left < r.right && r.top < p.bottom && p.top < r.bottom); if (p) under.push(`${c.key} under ${p[0]}`); });
    return under;
  };
  // what the map shows at this moment: each card's marks and value, each line's state
  const KEEP = ['visited', 'live', 'current', 'isnew', 'edited'];
  const snap = () => [...document.querySelectorAll('g.tnode')].map(g => [g.__data__.key, g.getAttribute('class').split(' ').filter(c => KEEP.includes(c)).join('+'), (g.querySelector('.vtext') || {}).textContent || '', [...g.querySelectorAll('.marks circle')].map(c => c.getAttribute('class')).join('')].join(' ')).concat([...document.querySelectorAll('path.tlink')].map(p => `${(p.__data__ || {}).key} ${p.getAttribute('class').split(' ').sort().join(' ')}`));
  const firstDiff = (a, b) => { const i = a.findIndex((x, n) => x !== b[n]); return i < 0 ? null : `"${a[i]}" jumped to, "${b[i]}" stepped`; };
  const settle = () => new Promise(r => setTimeout(r, 3000));  // the previous run's animations finish
  // words the page must never show: a machine's folders, numbered objects (ReadStats#1), "your code"
  const wordsOK = where => {
    const text = document.body.innerText;
    const m = /(\/home\/|\/Users\/|\/tmp\/|[A-Za-z]:\\Users)\S*|\b[A-Za-z_]\w*#\d+\b|your code/i.exec(text);
    if (m) bad(where, `the page shows "${m[0]}"`);
  };
  const html = document.documentElement.outerHTML, path = /(\/home\/|\/Users\/|\/tmp\/|[A-Za-z]:\\\\?Users\\)[^\s"'<]*/.exec(html);
  if (path) bad('page', `a local path is in the page: "${path[0].slice(0, 60)}"`);
  try {
    for (const key of DATA.projects.map(p => p.key)) {
      useProject(key);
      for (let p = 0; p < PARTS.length; p++) {
        try { setPart(p, false); } catch (e) { log(`${key} part${p}`, e); continue; }
        const c = check(), where = `${key} Part ${PARTS[p].label}`;
        const part = (summary[key] ||= {})[PARTS[p].label] = { commit: PARTS[p].commit, cards: c.cards, lines: c.lines, runs: [] };
        notes.push(`${where}: columns [${c.cols.join(', ')}]; ${c.cards} cards (${c.isnew} new, ${c.changed} changed), ${c.lines} lines; overlaps ${c.hits}${c.ex.length ? ' ' + c.ex.join(' | ') : ''}; through cards ${c.thru}${c.tex.length ? ' ' + c.tex.join(' | ') : ''}`);
        const covered = underPanel();
        if (covered.length) bad(where, `${covered.length} cards under a panel (${covered.slice(0, 3).join(', ')})`);
        wordsOK(where);
        for (let r = 0; r < RUNS.length; r++) {
          try {
            loadRun(r); stop();
            const at = `${where} "${RUN.title}"`;
            const unmapped = [...new Set([...RUN.calls.values()].filter(k => !isTestFn(k.fn) && !TREE.ofCall.get(k.id)).map(k => k.fn))];
            const notBuilt = [...new Set([...RUN.calls.values()].filter(k => TREE.nodes.get(k.fn) && !builtNow(TREE.nodes.get(k.fn))).map(k => k.fn))];
            const noLine = [...new Set([...RUN.calls.values()].filter(k => { const c = TREE.ofCall.get(k.id), pp = RUN.calls.get(k.parent), f = pp && TREE.ofCall.get(pp.id); return c && f && c !== f && !k.mapEdge && !(f.start && !entryOK(k.fn)); }).map(k => RUN.calls.get(k.parent).fn.split('.').pop() + '→' + k.fn.split('.').slice(-2).join('.')))];
            const start = idx, first = firstCallText(), end = (jump(EV.length), endSummary());
            // the functions of yours the run shows, against the ones it really ran (the 5-step kind of bug hides most)
            const yoursOrMid = fn => NODE[fn] && (!inTests(fn) || isMid(fn));
            const ran = new Set(RUN.allEvents.filter(e => (e.k === 'call' || e.k === 'new') && yoursOrMid(e.fn)).map(e => e.fn));
            const shown = new Set([...RUN.calls.values()].filter(k => yoursOrMid(k.fn)).map(k => k.fn));
            part.runs.push({ title: RUN.title, start: first, steps: lastStep(), end, calls: [...shown].sort() });
            if (!first) bad(at, 'START is not a call of yours');
            if (!end) bad(at, 'END shows no output');
            if (shown.size < ran.size / 2) bad(at, `shows ${shown.size} of the ${ran.size} functions it ran`);
            // every step shows something: a caption, every time
            for (let k = 0; k < STEPS.length - 1; k++) {
              const e = EV[STEPS[k]];
              if (!captionFor(e)) { bad(at, `step ${k + 1} (${e.k} ${e.fn || e.label || ''}) shows nothing`); break; }
            }
            // stepping back matches stepping forward and jumping, at three places in the run
            await settle();
            for (const f of [0.25, 0.5, 0.75]) {
              const k = Math.max(1, Math.min(STEPS.length - 2, Math.round((STEPS.length - 1) * f)));
              if (k + 1 >= STEPS.length) break;
              jump(STEPS[k]); const A = snap();
              jump(STEPS[k - 1]); await stepForward(false); const B = snap();
              jump(STEPS[k + 1]); await stepBack(false); const C = snap();
              const d = firstDiff(A, B) || firstDiff(A, C);
              if (d) { bad(at, `step ${k + 1} looks different reached ${firstDiff(A, B) ? 'forward' : 'backward'}: ${d}`); break; }
            }
            jump(start);
            for (let i = idx; i < EV.length; i++) { try { await stepForward(false); } catch (e) { log(`${key} P${PARTS[p].label} ${RUN.key} ev${i}`, e); break; } if (i % 11 === 0 && EV[i].id && RUN.calls.has(EV[i].id)) selectCall(EV[i].id); }
            wordsOK(at);
            resumeFollow(); jump(start); for (let i = 0; i < 10; i++) await stepForward(true);
            wordsOK(at);
            const box = document.getElementById('inspTitle').textContent;
            notes.push(`   ▶ ${RUN.title}: starts at ${start}/${EV.length} "${first}", ends "${end}"; box now "${box}"${unmapped.length ? '; NOT ON MAP ' + unmapped.join(', ') : ''}${notBuilt.length ? '; NOT BUILT YET ' + notBuilt.join(', ') : ''}${noLine.length ? '; no line ' + noLine.join(', ') : ''}`);
          } catch (e) { log(`${key} P${PARTS[p].label} run${r}`, e); }
        }
        try { TREE.nodes.forEach(c => { if (c.isCol ? c.col.present : builtNow(c)) selectT(c.key); }); } catch (e) { log(`${key} select P${PARTS[p].label}`, e); }
      }
    }
    useProject(DATA.projects[0].key);
    notes.push(`speed menu: ${[...document.querySelectorAll('#bSpeed option')].map(o => o.textContent).join(' ')}; panel: ${document.querySelector('#stack .panel-title').textContent}; views: ${document.querySelectorAll('.segb').length} switches; parts ${D.key}: ${PARTS.map(p => p.label).join(' ')}`);
  } catch (e) { log('fatal', e); }
  const out = document.createElement('pre'); out.id = 'smoke';
  out.textContent = 'SMOKE ' + (errs.length ? 'FAIL\n' + errs.slice(0, 15).map(e => 'ERROR ' + e).join('\n') : 'OK') + '\n' + [...new Set(problems)].join('\n') + (problems.length ? '\n' : '') + notes.join('\n');
  document.body.appendChild(out);
  const sum = document.createElement('pre'); sum.id = 'summary';
  sum.textContent = JSON.stringify(summary);
  document.body.appendChild(sum);
};
window.addEventListener('load', () => setTimeout(() => window.__smoke(), 500));
