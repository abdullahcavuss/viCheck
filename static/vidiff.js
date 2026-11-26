/* Controller for the VI diff page and the single-VI viewer */
(function () {
  "use strict";
  const { Pane, Tip, ST, esc, nodeTipHtml } = window.VIDiagram;
  const T = window.T || ((s, kw) => { let r = s; if (kw) for (const k in kw) r = r.split("{" + k + "}").join(kw[k]); return r; });

  // ------------------------------------------------ shared: menu, primitive names
  const Ctx = {
    el: null,
    show(items, ev) {
      this.hide();
      const m = document.createElement("div");
      m.className = "ctx";
      for (const it of items) {
        const b = document.createElement("button");
        b.innerHTML = it.html || esc(it.label);
        b.onclick = () => { this.hide(); it.fn(); };
        m.appendChild(b);
      }
      document.body.appendChild(m);
      const w = m.offsetWidth, h = m.offsetHeight;
      m.style.left = Math.min(ev.clientX, innerWidth - w - 8) + "px";
      m.style.top = Math.min(ev.clientY, innerHeight - h - 8) + "px";
      this.el = m;
      setTimeout(() => document.addEventListener("click", this._off = () => this.hide(), { once: true }), 0);
    },
    hide() { if (this.el) { this.el.remove(); this.el = null; } },
  };

  async function loadPrimNames() {
    try { return await (await fetch("/api/prim-names")).json(); } catch (e) { return {}; }
  }
  async function renamePrim(resId, current, panes) {
    const name = prompt(T("Name for primitive #{id} (e.g. Add, Equal?, Index Array). Leave empty to delete the name.\nThis name is used in all VIs.", { id: resId }), current || "");
    if (name === null) return;
    const r = await fetch("/api/prim-names", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: resId, name }) });
    const names = await r.json();
    for (const p of panes) {
      const cam = Object.assign({}, p.cam);
      const act = Object.assign({}, p.active);
      p.primNames = names;
      p.render();
      for (const k in act) p.setFrame(k, act[k], false);
      p.setCamera(cam, true);
    }
  }

  function frameMenu(pane, n, ev) {
    Ctx.show(n.frames.map((f, i) => ({
      html: (i === pane.active[n.uid] ? "<b>✓ " : "&nbsp;&nbsp;&nbsp;") + esc(f.name) + (i === pane.active[n.uid] ? "</b>" : "") +
        (f.changes ? ` <span style="color:#d97706">● ${f.changes}</span>` : ""),
      fn: () => pane.setFrame(n.uid, i, true),
    })), ev);
  }

  function bindCommon(pane, panes, changesById) {
    pane.on("hover", (n, ev, p) => { Tip.show(nodeTipHtml(n, p, changesById), ev); });
    pane.on("wirehover", (w, ev) => {
      let h = `<b>${T("Wire")}</b> <span class="k">${esc(w.cat)}${w.arr ? " " + T("array") : ""}</span><br><span class="k">${T("{n} ends", { n: w.ends.length })}</span>`;
      if (w.st && w.st !== "same" && ST[w.st]) h += `<br><span class="stx">● ${ST[w.st].t}</span>`;
      Tip.show(h, ev);
    });
    pane.on("notehover", (t, ev) => {
      let h = `<b>${T("Comment")}</b><br>${esc(t.text.slice(0, 300))}`;
      if (t.st && t.st !== "same" && ST[t.st]) h += `<br><span class="stx">● ${ST[t.st].t}</span>`;
      Tip.show(h, ev);
    });
    pane.on("hovermove", (_, ev) => Tip.move(ev));
    pane.on("leave", () => Tip.hide());
    pane.on("framemenu", (n, ev, p) => frameMenu(p, n, ev));
    pane.on("context", (n, ev, p) => {
      const items = [];
      if (n.kind === "prim") items.push({ label: T("Name primitive…"), fn: () => renamePrim(n.prim, p.primNames[n.prim], panes) });
      if (n.frames && n.frames.length > 1) items.push({ label: T("Choose frame…"), fn: () => frameMenu(p, n, ev) });
      items.push({ label: T("Copy name"), fn: () => navigator.clipboard && navigator.clipboard.writeText(p.displayName(n)) });
      Ctx.show(items, ev);
    });
    pane.svg.addEventListener("dblclick", ev => {
      const g = ev.target.closest("[data-uid]");
      if (!g) return;
      const n = pane.find(g.dataset.uid);
      if (n && n.kind === "prim") renamePrim(n.prim, pane.primNames[n.prim], panes);
    });
  }

  // ================================================ SINGLE VI VIEWER
  async function initViewer(root) {
    const url = root.dataset.model;
    const holder = root.querySelector(".viewer");
    const loading = document.createElement("div");
    loading.className = "loading-overlay";
    loading.innerHTML = '<span class="spinner"></span><span>' + esc(T("Parsing the VI (no LabVIEW needed)…")) + '</span>';
    holder.appendChild(loading);
    const [model, names] = await Promise.all([fetch(url).then(r => r.json()), loadPrimNames()]);
    loading.remove();
    const pane = new Pane(holder, { side: "single" });
    pane.primNames = names;
    bindCommon(pane, [pane], {});
    pane.on("fitrequest", p => p.fit());
    pane.setModel(model);
    pane.fit(true);
    window.addEventListener("resize", () => {});
    const info = root.querySelector("[data-vi-info]");
    if (info) renderInfo(info, model);
  }

  function renderInfo(box, m) {
    let h = "";
    if (m.error) h += `<div class="notice">⚠ ${esc(m.error)}</div>`;
    const meta = m.meta || {};
    h += `<table class="kv">`;
    if (m.icon) h += `<tr><td>Icon</td><td><img src="${m.icon}" style="width:32px;height:32px;image-rendering:pixelated;border:1px solid var(--border)"></td></tr>`;
    if (meta.lv_version) h += `<tr><td>LabVIEW version</td><td>${esc(meta.lv_version_str || meta.lv_version)}</td></tr>`;
    if (m.stats) h += `<tr><td>Block diagram</td><td>${m.stats.nodes} nodes, ${m.stats.wires} wires</td></tr>`;
    if (meta.props) {
      const p = meta.props;
      h += `<tr><td>Reentrant</td><td>${p["Execution.IsReentrant"] === "1" ? "Yes" : "No"}</td></tr>`;
    }
    h += `</table>`;
    if (meta.description) h += `<div style="padding:10px 14px;white-space:pre-wrap;font-size:12.5px" class="muted">${esc(meta.description)}</div>`;
    if (m.fp && m.fp.length) {
      h += `<div style="padding:10px 14px 4px;font-weight:600">Front panel (${m.fp.length})</div><table class="kv">`;
      for (const c of m.fp) h += `<tr><td>${c.io === "indicator" ? "◀" : "▶"} ${esc(c.name)}</td><td class="faint">${esc(c.ctype_name || "")} · ${c.io === "indicator" ? "indicator" : "control"}</td></tr>`;
      h += `</table>`;
    }
    const subs = (m.deps || []).filter(d => d.kind === "IUVI" || d.kind === "PUPV");
    if (subs.length) {
      h += `<div style="padding:10px 14px 4px;font-weight:600">SubVIs (${subs.length})</div><table class="kv">`;
      for (const d of subs) h += `<tr><td>${esc(d.name)}</td></tr>`;
      h += `</table>`;
    }
    box.innerHTML = h;
  }

  // ================================================ DIFF PAGE
  async function initDiff(root) {
    const ds = root.dataset;
    let groupOn = ds.group === "1";     // related changes shown as one (setting)
    const panesBox = root.querySelector(".panes");
    const oldBox = root.querySelector(".pane.old"), newBox = root.querySelector(".pane.new");
    const loading = root.querySelector(".loading-overlay");
    const params = new URLSearchParams({ old: ds.old || "", new: ds.new || "", name: ds.fname || "x.vi" });
    let data;
    try {
      const [resp, names] = await Promise.all([fetch("/api/vidiff?" + params), loadPrimNames()]);
      data = await resp.json();
      data.names = names;
      if (data.error) throw new Error(data.error);
    } catch (e) {
      loading.innerHTML = esc(T("⚠ Could not compute the diff:")) + " " + esc(e.message);
      return;
    }
    loading.remove();
    const diff = data.diff;
    const changes = diff.changes;
    const byId = {};
    changes.forEach(c => byId[c.id] = c);

    const oldPane = new Pane(oldBox, { side: "old", diff: true });
    const newPane = new Pane(newBox, { side: "new", diff: true });
    const panes = [oldPane, newPane];
    const state = { mode: "split", sync: true, off: { x: diff.shift[0], y: diff.shift[1] }, dimSame: true, showMoved: false };
    for (const p of panes) { p.primNames = data.names; p.dimSame = state.dimSame; p.showMoved = state.showMoved; bindCommon(p, panes, byId); }
    oldPane.setLabel(`<b class="tagold">A</b> ${esc(ds.oldLabel || "")}`);
    newPane.setLabel(`<b class="tagnew">B</b> ${esc(ds.newLabel || "")}`);
    for (const p of panes) p.showNames = false;
    oldPane.setModel(data.old);
    newPane.setModel(data.new);
    alignFrames();

    // On open: show the frames that contain changes and align both sides to the same frame
    function alignFrames() {
      const pick = (p) => {
        for (const uid in p.frameRefs) {
          const n = p.frameRefs[uid].node;
          const act = p.active[uid];
          if (n.frames[act] && n.frames[act].changes) continue;
          let best = -1, bc = 0;
          n.frames.forEach((f, i) => { if (f.changes > bc) { bc = f.changes; best = i; } });
          if (best >= 0) p.setFrame(uid, best, false);
        }
      };
      pick(newPane);
      pick(oldPane);
      for (const uid in newPane.frameRefs) {
        const n = newPane.frameRefs[uid].node;
        if (!n.pid) continue;
        const cp = oldPane.findByPid(n.pid);
        if (!cp || !cp.frames) continue;
        const name = n.frames[newPane.active[uid]].name;
        const j = cp.frames.findIndex(f => f.name === name);
        const curOld = cp.frames[oldPane.active[cp.uid]];
        if (j >= 0 && !(curOld && curOld.changes && !n.frames[newPane.active[uid]].changes)) oldPane.setFrame(cp.uid, j, false);
      }
    }

    // synced camera
    let syncing = false;
    oldPane.on("camera", c => { if (state.sync && !syncing && state.mode === "split") { syncing = true; newPane.setCamera({ x: c.x + state.off.x, y: c.y + state.off.y, s: c.s }, true); syncing = false; } });
    newPane.on("camera", c => { if (state.sync && !syncing && state.mode === "split") { syncing = true; oldPane.setCamera({ x: c.x - state.off.x, y: c.y - state.off.y, s: c.s }, true); syncing = false; } });

    function fitAll() {
      const ob = oldPane.model.bd_bounds, nb = newPane.model.bd_bounds;
      const hasOld = data.old.bd && data.old.bd.nodes.length, hasNew = data.new.bd && data.new.bd.nodes.length;
      state.off = { x: diff.shift[0], y: diff.shift[1] };
      if (state.mode === "split" && hasOld && hasNew) {
        const u = [Math.min(ob[0], nb[0] - state.off.x), Math.min(ob[1], nb[1] - state.off.y), Math.max(ob[2], nb[2] - state.off.x), Math.max(ob[3], nb[3] - state.off.y)];
        oldPane.fitBounds(u, true);
        newPane.setCamera({ x: oldPane.cam.x + state.off.x, y: oldPane.cam.y + state.off.y, s: oldPane.cam.s }, true);
      } else {
        if (hasOld) oldPane.fit(true);
        if (hasNew) newPane.fit(true);
      }
    }
    oldPane.on("fitrequest", fitAll);
    newPane.on("fitrequest", fitAll);
    requestAnimationFrame(fitAll);
    let rT;
    window.addEventListener("resize", () => { clearTimeout(rT); rT = setTimeout(fitAll, 150); });

    // frame sync
    function syncFrame(n, idx, src) {
      const other = src === oldPane ? newPane : oldPane;
      if (!n.pid) return;
      const cp = other.findByPid(n.pid);
      if (!cp || !cp.frames) return;
      const name = n.frames[idx].name;
      let j = cp.frames.findIndex(f => f.name === name);
      if (j < 0 && idx < cp.frames.length) j = idx;
      if (j >= 0) other.setFrame(cp.uid, j, false);
    }
    oldPane.on("frame", syncFrame);
    newPane.on("frame", syncFrame);

    // on click, show the counterpart
    function showCounterpart(n, src) {
      const other = src === oldPane ? newPane : oldPane;
      if (!n.pid) { src.flash(n.uid); return; }
      const cp = other.findByPid(n.pid);
      src.flash(n.uid);
      if (cp) other.flash(cp.uid);
      const relevant = changes.find(c => (c.old_uid === n.uid || c.new_uid === n.uid));
      if (relevant) selectChange(relevant.id, false);
    }
    oldPane.on("click", (n) => showCounterpart(n, oldPane));
    newPane.on("click", (n) => showCounterpart(n, newPane));

    // ------------------------------------------------ side panel
    const side = root.querySelector(".vd-side");
    const list = side.querySelector(".vd-list");
    const filterBox = side.querySelector(".vd-filter");
    const tabs = side.querySelectorAll(".vd-tabs button");
    const counts = diff.counts;
    const FILTERS = [
      { key: "added", label: T("Added"), color: "#1a7f37", kinds: ["added"], on: true },
      { key: "removed", label: T("Removed"), color: "#cf222e", kinds: ["removed"], on: true },
      { key: "modified", label: T("Modified"), color: "#d97706", kinds: ["modified"], on: true },
      { key: "reframe", label: T("Moved to another frame"), color: "#8250df", kinds: [], on: true, reframe: true },
      { key: "wire", label: T("Wires"), color: "#57606a", kinds: ["wire_added", "wire_removed", "wire_modified"], on: true },
      { key: "note", label: T("Comments"), color: "#c9b400", kinds: ["note_added", "note_removed"], on: true },
      { key: "moved", label: T("Moved"), color: "#2f6feb", kinds: ["moved"], on: false },
      { key: "typedef", label: T("Typedef / global it uses changed"), color: "#8c959f", kinds: [], on: true, typedef: true },
      { key: "auto", label: T("Timed Loop / XNode internal setting"), color: "#8b949e", kinds: [], on: false, auto: true },
      { key: "minor", label: T("Not counted as a change"), color: "#a8b1bb", kinds: [], on: true, minor: true },
    ];
    const nReframe = changes.filter(c => c.reframe).length;
    function kindCount(f) {
      if (f.auto) return counts.auto || 0;
      if (f.typedef) return counts.typedef || 0;
      if (f.minor) return counts.minor || 0;
      if (f.reframe) return nReframe;
      return f.kinds.reduce((a, k) => a + (counts[k] || 0), 0) - (f.key === "modified" ? nReframe : 0);
    }
    for (const p of panes) { p.showAuto = false; }
    filterBox.innerHTML = "";
    for (const f of FILTERS) {
      const n = kindCount(f);
      if (!n) continue;
      const c = document.createElement("span");
      c.className = "chip" + (f.on ? " on" : "");
      c.innerHTML = `<i style="background:${f.color}"></i>${f.label} ${n}`;
      c.onclick = () => {
        f.on = !f.on;
        c.classList.toggle("on", f.on);
        if (f.key === "auto") { for (const p of panes) { p.showAuto = f.on; rerender(p); } }
        if (f.key === "moved") { state.showMoved = f.on; for (const p of panes) { p.showMoved = f.on; rerender(p); } root.querySelector("[data-opt=moved]").checked = f.on; }
        renderList();
      };
      filterBox.appendChild(c);
    }
    if (changes.some(c => c.group_members)) {
      const g = document.createElement("span");
      g.className = "chip grp-chip" + (groupOn ? " on" : "");
      g.title = T("Show related changes (a node with its wires, items moved into a new structure, updates of one typedef …) as one change");
      g.innerHTML = `<i style="background:#57606a"></i>${esc(T("Join related changes"))}`;
      g.onclick = () => {
        groupOn = !groupOn;
        g.classList.toggle("on", groupOn);
        fetch("/api/setting", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: "group_changes", value: groupOn }) });
        setBdCount();
        renderList();
      };
      filterBox.appendChild(g);
    }
    let currentTab = "bd";
    let selected = null;
    const ICON = { added: ["added", "+"], removed: ["removed", "−"], modified: ["modified", "~"], moved: ["moved", "↔"], typedef: ["typedef", "◌"],
      wire_added: ["added", "⌁"], wire_removed: ["removed", "⌁"], wire_modified: ["modified", "⌁"], note_added: ["added", "✎"], note_removed: ["removed", "✎"] };

    function changeName(c) {
      let t = c.title;
      for (const [pane, uid] of [[newPane, c.new_uid], [oldPane, c.old_uid]]) {
        const n = uid && pane.find(uid);
        if (n && n.kind === "prim") { t = t.replace(/“Prim \d+”/, "“" + pane.displayName(n) + "”"); break; }
      }
      return t;
    }

    function renderList() {
      list.innerHTML = "";
      if (currentTab === "bd") {
        const on = new Set(FILTERS.filter(f => f.on).flatMap(f => f.kinds));
        const autoOn = FILTERS.find(f => f.auto).on;
        const reframeOn = FILTERS.find(f => f.reframe).on;
        const tdOn = FILTERS.find(f => f.typedef).on;
        const minorOn = FILTERS.find(f => f.minor).on;
        const items = changes.filter(c => c.cat === "auto" ? autoOn : c.cat === "typedef" ? tdOn : c.cat === "minor" ? minorOn : c.reframe ? reframeOn : on.has(c.kind));
        if (!items.length) {
          list.innerHTML = `<div class="empty small">${changes.length ? esc(T("No changes match the filter.")) : esc(T("No functional change found on the block diagram.")) + "<br><span class=\"faint\">" + esc(T("The file was most likely only re-saved or recompiled.")) + "</span>"}</div>`;
        }
        const itemEl = (c, cls, extra) => {
          const d = document.createElement("div");
          d.className = "vd-item" + (cls || "") + (selected === c.id ? " sel" : "");
          d.dataset.id = c.id;
          const ic = c.cat === "typedef" ? ["typedef", "◌"] : c.cat === "minor" ? ["minor", "·"] : c.reframe ? ["reframed", "⤳"] : (ICON[c.kind] || ["modified", "•"]);
          // a wire (or a group of wires) is told by what it connects; other changes keep their title
          const sents = ((extra && extra.story) || c.story_text || []).map(primText);
          const wireish = c.kind.startsWith("wire");
          const title = (extra && extra.title) || (wireish && sents.length ? sents[0] : changeName(c));
          const lines = wireish && !(extra && extra.title) ? sents.slice(1) : sents;
          const detail = wireish && sents.length ? "" : c.detail;
          d.innerHTML = `<span class="st ${ic[0]}">${ic[1]}</span><div style="min-width:0"><div class="t">${esc(title)}</div>${detail ? `<div class="d">${esc(detail)}</div>` : ""}${lines.length ? `<ul class="story">${lines.map(l => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}${extra && extra.rel ? `<div class="rel">${extra.rel}</div>` : ""}${c.path ? `<div class="p">↳ ${esc(c.path)}</div>` : ""}</div>`;
          return d;
        };
        if (!groupOn) {
          for (const c of items) {
            const d = itemEl(c);
            d.onclick = () => selectChange(c.id, true);
            list.appendChild(d);
          }
        } else {
          // related changes as one item: the group's main change, the others folded under it
          const shown = new Set(items.map(c => c.id));
          const done = new Set();
          for (const c of items) {
            const g = c.group != null ? c.group : c.id;
            if (done.has(g)) continue;
            done.add(g);
            const main = byId[g];
            const members = (main.group_members || [main.id]).filter(i => shown.has(i)).map(i => byId[i]);
            const head = shown.has(main.id) ? main : members[0];
            const rest = members.filter(m => m !== head);
            const gs = (main.gstory_text || []);
            const wireGroup = head.kind.startsWith("wire");
            const d = itemEl(head, rest.length ? " grp" : "", {
              title: main.group_title || (wireGroup && gs.length ? primText(gs[0]) : changeName(head)),
              story: wireGroup ? gs.slice(1) : gs,
              rel: rest.length ? relText(rest) : "" });
            d.onclick = ev => {
              if (ev.target.closest(".rel")) { d.classList.toggle("open"); return; }
              selectGroup(head.id, members.map(m => m.id));
            };
            list.appendChild(d);
            if (rest.length) {
              const sub = document.createElement("div");
              sub.className = "vd-sub";
              for (const m of rest) {
                const e = itemEl(m, " member");
                e.onclick = () => selectChange(m.id, true);
                sub.appendChild(e);
              }
              list.appendChild(sub);
            }
          }
        }
      } else if (currentTab === "fp") {
        if (!fpMarks.length) list.innerHTML = `<div class="empty small">${esc(T("No front panel control was added, removed, changed or moved."))}</div>`;
        for (const c of fpMarks) {
          const ic = ICON[c.kind] || ICON.modified;
          list.insertAdjacentHTML("beforeend", `<div class="vd-item" data-fp="${c.num}"><span class="st ${ic[0]}">${c.num}</span><div><div class="t">${esc(c.name)}</div><div class="d">${esc(c.detail)}</div></div></div>`);
        }
        list.querySelectorAll(".vd-item[data-fp]").forEach(d => d.onclick = () => focusFP(+d.dataset.fp));
        const fp = data.new.fp && data.new.fp.length ? data.new.fp : data.old.fp || [];
        if (fp.length) {
          let h = `<div style="padding:12px 14px 4px;font-weight:600;font-size:12.5px" class="muted">${esc(T("Controls in B"))}</div><table class="kv">`;
          for (const c of fp) h += `<tr><td>${c.io === "indicator" ? "◀" : "▶"} ${esc(c.name)}</td><td class="faint">${esc(c.ctype_name || "")}</td></tr>`;
          list.insertAdjacentHTML("beforeend", h + "</table>");
        }
      } else if (currentTab === "deps") {
        if (!diff.deps.length) list.innerHTML = `<div class="empty small">${esc(T("Dependencies (subVIs, typedefs, libraries) did not change."))}</div>`;
        for (const c of diff.deps) {
          const ic = ICON[c.kind];
          list.insertAdjacentHTML("beforeend", `<div class="vd-item"><span class="st ${ic[0]}">${ic[1]}</span><div><div class="t">${esc(c.name)}</div><div class="d">${c.kind === "added" ? T("added") : T("removed")} · ${esc(c.link)}</div></div></div>`);
        }
      } else if (currentTab === "props") {
        const mo = data.old.meta || {}, mn = data.new.meta || {};
        let h = `<table class="kv"><tr><td>${esc(T("LabVIEW version"))}</td><td>${esc(mo.lv_version_str || mo.lv_version || "—")} → ${esc(mn.lv_version_str || mn.lv_version || "—")}</td></tr>`;
        if (data.old.stats && data.new.stats) h += `<tr><td>${esc(T("Nodes / wires"))}</td><td>${data.old.stats.nodes}/${data.old.stats.wires} → ${data.new.stats.nodes}/${data.new.stats.wires}</td></tr>`;
        h += `</table>`;
        if (!diff.props.length) h += `<div class="empty small">${esc(T("VI properties did not change."))}</div>`;
        else {
          h += `<table class="kv">`;
          for (const p of diff.props.sort((a, b) => (b.important - a.important))) h += `<tr><td>${p.important ? "<b>" + esc(p.label) + "</b>" : esc(p.label)}</td><td class="old">${esc(p.old ?? "—")}</td><td class="new">${esc(p.new ?? "—")}</td></tr>`;
          h += `</table>`;
        }
        if (mo.description !== mn.description) h += `<div style="padding:10px 14px"><b>${esc(T("Description changed"))}</b><div class="small" style="white-space:pre-wrap;margin-top:6px"><span class="num-del">− ${esc(mo.description || "")}</span><br><span class="num-add">+ ${esc(mn.description || "")}</span></div></div>`;
        list.innerHTML = h;
      }
      filterBox.style.display = currentTab === "bd" ? "" : "none";
    }
    tabs.forEach(b => b.onclick = () => {
      tabs.forEach(x => x.classList.toggle("on", x === b));
      const was = currentTab;
      currentTab = b.dataset.tab;
      renderList();
      // the Panel tab shows the front panels; the other tabs the block diagrams
      if ((currentTab === "fp") !== fpOn && (currentTab === "fp" || was === "fp")) showFP(currentTab === "fp");
    });
    const setN = (tab, n) => { const s = side.querySelector(`[data-tab=${tab}] .n`); if (s) s.textContent = n; };
    const setBdCount = () => setN("bd", groupOn ? groupCount() : changes.filter(c => c.kind !== "moved").length);
    setBdCount();
    setN("fp", (diff.fp_marks || diff.fp).length);
    setN("deps", diff.deps.length);
    setN("props", diff.props.length);

    function locate(pane, uid, reveal, kind) {
      if (!uid) return null;
      pane.reveal(reveal);
      if (kind.startsWith("wire")) {
        const w = pane.allWires().find(x => x.uid === uid);
        if (!w) return null;
        const xs = w.ends.map(e => e.x), ys = w.ends.map(e => e.y);
        return { box: [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)], fl: () => pane.flashWire(w) };
      }
      if (kind.startsWith("note")) {
        const t = pane.allNotes().find(x => x.uid === uid);
        if (!t) return null;
        return { box: [t.x, t.y, t.w, t.h], fl: () => {} };
      }
      const n = pane.find(uid);
      if (!n) return null;
      return { box: [n.x, n.y, n.w, n.h], fl: () => pane.flash(uid) };
    }

    // ------------------------------------------------ related changes shown as one (setting; can be switched off)
    function relText(rest) {
      const n = { wire: 0, reframe: 0, added: 0, removed: 0, modified: 0, typedef: 0, minor: 0, other: 0 };
      for (const m of rest) {
        if (m.cat === "minor") n.minor++;
        else if (m.kind.startsWith("wire")) n.wire++;
        else if (m.cat === "typedef") n.typedef++;
        else if (m.reframe) n.reframe++;
        else if (n[m.kind] !== undefined) n[m.kind]++;
        else n.other++;
      }
      const parts = [];
      if (n.added) parts.push(T("{n} added", { n: n.added }));
      if (n.removed) parts.push(T("{n} removed", { n: n.removed }));
      if (n.modified) parts.push(T("{n} modified", { n: n.modified }));
      if (n.reframe) parts.push(T("{n} moved into/out of it", { n: n.reframe }));
      if (n.typedef) parts.push(T("{n} typedef/global update(s)", { n: n.typedef }));
      if (n.wire) parts.push(T("{n} wire(s)", { n: n.wire }));
      if (n.minor) parts.push(T("{n} not counted as change(s)", { n: n.minor }));
      if (n.other) parts.push(String(n.other));
      return `<span class="rel-tg">▸</span> ${esc(T("+{n} related: ", { n: rest.length }))}${esc(parts.join(", "))}`;
    }
    // "Prim 1102" in a sentence -> the primitive's name, when known
    function primText(t) {
      const names = (oldPane && oldPane.primNames) || {};
      return String(t).replace(/Prim (\d+)/g, (m, id) => names[id] || m);
    }
    function groupCount() {
      return new Set(changes.filter(c => c.kind !== "moved").map(c => c.group != null ? c.group : c.id)).size;
    }
    function selectGroup(id, ids) {
      selected = id;
      list.querySelectorAll(".vd-item").forEach(d => d.classList.toggle("sel", +d.dataset.id === id));
      const main = byId[id];
      // show the main change's frames, then fit every member that is visible there
      const boxes = { old: [], new: [] }, fls = [];
      for (const [pane, side] of [[oldPane, "old"], [newPane, "new"]]) {
        const r = main[side + "_reveal"];
        if (r) pane.reveal(r);
        for (const i of ids) {
          const c = byId[i];
          const uid = c[side + "_uid"];
          if (!uid) continue;
          let box = null;
          if (c.kind.startsWith("wire")) {
            const w = pane.allWires().find(x => x.uid === uid);
            if (w) { const xs = w.ends.map(e => e.x), ys = w.ends.map(e => e.y); box = [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)]; fls.push(() => pane.flashWire(w)); }
          } else {
            const n = pane.find(uid);
            if (n) { box = [n.x, n.y, n.w, n.h]; fls.push(() => pane.flash(uid)); }
          }
          if (box) boxes[side].push(box);
        }
      }
      const union = bs => {
        if (!bs.length) return null;
        const x0 = Math.min(...bs.map(b => b[0])), y0 = Math.min(...bs.map(b => b[1]));
        return [x0, y0, Math.max(...bs.map(b => b[0] + b[2])) - x0, Math.max(...bs.map(b => b[1] + b[3])) - y0];
      };
      const bo = union(boxes.old), bn = union(boxes.new), ref = bn || bo;
      if (!ref) return selectChange(id, true);
      const sz = (bn ? newPane : oldPane).size();
      const s = Math.min(2.4, Math.max(0.3, Math.min(sz.w / (ref[2] + 200), sz.h / (ref[3] + 160))));
      if (bo) oldPane.centerOn(...bo, s);
      if (bn) newPane.centerOn(...bn, s);
      if (bo && bn) state.off = { x: newPane.cam.x - oldPane.cam.x, y: newPane.cam.y - oldPane.cam.y };
      else if (bo) newPane.setCamera({ x: oldPane.cam.x + state.off.x, y: oldPane.cam.y + state.off.y, s }, true);
      else if (bn) oldPane.setCamera({ x: newPane.cam.x - state.off.x, y: newPane.cam.y - state.off.y, s }, true);
      fls.forEach(f => f());
    }

    function selectChange(id, focus) {
      selected = id;
      list.querySelectorAll(".vd-item").forEach(d => d.classList.toggle("sel", +d.dataset.id === id));
      const sel = list.querySelector(`.vd-item[data-id="${id}"]`);
      if (sel && !focus) sel.scrollIntoView({ block: "nearest" });
      if (!focus) return;
      const c = byId[id];
      const lo = locate(oldPane, c.old_uid, c.old_reveal, c.kind);
      const ln = locate(newPane, c.new_uid, c.new_reveal, c.kind);
      const ref = ln || lo;
      if (!ref) return;
      const sz = (ln ? newPane : oldPane).size();
      const s = Math.min(2.4, Math.max(0.45, Math.min(sz.w / (ref.box[2] + 360), sz.h / (ref.box[3] + 260))));
      if (lo) oldPane.centerOn(...lo.box, s);
      if (ln) newPane.centerOn(...ln.box, s);
      if (lo && ln) state.off = { x: newPane.cam.x - oldPane.cam.x, y: newPane.cam.y - oldPane.cam.y };
      else if (lo) newPane.setCamera({ x: oldPane.cam.x + state.off.x, y: oldPane.cam.y + state.off.y, s }, true);
      else if (ln) oldPane.setCamera({ x: newPane.cam.x - state.off.x, y: newPane.cam.y - state.off.y, s }, true);
      if (state.mode === "old" && !lo && ln) setMode("new");
      if (state.mode === "new" && !ln && lo) setMode("old");
      if (lo) lo.fl();
      if (ln) ln.fl();
    }

    // keyboard: move between changes with j/k
    document.addEventListener("keydown", ev => {
      if (ev.target.matches("input,textarea,select")) return;
      const items = [...list.querySelectorAll(".vd-item[data-id]")];
      if (!items.length) return;
      let idx = items.findIndex(d => +d.dataset.id === selected);
      if (ev.key === "j" || ev.key === "ArrowDown") { idx = Math.min(items.length - 1, idx + 1); selectChange(+items[idx].dataset.id, true); items[idx].scrollIntoView({ block: "nearest" }); ev.preventDefault(); }
      if (ev.key === "k" || ev.key === "ArrowUp") { idx = Math.max(0, idx - 1); selectChange(+items[idx].dataset.id, true); items[idx].scrollIntoView({ block: "nearest" }); ev.preventDefault(); }
    });


    // ------------------------------------------------ front panel view (Panel tab): server-drawn SVG, pan/zoom, synced
    const fpMarks = diff.fp_marks || [];
    const fpBoxes = { old: root.querySelector(".pane.fpv.old"), new: root.querySelector(".pane.fpv.new") };
    let fpOn = false, fpLoaded = false, fpSync = false;
    const fpViews = {};
    function FPView(box, side, label) {
      const v = { box, side, svg: null, vb0: null, vb: null };
      box.innerHTML = `<div class="pane-label">${label}</div><div class="fp-host"></div>` +
        `<div class="zoom-ctl"><button type="button" data-z="in" title="${esc(T("Zoom in"))}">+</button><button type="button" data-z="out" title="${esc(T("Zoom out"))}">−</button><button type="button" data-z="fit" title="${esc(T("Fit"))}">⤢</button></div>`;
      const host = box.querySelector(".fp-host");
      v.apply = (vb, fromSync) => {
        v.vb = vb;
        if (v.svg) v.svg.setAttribute("viewBox", vb.map(n => n.toFixed(1)).join(" "));
        if (!fromSync && state.sync && !fpSync) {
          fpSync = true;
          const o = fpViews[side === "old" ? "new" : "old"];
          if (o && o.svg) o.apply(vb.slice(), true);
          fpSync = false;
        }
      };
      v.fit = () => { if (v.vb0) v.apply(v.vb0.slice()); };
      v.zoom = (f, cx, cy) => {
        const [x, y, w, h] = v.vb;
        const nw = Math.max(40, Math.min(v.vb0[2] * 6, w * f)), k = nw / w, nh = h * k;
        v.apply([cx - (cx - x) * k, cy - (cy - y) * k, nw, nh]);
      };
      v.toPanel = (ev) => {     // client point -> panel coordinates
        const r = v.svg.getBoundingClientRect(), [x, y, w, h] = v.vb;
        const s = Math.max(w / r.width, h / r.height);     // preserveAspectRatio: meet
        const ox = (r.width * s - w) / 2, oy = (r.height * s - h) / 2;
        return [x - ox + (ev.clientX - r.left) * s, y - oy + (ev.clientY - r.top) * s, s];
      };
      v.load = async () => {
        const p = new URLSearchParams({ old: ds.old || "", new: ds.new || "", side, name: ds.fname || "x.vi" });
        host.innerHTML = await (await fetch("/api/fp-svg?" + p)).text();
        v.svg = host.querySelector("svg");
        if (!v.svg) return;
        v.svg.removeAttribute("width"); v.svg.removeAttribute("height");
        v.vb0 = v.svg.getAttribute("viewBox").split(/\s+/).map(Number);
        v.vb = v.vb0.slice();
        v.svg.addEventListener("wheel", ev => {
          ev.preventDefault();
          const [px, py] = v.toPanel(ev);
          v.zoom(ev.deltaY > 0 ? 1.15 : 1 / 1.15, px, py);
        }, { passive: false });
        let drag = null;
        v.svg.addEventListener("mousedown", ev => { drag = { x: ev.clientX, y: ev.clientY, vb: v.vb.slice(), s: v.toPanel(ev)[2] }; v.svg.classList.add("dragging"); });
        window.addEventListener("mousemove", ev => {
          if (!drag) return;
          v.apply([drag.vb[0] - (ev.clientX - drag.x) * drag.s, drag.vb[1] - (ev.clientY - drag.y) * drag.s, drag.vb[2], drag.vb[3]]);
        });
        window.addEventListener("mouseup", () => { drag = null; v.svg.classList.remove("dragging"); });
        v.svg.addEventListener("click", ev => {
          const t = ev.target.closest(".fptab");
          if (t) { setFPPage(t.dataset.tab, +t.dataset.page); return; }
          const m = ev.target.closest(".fpmark,.fpbadge");
          if (m) focusFP(+m.dataset.num);
        });
      };
      box.querySelectorAll("[data-z]").forEach(b => b.onclick = () => {
        if (!v.svg) return;
        if (b.dataset.z === "fit") return v.fit();
        const [x, y, w, h] = v.vb;
        v.zoom(b.dataset.z === "in" ? 1 / 1.3 : 1.3, x + w / 2, y + h / 2);
      });
      return v;
    }
    async function showFP(on) {
      fpOn = on;
      oldBox.hidden = newBox.hidden = on;
      fpBoxes.old.hidden = fpBoxes.new.hidden = !on;
      root.querySelectorAll("[data-opt=dim],[data-opt=moved],[data-opt=flat],[data-opt=names]").forEach(i => i.closest("label").classList.toggle("off", on));
      setMode(state.mode);
      if (on && !fpLoaded) {
        fpLoaded = true;
        fpViews.old = FPView(fpBoxes.old, "old", `<b class="tagold">A</b> ${esc(ds.oldLabel || "")}`);
        fpViews.new = FPView(fpBoxes.new, "new", `<b class="tagnew">B</b> ${esc(ds.newLabel || "")}`);
        await Promise.all([fpViews.old.load(), fpViews.new.load()]);
        // both panels in the same frame: the union of the two drawings
        const a = fpViews.old.vb0, b = fpViews.new.vb0;
        if (a && b) {
          const u = [Math.min(a[0], b[0]), Math.min(a[1], b[1])];
          u.push(Math.max(a[0] + a[2], b[0] + b[2]) - u[0], Math.max(a[1] + a[3], b[1] + b[3]) - u[1]);
          fpViews.old.vb0 = u.slice(); fpViews.new.vb0 = u.slice();
        }
        fpViews.old.fit(); fpViews.new.fit();
      }
    }
    // tab control pages: shown in both panes (matched by the tab control's name and the page index)
    function setFPPage(tab, page) {
      for (const s of ["old", "new"]) {
        const v = fpViews[s];
        if (!v || !v.svg) continue;
        v.svg.querySelectorAll(".fppage").forEach(g => { if (g.dataset.tab === tab) g.style.display = +g.dataset.page === page ? "" : "none"; });
        v.svg.querySelectorAll(".fptab").forEach(g => { if (g.dataset.tab === tab) g.classList.toggle("on", +g.dataset.page === page); });
      }
    }
    function focusFP(num) {
      list.querySelectorAll(".vd-item[data-fp]").forEach(d => d.classList.toggle("sel", +d.dataset.fp === num));
      // a change on a hidden tab page: show that page first
      for (const s of ["new", "old"]) {
        const v = fpViews[s];
        const r = v && v.svg && v.svg.querySelector(`.fpmark[data-num="${num}"]`);
        if (!r) continue;
        const pages = [];
        for (let g = r.parentNode; g && g !== v.svg; g = g.parentNode) if (g.classList && g.classList.contains("fppage")) pages.unshift(g);
        pages.forEach(g => setFPPage(g.dataset.tab, +g.dataset.page));
        break;
      }
      let box = null;
      for (const s of ["new", "old"]) {
        const v = fpViews[s];
        const r = v && v.svg && v.svg.querySelector(`.fpmark[data-num="${num}"]`);
        if (!r || !r.getClientRects().length) continue;
        r.classList.remove("flash"); void r.getBBox(); r.classList.add("flash");
        if (!box) box = r.getBBox();
      }
      if (!box) return;
      const w = Math.max(box.width * 2.2, 420), h = Math.max(box.height * 2.2, 260);
      const vb = [box.x + box.width / 2 - w / 2, box.y + box.height / 2 - h / 2, w, h];
      for (const s of ["old", "new"]) if (fpViews[s] && fpViews[s].svg) fpViews[s].apply(vb.slice(), true);
    }

    // ------------------------------------------------ toolbar
    function setMode(m) {
      state.mode = m;
      root.querySelectorAll("[data-mode]").forEach(b => b.classList.toggle("on", b.dataset.mode === m));
      oldBox.classList.toggle("hidden", m === "new");
      newBox.classList.toggle("hidden", m === "old");
      fpBoxes.old.classList.toggle("hidden", m === "new");
      fpBoxes.new.classList.toggle("hidden", m === "old");
      panesBox.classList.toggle("single", m !== "split");
      requestAnimationFrame(() => {
        if (m === "old") oldPane.setCamera(oldPane.cam, true);
        if (m === "new") newPane.setCamera(newPane.cam, true);
        if (m === "split") fitAll();
      });
    }
    root.querySelectorAll("[data-mode]").forEach(b => b.onclick = () => setMode(b.dataset.mode));
    function rerender(p) {
      const cam = Object.assign({}, p.cam), act = Object.assign({}, p.active);
      p.render();
      for (const k in act) p.setFrame(k, act[k], false);
      p.setCamera(cam, true);
    }
    root.querySelector("[data-opt=dim]").onchange = e => { for (const p of panes) { p.dimSame = e.target.checked; rerender(p); } };
    root.querySelector("[data-opt=moved]").onchange = e => { state.showMoved = e.target.checked; for (const p of panes) { p.showMoved = e.target.checked; rerender(p); } };
    const flatOpt = root.querySelector("[data-opt=flat]");
    if (flatOpt) flatOpt.onchange = e => {
      for (const p of panes) { p.flatSeq = e.target.checked; p.setModel(p.sourceModel); }
      alignFrames();
      fitAll();
    };
    root.querySelector("[data-opt=sync]").onchange = e => { state.sync = e.target.checked; };
    root.querySelector("[data-opt=names]").onchange = e => { for (const p of panes) { p.showNames = e.target.checked; rerender(p); } };

    // version selectors
    root.querySelectorAll("select[data-ver]").forEach(s => s.onchange = () => {
      const u = new URL(location.href);
      u.searchParams.set(s.dataset.ver, s.value);
      u.searchParams.delete("old_sha"); u.searchParams.delete("new_sha");
      location.href = u.toString();
    });

    // warnings
    const warn = [data.old.error, data.new.error].filter(Boolean);
    if (warn.length) side.querySelector(".head").insertAdjacentHTML("beforeend", warn.map(w => `<div class="notice" style="margin:10px 0 0">⚠ ${esc(w)}</div>`).join(""));
    // icons
    const icons = side.querySelector(".vd-icons");
    if (icons) {
      icons.innerHTML = (data.old.icon ? `<img src="${data.old.icon}" title="${esc(T("Icon of A"))}">` : `<span class="faint small">—</span>`) +
        `<span class="arrow">→</span>` + (data.new.icon ? `<img src="${data.new.icon}" title="${esc(T("Icon of B"))}">` : `<span class="faint small">—</span>`) +
        (data.old.icon && data.new.icon && data.old.icon !== data.new.icon ? `<span class="pill" style="color:var(--mod)">${esc(T("icon changed"))}</span>` : "") +
        `<span class="grow"></span><span class="small muted">${T(diff.functional === 1 ? "{n} change" : "{n} changes", { n: diff.functional })}</span>`;
    }
    // file-level verdict: which section did the change happen in?
    const v = diff.verdict;
    if (v) {
      const LV = { functional: T("Content changed"), layout: T("Visual/layout only"), saved: T("Re-saved only"),
                   typedef: T("Only typedefs / globals it uses changed (value unchanged)"),
                   minor: T("Only differences not counted as changes") };
      let h = `<div class="verdict ${v.level}"><div class="vt">${LV[v.level]}</div>`;
      if (!v.parts.length || (v.parts.length === 1 && v.parts[0].key === "version"))
        h += `<div class="small muted">${esc(T("Block diagram, front panel, connector pane, dependencies and settings are the same; only revision/compile information changed."))}</div>`;
      for (const p of v.parts) h += `<div class="vp"><span class="part ${p.level}">${esc(p.label)}</span>${p.detail ? ` <span class="small">${esc(p.detail)}</span>` : ""}</div>`;
      side.querySelector(".head").insertAdjacentHTML("beforeend", h + "</div>");
    }
    renderList();
    if (!changes.filter(c => c.kind !== "moved").length && !diff.fp.length && !diff.deps.length && diff.props.length) {
      tabs.forEach(x => x.classList.toggle("on", x.dataset.tab === "props"));
      currentTab = "props"; renderList();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-vi-viewer]").forEach(initViewer);
    document.querySelectorAll("[data-vi-diff]").forEach(initDiff);
  });
})();
