/* viCheck page behavior: path slots, native pickers, drag & drop, Explorer, SVG saving */
(function () {
  "use strict";
  const T = window.T || ((s, kw) => { let r = s; if (kw) for (const k in kw) r = r.split("{" + k + "}").join(kw[k]); return r; });
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const inWebview = () => !!(window.pywebview && window.pywebview.api && window.pywebview.api.pick);

  async function pick(kind, initial) {
    if (inWebview()) {
      try { return await window.pywebview.api.pick(kind, initial || ""); } catch (e) { /* fall through */ }
    }
    const r = await fetch("/api/pick?" + new URLSearchParams({ kind, initial: initial || "" }));
    return (await r.json()).path || "";
  }

  function toast(html, ms) {
    let t = document.querySelector(".toast");
    if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
    t.innerHTML = html;
    t.classList.add("on");
    clearTimeout(t._h);
    t._h = setTimeout(() => t.classList.remove("on"), ms || 6000);
    return t;
  }
  window.viCheckToast = toast;

  async function reveal(path) {
    const r = await fetch("/api/reveal", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
    if (!r.ok) toast(esc(T("⚠ Could not open:")) + " " + esc(path));
  }

  document.addEventListener("click", ev => {
    const rv = ev.target.closest("[data-reveal]");
    if (rv) { ev.preventDefault(); reveal(rv.dataset.reveal); return; }
    const of = ev.target.closest("[data-open-file]");
    if (of) {
      ev.preventDefault();
      fetch("/api/open-file", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: of.dataset.openFile }) })
        .then(r => { if (!r.ok) toast(esc(T("⚠ Could not open:")) + " " + esc(of.dataset.openFile)); });
      return;
    }
    const ob = ev.target.closest("[data-open-browser]");
    if (ob) {
      ev.preventDefault();
      fetch("/api/open-browser", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: location.pathname + location.search }) });
    }
  });

  // ------------------------------------------------ home page: two slots
  function initHome(form) {
    const inputs = { a: form.querySelector("[data-path=a]"), b: form.querySelector("[data-path=b]") };
    const slots = { a: form.querySelector("[data-slot=a]"), b: form.querySelector("[data-slot=b]") };
    const hint = document.getElementById("go-hint");
    const info = { a: null, b: null };
    let lastTarget = "a";
    const ICON_DIR = '<svg class="ficon big" viewBox="0 0 16 16"><path fill="#7a9cc6" d="M1.5 3.5A1.5 1.5 0 0 1 3 2h3.2l1.5 1.6H13A1.5 1.5 0 0 1 14.5 5v7.5A1.5 1.5 0 0 1 13 14H3a1.5 1.5 0 0 1-1.5-1.5z"/></svg>';
    const ICON_VI = slots.a.querySelector("[data-icon]").innerHTML;

    async function check(side) {
      const v = inputs[side].value.trim();
      const slot = slots[side];
      const kindEl = slot.querySelector("[data-kind]"), hintEl = slot.querySelector("[data-hint]"), iconEl = slot.querySelector("[data-icon]");
      slot.classList.remove("ok", "bad");
      if (!v) { info[side] = null; kindEl.textContent = ""; hintEl.textContent = T("Drop a VI or a folder here"); iconEl.innerHTML = ICON_VI; update(); return; }
      try {
        const j = await (await fetch("/api/kind?" + new URLSearchParams({ path: v }))).json();
        if (inputs[side].value.trim() !== v) return;
        info[side] = j;
        if (!j.kind) { slot.classList.add("bad"); kindEl.textContent = T("not found"); hintEl.textContent = T("This path does not exist"); }
        else if (j.kind === "folder") { slot.classList.add("ok"); kindEl.textContent = T("folder"); iconEl.innerHTML = ICON_DIR; hintEl.innerHTML = T("{vis} VI/control in {files} files", { vis: `<b>${j.vis}</b>`, files: `<b>${j.files}</b>` }); }
        else { slot.classList.add("ok"); kindEl.textContent = j.is_vi ? "VI" : T("file"); iconEl.innerHTML = ICON_VI; hintEl.innerHTML = `${esc(j.path.split(/[\\/]/).pop())} · ${j.size}`; }
      } catch (e) { info[side] = null; }
      update();
    }
    function update() {
      const a = info.a, b = info.b;
      let msg = "";
      if (a && b && a.kind && b.kind && a.kind !== b.kind) msg = T("⚠ A and B must both be files or both be folders.");
      else if (a && b && a.kind === "folder" && b.kind === "folder") msg = T("Folder comparison: every file is matched by its path.");
      else if (a && b && a.kind === "file" && b.kind === "file") msg = T("Block diagram diff of the two VIs.");
      hint.textContent = msg;
    }
    let tmr = {};
    for (const side of ["a", "b"]) {
      inputs[side].addEventListener("input", () => { clearTimeout(tmr[side]); tmr[side] = setTimeout(() => check(side), 250); });
      inputs[side].addEventListener("focus", () => lastTarget = side);
      check(side);
      const drop = slots[side];
      drop.addEventListener("dragenter", e => { e.preventDefault(); lastTarget = side; drop.classList.add("over"); });
      drop.addEventListener("dragover", e => { e.preventDefault(); lastTarget = side; drop.classList.add("over"); });
      drop.addEventListener("dragleave", e => { if (!drop.contains(e.relatedTarget)) drop.classList.remove("over"); });
      drop.addEventListener("drop", e => {
        e.preventDefault(); drop.classList.remove("over"); lastTarget = side;
        // In the desktop window the full path arrives through window.viCheckDropped.
        if (!inWebview()) {
          const txt = e.dataTransfer.getData("text/plain");
          if (txt && /^([a-zA-Z]:\\|\\\\|\/)/.test(txt.trim())) { inputs[side].value = txt.trim(); check(side); }
          else toast(T("Drag & drop of files works in the viCheck window. In a browser, use <b>Choose VI…</b> / <b>Choose folder…</b> or paste the path."));
        }
      });
    }
    // the page-wide drop (outside a slot) fills the slot that was entered last
    document.addEventListener("dragover", e => e.preventDefault());
    document.addEventListener("drop", e => e.preventDefault());
    window.viCheckDropped = paths => {
      if (!paths || !paths.length) return;
      if (paths.length >= 2) { inputs.a.value = paths[0]; inputs.b.value = paths[1]; check("a"); check("b"); return; }
      inputs[lastTarget].value = paths[0];
      check(lastTarget);
      if (lastTarget === "a" && !inputs.b.value) lastTarget = "b";
    };
    form.querySelectorAll("[data-pick]").forEach(btn => btn.addEventListener("click", async () => {
      const side = btn.dataset.for;
      const other = inputs[side === "a" ? "b" : "a"].value.trim();
      const p = await pick(btn.dataset.pick, inputs[side].value.trim() || other);
      if (p) { inputs[side].value = p; check(side); }
    }));
    form.querySelectorAll("[data-clear]").forEach(btn => btn.addEventListener("click", () => { inputs[btn.dataset.clear].value = ""; check(btn.dataset.clear); }));
    document.getElementById("swap").addEventListener("click", () => {
      [inputs.a.value, inputs.b.value] = [inputs.b.value, inputs.a.value];
      check("a"); check("b");
    });
    form.addEventListener("submit", ev => {
      if (!inputs.a.value.trim() || !inputs.b.value.trim()) { ev.preventDefault(); toast(esc(T("Choose both A and B."))); return; }
      const btn = document.getElementById("go");
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> ' + esc(T("Comparing…"));
      setTimeout(() => { btn.disabled = false; btn.textContent = T("Compare"); }, 15000);
    });
  }

  // ------------------------------------------------ diff page: save the current view as one SVG
  const SVG_STYLE = `.dg text{font-family:"Segoe UI",Arial,sans-serif;fill:#1c2128}.dg .dim{opacity:.28}.dg .hl-ring{fill:none}`;
  function paneSvg(sel) {
    const svg = document.querySelector(sel + " svg.dg");
    const pane = document.querySelector(sel);
    if (!svg || !pane || pane.classList.contains("hidden")) return null;
    const r = svg.getBoundingClientRect();
    const c = svg.cloneNode(true);
    c.querySelectorAll(".flash").forEach(e => e.classList.remove("flash"));
    return { node: c, w: Math.round(r.width), h: Math.round(r.height) };
  }
  async function saveView() {
    const root = document.querySelector("[data-vi-diff]");
    const sides = [["A", ".pane.old", root.dataset.oldLabel, "#cf222e"], ["B", ".pane.new", root.dataset.newLabel, "#1a7f37"]]
      .map(([t, sel, label, col]) => ({ t, label, col, p: paneSvg(sel) })).filter(s => s.p);
    if (!sides.length) return;
    const HEAD = 30, GAP = 12;
    const W = sides.reduce((a, s) => a + s.p.w, 0) + GAP * (sides.length - 1);
    const H = Math.max(...sides.map(s => s.p.h)) + HEAD;
    let x = 0, inner = "";
    for (const s of sides) {
      const n = s.p.node;
      n.removeAttribute("style");
      n.setAttribute("x", x); n.setAttribute("y", HEAD); n.setAttribute("width", s.p.w); n.setAttribute("height", s.p.h);
      n.setAttribute("class", "dg");
      inner += `<rect x="${x}" y="${HEAD}" width="${s.p.w}" height="${s.p.h}" fill="#ffffff" stroke="#d0d7de"/>`;
      inner += `<text x="${x + 6}" y="20" font-family="Segoe UI,Arial,sans-serif" font-size="13"><tspan font-weight="700" fill="${s.col}">${s.t}</tspan><tspan fill="#1c2128"> ${esc(s.label || "")}</tspan></text>`;
      inner += new XMLSerializer().serializeToString(n);
      x += s.p.w + GAP;
    }
    const out = `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><style>${SVG_STYLE}</style><rect width="100%" height="100%" fill="#ffffff"/>${inner}</svg>`;
    const r = await fetch("/api/save-svg", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: root.dataset.fname, svg: out }) });
    const j = await r.json();
    if (j.path) toast(`${esc(T("✓ Saved"))} <span class="mono">${esc(j.path)}</span><br><a href="#" data-reveal="${esc(j.path)}">${esc(T("Show in folder"))}</a> · <a href="${esc(j.url)}" target="_blank">${esc(T("Open"))}</a>`, 12000);
    else toast("⚠ " + esc(j.error || T("Could not save")));
  }

  // ------------------------------------------------ first-start help (also opened with the ? button)
  function initWelcome() {
    const dlg = document.getElementById("welcome");
    if (!dlg || typeof dlg.showModal !== "function") return;
    dlg.addEventListener("close", () => {
      if (dlg.dataset.autoOpen === "1") {
        dlg.dataset.autoOpen = "0";
        fetch("/api/welcome-seen", { method: "POST" });
      }
    });
    dlg.addEventListener("click", e => {
      if (e.target === dlg) { dlg.close(); return; }   // click on the backdrop
      const a = e.target.closest("a[href]");
      if (a && !a.hasAttribute("lang") && dlg.dataset.autoOpen === "1") {   // a link (not the language switch): seen
        dlg.dataset.autoOpen = "0";
        navigator.sendBeacon ? navigator.sendBeacon("/api/welcome-seen") : fetch("/api/welcome-seen", { method: "POST", keepalive: true });
      }
    });
    document.querySelectorAll("[data-help]").forEach(b => b.addEventListener("click", () => dlg.showModal()));
    if (dlg.dataset.autoOpen === "1") dlg.showModal();
  }

  document.addEventListener("DOMContentLoaded", () => {
    initWelcome();
    const f = document.getElementById("cmp-form");
    if (f) initHome(f);
    const tg = document.querySelector("[data-head-toggle]");
    if (tg) {
      const side = tg.closest(".vd-side");
      let closed = false;
      try { closed = localStorage.getItem("vicheck.headClosed") === "1"; } catch (e) { /* no storage */ }
      side.classList.toggle("head-closed", closed);
      tg.addEventListener("click", () => {
        closed = !side.classList.toggle("head-closed") ? false : true;
        try { localStorage.setItem("vicheck.headClosed", closed ? "1" : "0"); } catch (e) { /* no storage */ }
      });
    }
    const sv = document.querySelector("[data-svg-copy]");
    if (sv) sv.addEventListener("click", saveView);
  });
})();
