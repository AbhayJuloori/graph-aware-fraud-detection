/* Fraud Signal Lab — project site. Data: data/summary.json (written by `fraud-lab report`). */
(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const palette = () => ({
    ink: css("--ink"), ink2: css("--ink-2"), ink3: css("--ink-3"), line: css("--line"),
    surface: css("--surface"), surface2: css("--surface-2"), bg: css("--bg"),
    blue: css("--blue"), orange: css("--orange"), aqua: css("--aqua"), good: css("--good"), bad: css("--bad"),
  });
  let C = palette();
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
  };
  const pct = (v, d = 1) => (v * 100).toFixed(d) + "%";
  const smartPct = (v) => (v === 0 ? "0%" : v > 0.99 && v < 1 ? pct(v, 2) : v >= 0.1 ? pct(v, 0) : v >= 0.01 ? pct(v, 1) : pct(v, 2));
  const int = (v) => Math.round(v).toLocaleString("en-US");
  const money = (v) => "$" + (v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : v >= 1e3 ? (v / 1e3).toFixed(1) + "k" : Math.round(v));
  const signed = (v, d = 4) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(d);
  const logit = (p) => { const q = Math.min(1 - 1e-7, Math.max(1e-7, p)); return Math.log(q / (1 - q)); };

  /* ---------------- Theme & audience ---------------- */
  const rerenders = [];
  const savedTheme = store.get("theme");
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;
  $("#theme").addEventListener("click", () => {
    // Dark is the default look; light is an opt-in "paper" theme.
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    store.set("theme", next);
    C = palette();
    rerenders.forEach((fn) => fn());
  });

  const setAudience = (aud) => {
    document.body.dataset.audience = aud;
    $$("[data-audience]", $(".nav")).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.audience === aud)));
    store.set("audience", aud);
  };
  $$(".nav [data-audience]").forEach((b) => b.addEventListener("click", () => setAudience(b.dataset.audience)));
  const params = new URLSearchParams(location.search);
  setAudience(params.get("view") === "tech" ? "tech" : store.get("audience") || "plain");

  /* ---------------- Scroll chrome ---------------- */
  const nav = $("#nav");
  const progress = $("#progress");
  const sections = $$("main section[id]");
  const links = $$(".nav-links a");
  const onScroll = () => {
    const y = window.scrollY;
    nav.classList.toggle("scrolled", y > 8);
    const h = document.documentElement.scrollHeight - innerHeight;
    progress.style.width = (h > 0 ? (y / h) * 100 : 0) + "%";
    let current = "";
    sections.forEach((s) => { if (s.offsetTop - 120 <= y) current = s.id; });
    links.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === "#" + current));
  };
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------------- Reveal + count-up ---------------- */
  const onVisible = (el, fn, threshold = 0.25) => {
    if (reduceMotion || !("IntersectionObserver" in window)) { fn(); return; }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) { fn(); io.disconnect(); } });
    }, { threshold });
    io.observe(el);
  };
  $$(".reveal").forEach((el) => onVisible(el, () => el.classList.add("in"), 0.12));

  const countUp = (el) => {
    const target = parseFloat(el.dataset.count);
    const decimals = parseInt(el.dataset.decimals || "0", 10);
    const suffix = el.dataset.suffix || "";
    const fmt = (v) => v.toFixed(decimals) + suffix;
    if (reduceMotion) { el.textContent = fmt(target); return; }
    const t0 = performance.now();
    const dur = 1400;
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur);
      el.textContent = fmt(target * (1 - Math.pow(1 - k, 3)));
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  $$("[data-count]").forEach((el) => onVisible(el, () => countUp(el), 0.5));

  /* ---------------- Tooltip ---------------- */
  const tip = $("#tip");
  const showTip = (event, html) => {
    tip.innerHTML = html;
    tip.style.opacity = 1;
    const pad = 14;
    const r = tip.getBoundingClientRect();
    let x = event.clientX + pad;
    let y = event.clientY + pad;
    if (x + r.width > innerWidth - 8) x = event.clientX - r.width - pad;
    if (y + r.height > innerHeight - 8) y = event.clientY - r.height - pad;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
  };
  const hideTip = () => { tip.style.opacity = 0; };
  const row = (k, v) => `<div class="row"><span>${k}</span><span>${v}</span></div>`;

  /* =========================================================
     HERO: streaming transfer network (illustrative)
     One-time senders appear, send, and fade; a pool of receivers persists.
     ========================================================= */
  function heroNet() {
    const canvas = $("#net");
    const ctx = canvas.getContext("2d");
    const H = 80;
    let W = 160, scale = 1, receivers = [];
    const rng = (() => { let s = 11; return () => ((s = (s * 16807) % 2147483647) / 2147483647); })();
    const place = () => {
      const wide = W > 130;
      const cx = wide ? W * 0.76 : W * 0.5, cy = wide ? 38 : 26, spread = wide ? 0.95 : 0.7;
      receivers = Array.from({ length: wide ? 22 : 14 }, (_, i) => {
        const a = (i / (wide ? 22 : 14)) * Math.PI * 2 + rng() * 0.35;
        const r = (10 + rng() * 20) * spread;
        return { x: cx + Math.cos(a) * r * 1.25, y: cy + Math.sin(a) * r * 0.85, hits: 1 + Math.floor(rng() * 3), pulse: 0 };
      });
    };
    const resize = () => {
      const dpr = Math.min(2, devicePixelRatio || 1);
      const r = canvas.getBoundingClientRect();
      canvas.width = r.width * dpr;
      canvas.height = r.height * dpr;
      scale = canvas.height / H;
      W = canvas.width / scale;
      place();
      transfers = [];
    };
    let transfers = [], step = 1, stepT = 0, scored = 0, flagged = 0, spawn = 0, last = performance.now(), running = true;
    resize();
    addEventListener("resize", resize);

    const tick = (dt) => {
      stepT += dt;
      if (stepT > 0.9) { stepT = 0; step = step >= 743 ? 1 : step + 1; }
      spawn += dt * (W > 130 ? 10 : 6);
      while (spawn >= 1) {
        spawn -= 1;
        const target = receivers[Math.floor(rng() * receivers.length)];
        const a = rng() * Math.PI * 2, d = 14 + rng() * 22;
        const sx = Math.max(2, Math.min(W - 2, target.x + Math.cos(a) * d * 1.3));
        const sy = Math.max(4, Math.min(H - 4, target.y + Math.sin(a) * d * 0.8));
        transfers.push({ sx, sy, t: target, k: 0, life: 1, fraud: rng() < 0.06 });
      }
      for (const tr of transfers) {
        if (tr.k < 1) {
          tr.k = Math.min(1, tr.k + dt * 1.5);
          if (tr.k === 1) { scored += 1; tr.t.hits += 1; tr.t.pulse = 1; if (tr.fraud) flagged += 1; }
        } else tr.life -= dt * (tr.fraud ? 0.4 : 0.85);
      }
      transfers = transfers.filter((tr) => tr.life > 0);
      receivers.forEach((r) => { r.pulse = Math.max(0, r.pulse - dt * 2); });
    };

    const draw = () => {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      for (const tr of transfers) {
        const ex = tr.sx + (tr.t.x - tr.sx) * tr.k, ey = tr.sy + (tr.t.y - tr.sy) * tr.k;
        const alpha = Math.max(0, Math.min(1, tr.life));
        ctx.globalAlpha = alpha * (tr.fraud ? 0.95 : 0.4);
        ctx.strokeStyle = tr.fraud ? C.orange : C.ink3;
        ctx.lineWidth = tr.fraud ? 0.35 : 0.18;
        ctx.beginPath(); ctx.moveTo(tr.sx, tr.sy); ctx.lineTo(ex, ey); ctx.stroke();
        ctx.fillStyle = tr.fraud ? C.orange : C.ink3;
        ctx.fillRect(tr.sx - 0.35, tr.sy - 0.35, 0.7, 0.7);
        if (tr.k < 1) { ctx.globalAlpha = alpha; ctx.fillStyle = tr.fraud ? C.orange : C.ink2; ctx.beginPath(); ctx.arc(ex, ey, 0.4, 0, Math.PI * 2); ctx.fill(); }
        if (tr.fraud && tr.k === 1) {
          ctx.globalAlpha = alpha * 0.5;
          ctx.strokeStyle = C.orange; ctx.lineWidth = 0.15;
          const s = 1.6 + (1 - tr.life) * 2.4;
          ctx.strokeRect(tr.sx - s, tr.sy - s, s * 2, s * 2);
        }
      }
      ctx.globalAlpha = 1;
      for (const r of receivers) {
        const rad = 0.42 + Math.min(0.7, Math.sqrt(r.hits) * 0.08) + r.pulse * 0.35;
        ctx.shadowColor = C.blue; ctx.shadowBlur = 8 * r.pulse;
        ctx.fillStyle = C.blue;
        ctx.beginPath(); ctx.arc(r.x, r.y, rad, 0, Math.PI * 2); ctx.fill();
      }
      ctx.shadowBlur = 0;
      $("#hudStep").textContent = step;
      $("#hudScored").textContent = scored.toLocaleString("en-US");
      $("#hudFlagged").textContent = flagged.toLocaleString("en-US");
    };

    const loop = (t) => {
      const dt = Math.min(0.05, (t - last) / 1000);
      last = t;
      if (running) { tick(dt); draw(); }
      requestAnimationFrame(loop);
    };
    if (reduceMotion) {
      for (let i = 0; i < 240; i++) tick(1 / 60);
      draw();
      rerenders.push(draw);
      return;
    }
    if ("IntersectionObserver" in window) {
      new IntersectionObserver((e) => { running = e[0].isIntersecting; last = performance.now(); }).observe(canvas);
    }
    requestAnimationFrame(loop);
  }
  heroNet();

  /* Ticker: an illustrative replay of scored transfers (synthetic IDs, not PaySim rows). */
  (function ticker() {
    const rng = (() => { let s = 97; return () => ((s = (s * 16807) % 2147483647) / 2147483647); })();
    const id = (p) => p + String(Math.floor(rng() * 9e8 + 1e8));
    const rows = Array.from({ length: 36 }, () => {
      const flag = rng() < 0.14;
      const type = flag ? (rng() < 0.5 ? "TRANSFER" : "CASH_OUT") : ["PAYMENT", "CASH_IN", "CASH_OUT", "TRANSFER", "PAYMENT"][Math.floor(rng() * 5)];
      const amount = Math.round(Math.pow(10, 2 + rng() * (flag ? 4.2 : 3.4)));
      const score = flag ? 0.9 + rng() * 0.0999 : rng() * 0.004;
      return `<span class="${flag ? "flag" : ""}"><b>${type}</b> ${id("C")} → ${id(type === "PAYMENT" ? "M" : "C")} · $${amount.toLocaleString("en-US")} · <span class="sc">p=${score.toFixed(4)}</span>${flag ? " · <b>REVIEW</b>" : ""}</span>`;
    }).join("");
    $("#ticker").innerHTML = rows + rows;
  })();

  /* =========================================================
     GRAPH EXPLAINER — same rules as TemporalGraph.row_features
     ========================================================= */
  function graphExplainer() {
    const svg = d3.select("#graphSvg");
    const NODES = {
      A: { x: 120, y: 70 }, B: { x: 320, y: 150 }, C: { x: 120, y: 230 },
      D: { x: 520, y: 70 }, G: { x: 440, y: 245 }, H: { x: 580, y: 245 },
    };
    // Training window: labels are learned after each step.
    const TX = [
      { step: 1, s: "A", r: "B", fraud: 1 }, { step: 1, s: "C", r: "B", fraud: 0 },
      { step: 2, s: "D", r: "B", fraud: 0 },
      { step: 3, s: "A", r: "D", fraud: 1 },
      { step: 4, s: "G", r: "H", fraud: 0 },
    ];
    const NOTES = {
      1: "Both step 1 transfers are scored against an empty network. C→B cannot see A→B, even though it happened in the same hour.",
      2: "D→B is scored after step 1 was added and labeled: B has 2 earlier links, and 1 of its 2 past transfers was fraud.",
      3: "A sends again. A and D share a counterparty (B), which closes a possible triangle: the ring flag fires.",
      4: "Two brand new accounts. Every network feature is zero. In PaySim, this is what nearly every transfer looks like.",
    };
    let current = 1;

    const featuresAt = (step) => {
      const prior = TX.filter((t) => t.step < step);
      const edges = new Set(prior.map((t) => t.s + ">" + t.r));
      const nbrs = (n) => {
        const out = new Set();
        edges.forEach((e) => { const [a, b] = e.split(">"); if (a === n) out.add(b); if (b === n) out.add(a); });
        return out;
      };
      const degree = (n) => [...edges].filter((e) => e.split(">").includes(n)).length;
      const rate = (n) => {
        const rows = prior.filter((t) => t.s === n || t.r === n);
        return rows.length ? rows.filter((t) => t.fraud).length / rows.length : 0;
      };
      return TX.filter((t) => t.step === step).map((t) => {
        const shared = [...nbrs(t.s)].filter((x) => nbrs(t.r).has(x)).length;
        return { ...t, feats: [
          ["sender_degree", degree(t.s)], ["receiver_degree", degree(t.r)],
          ["shared_counterparties", shared], ["ring_flag", shared > 0 ? 1 : 0],
          ["sender_fraud_rate", rate(t.s)], ["receiver_fraud_rate", rate(t.r)],
        ] };
      });
    };

    const render = (animate) => {
      svg.selectAll("*").remove();
      svg.append("defs").html(`<marker id="ga" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="${C.ink2}"/></marker><marker id="gaO" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="${C.orange}"/></marker><marker id="gaB" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="${C.blue}"/></marker>`);
      const edgePath = (t, bend) => {
        const a = NODES[t.s], b = NODES[t.r];
        const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy);
        const ux = dx / len, uy = dy / len, R = 22;
        const x1 = a.x + ux * R, y1 = a.y + uy * R, x2 = b.x - ux * (R + 3), y2 = b.y - uy * (R + 3);
        const mx = (x1 + x2) / 2 - uy * bend, my = (y1 + y2) / 2 + ux * bend;
        return `M${x1},${y1} Q${mx},${my} ${x2},${y2}`;
      };
      const visible = TX.filter((t) => t.step < current);
      const scoring = TX.filter((t) => t.step === current);
      visible.forEach((t) => {
        svg.append("path").attr("d", edgePath(t, 0)).attr("fill", "none")
          .attr("stroke", t.fraud ? C.orange : C.ink2).attr("stroke-width", 2).attr("marker-end", t.fraud ? "url(#gaO)" : "url(#ga)");
        const a = NODES[t.s], b = NODES[t.r];
        svg.append("text").attr("x", (a.x + b.x) / 2).attr("y", (a.y + b.y) / 2 - 8).attr("text-anchor", "middle")
          .attr("fill", t.fraud ? C.orange : C.ink3).attr("font-size", 10.5).attr("font-family", "IBM Plex Mono")
          .text(`step ${t.step}${t.fraud ? " · fraud" : ""}`);
      });
      scoring.forEach((t, i) => {
        const p = svg.append("path").attr("d", edgePath(t, scoring.length > 1 ? (i ? -18 : 18) : 0)).attr("fill", "none")
          .attr("stroke", C.blue).attr("stroke-width", 2.4).attr("stroke-dasharray", "6 5").attr("marker-end", "url(#gaB)");
        if (animate && !reduceMotion) {
          p.attr("opacity", 0).transition().duration(500).attr("opacity", 1);
        }
      });
      const used = new Set([...visible, ...scoring].flatMap((t) => [t.s, t.r]));
      Object.entries(NODES).forEach(([id, n]) => {
        const on = used.has(id);
        const g = svg.append("g").attr("transform", `translate(${n.x},${n.y})`).attr("opacity", on ? 1 : 0.25);
        g.append("circle").attr("r", 20).attr("fill", on ? C.bg : "none").attr("stroke", scoring.some((t) => t.s === id || t.r === id) ? C.blue : C.line).attr("stroke-width", 2);
        g.append("text").attr("y", 5).attr("text-anchor", "middle").attr("fill", C.ink).attr("font-size", 14).attr("font-weight", 700).text(id);
      });
      svg.append("text").attr("x", 14).attr("y", 22).attr("fill", C.ink3).attr("font-size", 10.5).attr("font-family", "IBM Plex Mono").text("SOLID = KNOWN BEFORE THIS STEP · DASHED = BEING SCORED");

      const rows = featuresAt(current);
      $("#stepCaption").textContent = `scoring step ${current}`;
      $("#stepNote").textContent = NOTES[current];
      $("#featRows").innerHTML = `<tr><td><b style="color:var(--ink)">Feature</b></td>${rows.map((r) => `<td><b>${r.s}→${r.r}</b></td>`).join("")}</tr>` +
        rows[0].feats.map(([name], j) => {
          const vals = rows.map((r) => r.feats[j][1]);
          const hot = vals.some((v) => v > 0);
          return `<tr class="${hot ? "hot" : ""}"><td><code>${name}</code></td>${vals.map((v) => `<td>${Number.isInteger(v) ? v : v.toFixed(2)}</td>`).join("")}</tr>`;
        }).join("");
    };

    $$("#stepSeg button").forEach((b) => b.addEventListener("click", () => {
      current = +b.dataset.step;
      $$("#stepSeg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      render(true);
    }));
    render(false);
    rerenders.push(() => render(false));
  }
  graphExplainer();

  /* =========================================================
     DATA-DRIVEN CHARTS
     ========================================================= */
  const chartSize = (el, ratio) => {
    const w = Math.max(280, el.clientWidth);
    return { w, h: Math.round(w * ratio) };
  };
  const drawAxes = (g, x, y, w, h, opts = {}) => {
    g.append("g").attr("class", "grid").call(d3.axisLeft(y).ticks(opts.yTicks || 5).tickSize(-w).tickFormat(""));
    g.append("g").attr("class", "axis").attr("transform", `translate(0,${h})`).call(d3.axisBottom(x).ticks(opts.xTicks || 6).tickFormat(opts.xFmt || null).tickSizeOuter(0));
    g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(opts.yTicks || 5).tickFormat(opts.yFmt || null).tickSize(0).tickPadding(8)).select(".domain").remove();
    if (opts.xLabel) g.append("text").attr("x", w).attr("y", h + 34).attr("text-anchor", "end").attr("fill", C.ink2).attr("font-size", 11.5).text(opts.xLabel);
    if (opts.yLabel) g.append("text").attr("x", -2).attr("y", -10).attr("fill", C.ink2).attr("font-size", 11.5).text(opts.yLabel);
  };
  const drawLine = (path, animate) => {
    if (!animate || reduceMotion) return;
    const len = path.node().getTotalLength();
    path.attr("stroke-dasharray", `${len} ${len}`).attr("stroke-dashoffset", len)
      .transition().duration(1400).ease(d3.easeCubicInOut).attr("stroke-dashoffset", 0)
      .on("end", () => path.attr("stroke-dasharray", null));
  };
  const MODEL_COLORS = () => ({ logistic_baseline: C.ink3, xgboost_baseline: C.blue, xgboost_graph: C.orange });
  const MODEL_LABELS = { logistic_baseline: "Logistic regression", xgboost_baseline: "XGBoost, transaction only", xgboost_graph: "XGBoost + graph" };

  function prChart(D, animate) {
    const el = $("#chartPR");
    el.innerHTML = "";
    const { w: W, h: H } = chartSize(el, 0.66);
    const m = { t: 24, r: 18, b: 44, l: 44 }, w = W - m.l - m.r, h = H - m.t - m.b;
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
    const x = d3.scaleLinear().domain([0, 1]).range([0, w]);
    const y = d3.scaleLinear().domain([0, 1.02]).range([h, 0]);
    drawAxes(g, x, y, w, h, { xFmt: d3.format(".0%"), yFmt: d3.format(".0%"), xLabel: "Recall (fraud caught)", yLabel: "Precision (alerts that are fraud)" });
    const colors = MODEL_COLORS();
    const order = ["logistic_baseline", "xgboost_graph", "xgboost_baseline"];
    order.forEach((name) => {
      const curve = D.models[name].pr_curve;
      const p = g.append("path").datum(curve).attr("fill", "none").attr("stroke", colors[name])
        .attr("stroke-width", name === "xgboost_graph" ? 2 : 2.4).attr("stroke-dasharray", name === "xgboost_graph" ? "6 4" : null)
        .attr("d", d3.line().curve(d3.curveStepAfter).x((d) => x(d.recall)).y((d) => y(d.precision)));
      if (name !== "xgboost_graph") drawLine(p, animate);
    });
    const cross = g.append("line").attr("y1", 0).attr("y2", h).attr("stroke", C.ink3).attr("opacity", 0);
    const dots = order.map((name) => g.append("circle").attr("r", 4).attr("fill", colors[name]).attr("stroke", C.surface).attr("stroke-width", 1.5).attr("opacity", 0));
    const at = (curve, r) => { let best = curve[0]; for (const p of curve) { if (p.recall <= r + 1e-9) best = p; else break; } return best; };
    g.append("rect").attr("width", w).attr("height", h).attr("fill", "transparent")
      .on("mousemove", (ev) => {
        const r = Math.max(0, Math.min(1, x.invert(d3.pointer(ev)[0])));
        cross.attr("x1", x(r)).attr("x2", x(r)).attr("opacity", 1);
        const pts = order.map((name) => at(D.models[name].pr_curve, r));
        dots.forEach((d, i) => d.attr("cx", x(r)).attr("cy", y(pts[i].precision)).attr("opacity", 1));
        showTip(ev, `<b>At ${pct(r, 0)} recall</b>` + order.slice().reverse().map((name, i) => row(MODEL_LABELS[name], pct(pts[order.length - 1 - i].precision, 1) + " precision")).join("") +
          row("Test PR-AUC (txn / graph)", D.models.xgboost_baseline.test.pr_auc.toFixed(4) + " / " + D.models.xgboost_graph.test.pr_auc.toFixed(4)));
      })
      .on("mouseleave", () => { cross.attr("opacity", 0); dots.forEach((d) => d.attr("opacity", 0)); hideTip(); });
  }

  let opIndex = null;
  function operatingPanel(D, animate) {
    const curve = D.models[D.champion].operating_curve;
    const slider = $("#fprSlider");
    slider.max = curve.length - 1;
    if (opIndex === null) {
      opIndex = curve.reduce((best, p, i) => (Math.abs(Math.log(p.target_fpr / 0.01)) < Math.abs(Math.log(curve[best].target_fpr / 0.01)) ? i : best), 0);
      slider.value = opIndex;
    }
    const chosenIdx = curve.reduce((best, p, i) => (Math.abs(Math.log(p.target_fpr / 0.01)) < Math.abs(Math.log(curve[best].target_fpr / 0.01)) ? i : best), 0);
    const el = $("#chartOp");
    el.innerHTML = "";
    const { w: W } = chartSize(el, 0.4);
    const H = Math.round(Math.max(170, W * 0.38));
    const m = { t: 14, r: 14, b: 40, l: 44 }, w = W - m.l - m.r, h = H - m.t - m.b;
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
    const x = d3.scaleLog().domain([curve[0].target_fpr, curve[curve.length - 1].target_fpr]).range([0, w]);
    const y = d3.scaleLinear().domain([0, 1]).range([h, 0]);
    g.append("g").attr("class", "grid").call(d3.axisLeft(y).ticks(4).tickSize(-w).tickFormat(""));
    g.append("g").attr("class", "axis").attr("transform", `translate(0,${h})`).call(d3.axisBottom(x).tickValues([1e-4, 1e-3, 1e-2, 0.1]).tickFormat((v) => pct(v, v < 0.001 ? 2 : v < 0.01 ? 1 : 0)).tickSizeOuter(0));
    g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(4).tickFormat(d3.format(".0%")).tickSize(0).tickPadding(8)).select(".domain").remove();
    g.append("text").attr("x", w).attr("y", h + 32).attr("text-anchor", "end").attr("fill", C.ink2).attr("font-size", 11.5).text("False alarm budget (log scale)");
    [["recall", C.good], ["precision", C.orange]].forEach(([k, color]) => {
      const p = g.append("path").datum(curve).attr("fill", "none").attr("stroke", color).attr("stroke-width", 2.2)
        .attr("d", d3.line().x((d) => x(d.target_fpr)).y((d) => y(d[k])));
      drawLine(p, animate);
      const lastPt = k === "recall" ? curve[Math.floor(curve.length * 0.15)] : curve[Math.floor(curve.length * 0.75)];
      g.append("text").attr("x", x(lastPt.target_fpr) + 6).attr("y", y(lastPt[k]) + (k === "recall" ? 16 : -8)).attr("fill", color).attr("font-size", 11.5).attr("font-weight", 600).text(k === "recall" ? "fraud caught" : "alerts that are fraud");
    });
    const cp = curve[chosenIdx];
    g.append("line").attr("x1", x(cp.target_fpr)).attr("x2", x(cp.target_fpr)).attr("y1", 0).attr("y2", h).attr("stroke", C.ink2).attr("stroke-dasharray", "4 4");
    g.append("text").attr("x", x(cp.target_fpr) + 4).attr("y", 10).attr("fill", C.ink2).attr("font-size", 10.5).text("validation pick");
    const marker = g.append("line").attr("y1", 0).attr("y2", h).attr("stroke", C.ink).attr("stroke-width", 1.6);
    const lo = Math.log(curve[0].target_fpr), hi = Math.log(curve[curve.length - 1].target_fpr);
    $("#fprTicks").innerHTML = [1e-4, 1e-3, 1e-2, 0.2].map((v) => `<span style="left:${((Math.log(v) - lo) / (hi - lo)) * 100}%">${pct(v, v < 0.001 ? 2 : v < 0.01 ? 1 : 0)}</span>`).join("");
    const update = () => {
      const p = curve[+slider.value];
      marker.attr("x1", x(p.target_fpr)).attr("x2", x(p.target_fpr));
      $("#fprVal").textContent = pct(p.target_fpr, p.target_fpr < 0.001 ? 3 : p.target_fpr < 0.01 ? 2 : 1);
      const chip = $("#fprChip");
      const isChosen = +slider.value === chosenIdx;
      chip.textContent = isChosen ? "chosen on validation" : p.recall >= 0.999 ? "still catches ≈ all fraud" : `misses ${pct(1 - p.recall, 1)} of fraud`;
      chip.className = "chip " + (isChosen ? "neutral" : p.recall >= 0.99 ? "good" : "warn");
      $("#kRecall").textContent = pct(p.recall, p.recall > 0.999 ? 0 : 1);
      $("#kPrec").textContent = pct(p.precision, 0);
      $("#kAlerts").textContent = int(p.alerts_per_100k);
      const fraudPer100k = curve[curve.length - 1].caught_per_100k;
      $("#kMissed").textContent = (fraudPer100k - p.caught_per_100k).toFixed(1);
    };
    slider.oninput = () => { opIndex = +slider.value; update(); };
    update();
  }

  function liftChart(D, animate) {
    const el = $("#chartLift");
    el.innerHTML = "";
    const { w: W, h: H } = chartSize(el, 0.58);
    const m = { t: 20, r: 12, b: 54, l: 52 }, w = W - m.l - m.r, h = H - m.t - m.b;
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
    const rows = D.cohorts;
    const x = d3.scaleBand().domain(rows.map((d) => d.id)).range([0, w]).padding(0.3);
    const xi = d3.scaleBand().domain(["validation_lift", "test_lift"]).range([0, x.bandwidth()]).padding(0.08);
    const y = d3.scaleLinear().domain([-0.008, 0.013]).range([h, 0]);
    g.append("g").attr("class", "grid").call(d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(""));
    g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(5).tickFormat((v) => (v > 0 ? "+" : "") + v.toFixed(3)).tickSize(0).tickPadding(8)).select(".domain").remove();
    g.append("line").attr("x1", 0).attr("x2", w).attr("y1", y(0)).attr("y2", y(0)).attr("stroke", C.ink2);
    g.append("line").attr("x1", 0).attr("x2", w).attr("y1", y(D.promotion_margin)).attr("y2", y(D.promotion_margin)).attr("stroke", C.ink2).attr("stroke-dasharray", "5 4");
    g.append("text").attr("x", w).attr("y", y(D.promotion_margin) - 6).attr("text-anchor", "end").attr("fill", C.ink2).attr("font-size", 11).text("promotion gate +0.01");
    rows.forEach((d) => {
      ["validation_lift", "test_lift"].forEach((k) => {
        const v = d[k];
        const bar = g.append("rect").attr("x", x(d.id) + xi(k)).attr("width", xi.bandwidth()).attr("rx", 3)
          .attr("fill", k === "validation_lift" ? C.blue : C.orange)
          .attr("y", y(0)).attr("height", 0)
          .on("mousemove", (ev) => showTip(ev, `<b>${d.id} · ${d.label}</b>` + row(k === "validation_lift" ? "Validation lift" : "Test lift", signed(v)) + row("Validation fraud", d.validation_fraud) + row("Test fraud", d.test_fraud) + row("Role", d.role)))
          .on("mouseleave", hideTip);
        bar.transition().duration(animate && !reduceMotion ? 800 : 0).delay(animate ? 200 : 0)
          .attr("y", v >= 0 ? y(v) : y(0)).attr("height", Math.max(1, Math.abs(y(v) - y(0))));
        g.append("text").attr("x", x(d.id) + xi(k) + xi.bandwidth() / 2).attr("y", v >= 0 ? y(v) - 5 : y(v) + 13).attr("text-anchor", "middle")
          .attr("fill", C.ink2).attr("font-size", 10).attr("font-family", "IBM Plex Mono").text(signed(v, 4));
      });
      g.append("text").attr("x", x(d.id) + x.bandwidth() / 2).attr("y", h + 18).attr("text-anchor", "middle").attr("fill", C.ink).attr("font-size", 12).attr("font-weight", 600).text(d.id);
      g.append("text").attr("x", x(d.id) + x.bandwidth() / 2).attr("y", h + 34).attr("text-anchor", "middle").attr("fill", C.ink3).attr("font-size", 10.5).text(W < 460 ? d.role : d.label.replace(" (published)", ""));
    });
  }

  function coverageBars(D) {
    const el = $("#coverageBars");
    const cov = D.graph_coverage;
    const LABEL = {
      sender_degree: "Sender has earlier links", receiver_degree: "Receiver has earlier links",
      shared_counterparties: "Sender and receiver share a contact", ring_flag: "Possible ring (triangle)",
      same_component_flag: "Same connected cluster", receiver_pagerank: "Receiver PageRank",
      sender_fraud_rate: "Sender has past fraud", receiver_fraud_rate: "Receiver has past fraud",
    };
    const items = Object.keys(LABEL).map((k) => [LABEL[k], cov[k].share_nonzero_all, k]);
    const ds = D.dataset;
    const ctx = [
      ["Senders seen exactly once (full data)", ds.senders_seen_once_share, "txn"],
      ["Fraud receivers that are reused", ds.fraud_receivers_reused_share, "txn"],
      ["Fraud receivers that ever send money", ds.fraud_receivers_that_send_share, "txn"],
    ];
    const bar = ([label, v, k], color, tag) => `<div class="hbar"><div class="head"><span>${label}${tag ? `<span class="g ${tag}">${tag === "graph" ? "feature" : "data"}</span>` : ""}</span><b>${smartPct(v)}</b></div><div class="bar"><span style="background:${color}" data-w="${Math.max(v > 0 ? 0.6 : 0, v * 100).toFixed(2)}" title="${k}"></span></div></div>`;
    el.innerHTML = items.map((it) => bar(it, it[1] > 0.05 ? C.blue : C.orange, "graph")).join("") +
      `<div style="border-top:1px dashed var(--line);margin:4px 0 0;padding-top:10px;font:600 11.5px var(--mono);color:var(--ink-3)">WHY · ACROSS ALL ${int(ds.rows)} TRANSFERS</div>` +
      ctx.map((it) => bar(it, C.ink3, "txn")).join("");
    const fill = () => $$("span[data-w]", el).forEach((s, i) => setTimeout(() => (s.style.width = s.dataset.w + "%"), reduceMotion ? 0 : i * 90));
    onVisible(el, fill, 0.3);
  }

  const CASES = { caught_fraud: "Caught fraud", false_alarm: "False alarm", cleared_legit: "Cleared transfer", missed_fraud: "Missed fraud" };
  let currentCase = null;
  const FEATURE_TEXT = {
    amount_to_origin_balance: "amount ÷ sender balance", amount_to_dest_balance: "amount ÷ receiver balance",
    oldbalanceOrg: "sender balance (log)", oldbalanceDest: "receiver balance (log)", amount: "amount (log)",
    hour_sin: "hour of day (sin)", hour_cos: "hour of day (cos)", dest_is_merchant: "receiver is a merchant",
  };
  const ftext = (f) => FEATURE_TEXT[f] || f.replace(/^type_/, "type is ").replace(/_/g, " ");
  function waterfall(D, animate) {
    const ex = D.examples;
    if (currentCase === null) currentCase = ex[0].outcome;
    const seg = $("#caseSeg");
    seg.innerHTML = ex.map((e) => `<button type="button" data-case="${e.outcome}" aria-pressed="${e.outcome === currentCase}">${CASES[e.outcome] || e.outcome}</button>`).join("");
    $$("button", seg).forEach((b) => b.addEventListener("click", () => { currentCase = b.dataset.case; waterfall(D, true); }));
    const e = ex.find((d) => d.outcome === currentCase);
    $("#txnCard").innerHTML = [["Type", e.type], ["Amount", money(e.amount)], ["Sender balance", money(e.oldbalanceOrg)], ["Receiver balance", money(e.oldbalanceDest)]]
      .map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("");
    const flagged = e.fraud_probability >= e.threshold;
    $("#verdict").innerHTML = `<span class="chip ${flagged ? "warn" : "good"}">${flagged ? "flagged for review" : "cleared"}</span><span>score <b style="color:var(--ink)">${e.fraud_probability >= 0.9995 ? ">0.999" : e.fraud_probability.toFixed(4)}</b> · truth: <b style="color:var(--ink)">${e.is_fraud ? "fraud" : "legitimate"}</b></span>`;

    const final = logit(e.fraud_probability);
    const top = e.reason_codes.map((r) => ({ k: ftext(r.feature), v: r.shap_log_odds }));
    const rest = final - e.base_log_odds - top.reduce((a, r) => a + r.v, 0);
    const steps = [{ k: "average transfer (base)", v: e.base_log_odds, base: true }, ...top, { k: "all other features", v: rest }];
    let run = 0;
    steps.forEach((s) => { s.start = s.base ? 0 : run; run = s.base ? s.v : run + s.v; s.end = run; });
    const el = $("#chartWaterfall");
    el.innerHTML = "";
    const { w: W } = chartSize(el, 0.5);
    const rowH = 30, H = steps.length * rowH + 64;
    const m = { t: 10, r: 18, b: 40, l: W < 460 ? 130 : 170 }, w = W - m.l - m.r, h = H - m.t - m.b;
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
    const thr = logit(e.threshold);
    const ext = d3.extent([0, thr, final, ...steps.flatMap((s) => [s.start, s.end])]);
    const x = d3.scaleLinear().domain([ext[0] - 1, ext[1] + 1]).nice().range([0, w]);
    const y = d3.scaleBand().domain(steps.map((s) => s.k).concat(["final score"])).range([0, h]).padding(0.28);
    g.append("g").attr("class", "grid").call(d3.axisBottom(x).ticks(6).tickSize(h).tickFormat("")).attr("transform", "translate(0,0)");
    g.append("g").attr("class", "axis").attr("transform", `translate(0,${h})`).call(d3.axisBottom(x).ticks(6).tickSizeOuter(0));
    g.append("text").attr("x", w).attr("y", h + 32).attr("text-anchor", "end").attr("fill", C.ink2).attr("font-size", 11).text("log odds of fraud →");
    g.append("line").attr("x1", x(thr)).attr("x2", x(thr)).attr("y1", -4).attr("y2", h).attr("stroke", C.ink2).attr("stroke-dasharray", "5 4");
    g.append("text").attr("x", x(thr) + 4).attr("y", h - 4).attr("fill", C.ink2).attr("font-size", 10.5).text("flag line");
    steps.forEach((s, i) => {
      const color = s.base ? C.ink3 : s.v >= 0 ? C.orange : C.blue;
      g.append("text").attr("x", -10).attr("y", y(s.k) + y.bandwidth() / 2 + 4).attr("text-anchor", "end").attr("fill", C.ink2).attr("font-size", 12).text(s.k);
      const r = g.append("rect").attr("y", y(s.k)).attr("height", y.bandwidth()).attr("rx", 3).attr("fill", color)
        .attr("x", x(Math.min(s.start, s.end))).attr("width", animate && !reduceMotion ? 0 : Math.max(2, Math.abs(x(s.end) - x(s.start))))
        .on("mousemove", (ev) => showTip(ev, `<b>${s.k}</b>` + row("Contribution", (s.v >= 0 ? "+" : "") + s.v.toFixed(2) + " log odds") + row("Running total", s.end.toFixed(2))))
        .on("mouseleave", hideTip);
      if (animate && !reduceMotion) r.transition().delay(i * 160).duration(500).attr("width", Math.max(2, Math.abs(x(s.end) - x(s.start))));
      g.append("text").attr("x", x(Math.max(s.start, s.end)) + 5).attr("y", y(s.k) + y.bandwidth() / 2 + 4).attr("fill", C.ink).attr("font-size", 11).attr("font-family", "IBM Plex Mono")
        .text((s.base ? "" : s.v >= 0 ? "+" : "") + s.v.toFixed(2));
      if (i < steps.length - 1) g.append("line").attr("x1", x(s.end)).attr("x2", x(s.end)).attr("y1", y(s.k) + y.bandwidth()).attr("y2", y(steps[i + 1].k)).attr("stroke", C.ink3).attr("stroke-dasharray", "2 2");
    });
    g.append("text").attr("x", -10).attr("y", y("final score") + y.bandwidth() / 2 + 4).attr("text-anchor", "end").attr("fill", C.ink).attr("font-size", 12).attr("font-weight", 700).text("final score");
    g.append("circle").attr("cx", x(final)).attr("cy", y("final score") + y.bandwidth() / 2).attr("r", 6).attr("fill", flagged ? C.orange : C.good);
    g.append("text").attr("x", x(final) + 10).attr("y", y("final score") + y.bandwidth() / 2 + 4).attr("fill", C.ink).attr("font-size", 11).attr("font-family", "IBM Plex Mono").text(final.toFixed(2));
  }

  function shapChart(D) {
    const el = $("#chartShap");
    el.innerHTML = "";
    const rows = D.shap.xgboost_graph.slice(0, 12);
    const { w: W } = chartSize(el, 0.6);
    const H = rows.length * 22 + 36;
    const m = { t: 4, r: 40, b: 28, l: W < 460 ? 150 : 190 }, w = W - m.l - m.r, h = H - m.t - m.b;
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
    const x = d3.scaleLinear().domain([0, d3.max(rows, (d) => d.mean_abs_shap)]).nice().range([0, w]);
    const y = d3.scaleBand().domain(rows.map((d) => d.feature)).range([0, h]).padding(0.25);
    g.append("g").attr("class", "axis").attr("transform", `translate(0,${h})`).call(d3.axisBottom(x).ticks(4).tickSizeOuter(0));
    rows.forEach((d) => {
      g.append("text").attr("x", -8).attr("y", y(d.feature) + y.bandwidth() / 2 + 4).attr("text-anchor", "end").attr("fill", d.is_graph ? C.orange : C.ink2).attr("font-size", 11.5).text(ftext(d.feature));
      g.append("rect").attr("x", 0).attr("y", y(d.feature)).attr("height", y.bandwidth()).attr("width", Math.max(1, x(d.mean_abs_shap))).attr("rx", 3).attr("fill", d.is_graph ? C.orange : C.blue)
        .on("mousemove", (ev) => showTip(ev, `<b>${d.feature}</b>` + row("Mean |SHAP|", d.mean_abs_shap.toFixed(3)) + row("Mean on fraud", d.mean_shap_fraud.toFixed(2)) + row("Mean on legit", d.mean_shap_legit.toFixed(2)) + row("Graph feature", d.is_graph ? "yes" : "no")))
        .on("mouseleave", hideTip);
      g.append("text").attr("x", x(d.mean_abs_shap) + 5).attr("y", y(d.feature) + y.bandwidth() / 2 + 4).attr("fill", C.ink2).attr("font-size", 10.5).attr("font-family", "IBM Plex Mono").text(d.mean_abs_shap.toFixed(2));
    });
  }

  let driftIdx = null;
  function driftPanel(D, animate) {
    const sweep = D.drift.sweep;
    const slider = $("#multSlider");
    slider.max = sweep.length - 1;
    if (driftIdx === null) { driftIdx = sweep.findIndex((s) => s.multiplier === 1); slider.value = driftIdx; }
    $("#multTicks").innerHTML = sweep.map((s) => `<span>${s.multiplier}×</span>`).join("");
    const edges = D.drift.log10_edges;
    const centers = edges.slice(0, -1).map((e, i) => (e + edges[i + 1]) / 2);
    const el = $("#chartDrift");
    el.innerHTML = "";
    const { w: W } = chartSize(el, 0.42);
    const H = Math.round(Math.max(170, W * 0.4));
    const m = { t: 10, r: 12, b: 32, l: 40 }, w = W - m.l - m.r, h = H - m.t - m.b;
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
    const x = d3.scaleLinear().domain([0, 8]).range([0, w]);
    const ymax = d3.max(sweep.flatMap((s) => s.amount_hist).concat(D.drift.reference_amount_hist));
    const y = d3.scaleLinear().domain([0, ymax * 1.05]).range([h, 0]);
    g.append("g").attr("class", "axis").attr("transform", `translate(0,${h})`).call(d3.axisBottom(x).tickValues([1, 2, 3, 4, 5, 6, 7]).tickFormat((v) => money(Math.pow(10, v))).tickSizeOuter(0));
    g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(3).tickFormat(d3.format(".0%")).tickSize(0).tickPadding(6)).select(".domain").remove();
    const area = d3.area().curve(d3.curveMonotoneX).x((_, i) => x(centers[i])).y0(h).y1((d) => y(d));
    g.append("path").datum(D.drift.reference_amount_hist).attr("d", area).attr("fill", C.ink3).attr("opacity", 0.25).attr("stroke", C.ink3).attr("stroke-width", 1.2);
    const cur = g.append("path").attr("fill", C.blue).attr("opacity", 0.28).attr("stroke", C.blue).attr("stroke-width", 1.8);
    const update = (anim) => {
      const s = sweep[+slider.value];
      cur.datum(s.amount_hist).transition().duration(anim && !reduceMotion ? 450 : 0).attr("d", area);
      $("#multVal").textContent = s.multiplier + "×";
      const chip = $("#driftChip");
      chip.textContent = s.alert ? "drift alert" : "healthy";
      chip.className = "chip " + (s.alert ? "bad" : "good");
      const thr = D.drift.threshold;
      $("#dAmt").textContent = s.amount_ks.toFixed(3);
      $("#dAmt").style.color = s.amount_ks >= thr ? "var(--bad)" : "";
      $("#dScore").textContent = s.score_ks.toFixed(3);
      $("#dScore").style.color = s.score_ks >= thr ? "var(--bad)" : "";
      $("#dAlerts").textContent = int(s.alerts_per_100k);
      $("#dJob").textContent = s.alert ? "queued" : "none";
      $("#dJob").style.color = s.alert ? "var(--orange)" : "";
    };
    slider.oninput = () => { driftIdx = +slider.value; update(true); };
    update(false);
  }

  function dailyChart(D, animate) {
    const el = $("#chartDaily");
    el.innerHTML = "";
    const rows = D.drift.daily;
    const { w: W, h: H } = chartSize(el, 0.55);
    const m = { t: 18, r: 12, b: 40, l: 40 }, w = W - m.l - m.r, h = H - m.t - m.b;
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`);
    const g = svg.append("g").attr("transform", `translate(${m.l},${m.t})`);
    const x = d3.scaleBand().domain(rows.map((d) => d.day)).range([0, w]).padding(0.22);
    const CAP = 0.3;
    const y = d3.scaleLinear().domain([0, CAP]).range([h, 0]);
    g.append("g").attr("class", "grid").call(d3.axisLeft(y).ticks(4).tickSize(-w).tickFormat(""));
    g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(4).tickSize(0).tickPadding(6)).select(".domain").remove();
    g.append("g").attr("class", "axis").attr("transform", `translate(0,${h})`).call(d3.axisBottom(x).tickValues(rows.map((d) => d.day).filter((d) => W > 460 || d % 2 === 1)).tickSizeOuter(0));
    g.append("text").attr("x", w).attr("y", h + 32).attr("text-anchor", "end").attr("fill", C.ink2).attr("font-size", 11.5).text("Day of the test window");
    g.append("line").attr("x1", 0).attr("x2", w).attr("y1", y(D.drift.threshold)).attr("y2", y(D.drift.threshold)).attr("stroke", C.ink2).attr("stroke-dasharray", "5 4");
    g.append("text").attr("x", 4).attr("y", y(D.drift.threshold) - 6).attr("fill", C.ink2).attr("font-size", 11).text("alert line 0.10");
    rows.forEach((d, i) => {
      const v = Math.max(d.amount_ks, d.score_ks);
      const low = d.rows < 1000;
      const color = d.alert ? C.orange : C.blue;
      const r = g.append("rect").attr("x", x(d.day)).attr("width", x.bandwidth()).attr("rx", 3)
        .attr("fill", low ? "transparent" : color).attr("stroke", color).attr("stroke-width", low ? 1.6 : 0)
        .attr("y", h).attr("height", 0)
        .on("mousemove", (ev) => showTip(ev, `<b>Day ${d.day} · steps ${d.first_step} to ${d.last_step}</b>` + row("Transfers", int(d.rows)) + row("Amount KS", d.amount_ks.toFixed(3)) + row("Score KS", d.score_ks.toFixed(3)) + row("Would alert", d.alert ? "yes" : "no")))
        .on("mouseleave", hideTip);
      r.transition().delay(animate && !reduceMotion ? i * 40 : 0).duration(animate && !reduceMotion ? 500 : 0).attr("y", y(Math.min(CAP, v))).attr("height", h - y(Math.min(CAP, v)));
      if (v > CAP) g.append("text").attr("x", x(d.day) + x.bandwidth() / 2).attr("y", -4).attr("text-anchor", "middle").attr("fill", C.ink2).attr("font-size", 9.5).attr("font-family", "IBM Plex Mono").text("▲" + v.toFixed(2));
    });
  }

  /* =========================================================
     PIPELINE
     ========================================================= */
  const NODES = [
    { id: "data", x: 20, y: 60, t: "PaySim CSV", s: "6.36M rows · local",
      plain: "A public, simulated record of a month of mobile money transfers, with each fraud labeled. It stays on the laptop; only summaries are published.",
      tech: ["ealaxi/paysim1 on Kaggle, CC BY-SA 4.0; git-ignored", "Read in 200k row chunks with explicit dtypes", "Post event columns dropped at load: newbalanceOrig, newbalanceDest, isFlaggedFraud"], stack: ["pandas"] },
    { id: "split", x: 170, y: 60, t: "Cohort + time split", s: "25% · whole steps",
      plain: "A random quarter of transfers is drawn without looking at labels, then split by time: learn on the past, tune on the middle, grade on the end.",
      tech: ["Seeded uniform draw window [0.25, 0.50) for E4", "Quantiles of step → train ≤ 281, validation ≤ 355, test after", "Each window must contain both classes"], stack: ["numpy", "pandas"] },
    { id: "features", x: 320, y: 60, t: "Features", s: "13 txn + 11 graph",
      plain: "Each transfer becomes numbers the model can learn from: amount, balances, type, time of day, and how the accounts were linked before.",
      tech: ["amount / balance ratios (capped at 1e6), log amounts, hour sin/cos, one hot type, merchant flag", "TemporalGraph: degree, PageRank, shared counterparties, ring flag, components, neighbor fraud rates", "Same step isolation; labels learned in train only"], stack: ["NetworkX", "numpy"] },
    { id: "models", x: 470, y: 60, t: "3 candidates", s: "LogReg + 2 XGB",
      plain: "Three models are trained on identical data: a simple baseline, a strong tree model, and the same tree model with network features added.",
      tech: ["Class balanced logistic regression (scaled)", "XGBoost hist, 180 trees, depth 5, scale_pos_weight = neg/pos", "Thresholds from validation negatives at FPR ≤ 1%"], stack: ["scikit-learn", "XGBoost"] },
    { id: "gate", x: 620, y: 60, t: "Promotion gate", s: "Δ PR-AUC ≥ 0.01",
      plain: "The network model only wins if it clearly beats the simple one on the tuning data. Small wins are treated as luck.",
      tech: ["champion = graph iff ΔPR-AUC_val ≥ 0.01, else transaction XGBoost", "Test window evaluated only after selection", "E4 result: Δval −0.0020 → transaction model"], stack: ["MLflow"] },
    { id: "registry", x: 770, y: 60, t: "Model registry", s: "MLflow · @champion",
      plain: "Every run is logged with its settings and scores. The chosen model gets a version number and a 'champion' label the API looks up.",
      tech: ["SQLite tracking store; runs per candidate", "Registered model graph-aware-fraud-detector, alias champion", "feature_mode tag + frozen graph snapshot artifact"], stack: ["MLflow"] },
    { id: "api", x: 920, y: 60, t: "Scoring API", s: "FastAPI · SHAP",
      plain: "Send a transfer, get back a fraud probability and the top three reasons, in milliseconds.",
      tech: ["POST /score with only pre transaction fields (Pydantic validated)", "Top 3 signed TreeSHAP contributions in log odds", "GET /health returns the champion version"], stack: ["FastAPI", "XGBoost pred_contribs"] },
    { id: "replay", x: 470, y: 200, t: "Later window replay", s: "× amount shift",
      plain: "To test monitoring, next month's transfers are replayed, optionally with every amount scaled up or down, and rescored by the live model.",
      tech: ["Reference = validation scores; current = test window", "--amount-multiplier rebuilds amount features and rescores", "Deterministic 20k row samples"], stack: ["pandas"] },
    { id: "drift", x: 620, y: 200, t: "Drift check", s: "Evidently + KS",
      plain: "The monitor compares the new data with the old. If amounts or scores moved enough, it raises an alarm and saves a full report.",
      tech: ["Evidently DataDriftPreset HTML report on amount + score", "Alert: KS ≥ 0.10 and p < 0.01 on either", "Report failures are recorded; the alert rule still runs"], stack: ["Evidently", "SciPy"] },
    { id: "retrain", x: 770, y: 200, t: "Retrain queue", s: "waits for labels",
      plain: "An alarm does not retrain blindly. It queues a job that waits for confirmed fraud outcomes, then reruns the full time based evaluation.",
      tech: ["retrain_request.json: queued_awaiting_mature_labels", "fraud-lab retrain --labeled-csv repeats train + gate + registration", "Job marked completed with the new version"], stack: ["CLI", "MLflow"] },
    { id: "ui", x: 920, y: 200, t: "Dashboard", s: "Streamlit · live",
      plain: "A live dashboard shows monitor status, lets you replay a drift scenario, and scores a transfer by hand.",
      tech: ["30 s auto refresh fragment", "Drift replay slider and score tail histogram", "Manual scorer with reason codes"], stack: ["Streamlit"] },
  ];
  const EDGES = [["data", "split"], ["split", "features"], ["features", "models"], ["models", "gate"], ["gate", "registry"], ["registry", "api"], ["registry", "replay"], ["replay", "drift"], ["drift", "retrain"], ["retrain", "ui"]];
  function pipeline() {
    const svg = d3.select("#pipe");
    svg.selectAll("*").remove();
    const NW = 140, NH = 58;
    const byId = Object.fromEntries(NODES.map((n) => [n.id, n]));
    svg.append("text").attr("x", 20).attr("y", 36).attr("fill", C.ink3).attr("font-size", 11).attr("font-family", "IBM Plex Mono").text("BUILD + CHOOSE");
    svg.append("text").attr("x", 470).attr("y", 176).attr("fill", C.ink3).attr("font-size", 11).attr("font-family", "IBM Plex Mono").text("SERVE + WATCH");
    const paths = EDGES.map(([a, b]) => {
      const A = byId[a], B = byId[b];
      let d;
      if (A.y === B.y) d = `M${A.x + NW},${A.y + NH / 2} L${B.x},${B.y + NH / 2}`;
      else d = `M${A.x + NW / 2},${A.y + NH} L${A.x + NW / 2},${A.y + NH + 30} L${B.x + NW / 2},${A.y + NH + 30} L${B.x + NW / 2},${B.y}`;
      return svg.append("path").attr("class", "edge").attr("d", d).node();
    });
    const nodes = svg.selectAll("g.node").data(NODES).enter().append("g").attr("class", "node")
      .attr("transform", (d) => `translate(${d.x},${d.y})`).attr("tabindex", 0).attr("role", "button").attr("aria-label", (d) => d.t);
    nodes.append("rect").attr("width", NW).attr("height", NH).attr("rx", 12);
    nodes.append("text").attr("x", 14).attr("y", 25).text((d) => d.t);
    nodes.append("text").attr("class", "sub").attr("x", 14).attr("y", 43).text((d) => d.s);
    const select = (d) => {
      nodes.classed("active", (n) => n.id === d.id);
      $("#nodeDetail").innerHTML = `<div><div class="kicker">${d.s}</div><h3>${d.t}</h3><p class="for-plain">${d.plain}</p><ul class="facts for-tech">${d.tech.map((t) => `<li>${t}</li>`).join("")}</ul></div>
        <div><p class="for-plain" style="font-size:14px">Switch to <b>Technical</b> at the top for implementation details.</p><ul class="facts for-plain">${d.tech.slice(0, 2).map((t) => `<li>${t}</li>`).join("")}</ul><div style="font-size:13px;color:var(--ink-2);margin-top:6px" class="for-tech">Built with</div><div class="stack">${d.stack.map((s) => `<span>${s}</span>`).join("")}</div></div>`;
    };
    nodes.on("click", (_, d) => select(d)).on("keydown", (ev, d) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); select(d); } });
    select(byId.gate);
    if (reduceMotion) return;
    const parts = paths.flatMap((p, i) => Array.from({ length: 2 }, (_, k) => ({ p, len: p.getTotalLength(), off: k / 2, el: svg.insert("circle", "g.node").attr("r", 3.2).attr("class", "particle" + (i >= 6 ? " alt" : "")) })));
    let visible = true;
    new IntersectionObserver((e) => (visible = e[0].isIntersecting)).observe($("#pipe"));
    const tick = (t) => {
      if (visible) parts.forEach((q) => {
        const k = ((t / 2400 + q.off) % 1);
        const pt = q.p.getPointAtLength(k * q.len);
        q.el.attr("cx", pt.x).attr("cy", pt.y).attr("opacity", Math.sin(k * Math.PI));
      });
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  pipeline();
  rerenders.push(pipeline);

  /* ---------------- Copy button ---------------- */
  $("#copyBtn").addEventListener("click", async () => {
    const text = $("#cmds").innerText.split("\n").filter((l) => l.startsWith("$")).map((l) => l.slice(2)).join("\n");
    try { await navigator.clipboard.writeText(text); $("#copyBtn").textContent = "Copied ✓"; } catch { $("#copyBtn").textContent = "Copy failed"; }
    setTimeout(() => ($("#copyBtn").textContent = "Copy"), 1600);
  });

  /* ---------------- Load data & draw ---------------- */
  fetch("data/summary.json")
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((D) => {
      const champ = D.models[D.champion];
      $("#testRows").textContent = int(D.counts.test.rows);
      $("#testFraud").textContent = int(D.counts.test.fraud);
      $("#f1Auc").textContent = D.models.xgboost_baseline.test.pr_auc.toFixed(3);
      $("#f2Prec").textContent = pct(champ.test.tp / (champ.test.tp + champ.test.fp), 0);
      $("#f5Drain").textContent = pct(D.dataset.drain.fraud_share, 1);
      $("#f6Ks").textContent = D.drift.sweep.find((s) => s.multiplier === 3).amount_ks.toFixed(3);

      const charts = [
        ["#chartPR", (a) => prChart(D, a)],
        ["#chartOp", (a) => operatingPanel(D, a)],
        ["#chartLift", (a) => liftChart(D, a)],
        ["#chartWaterfall", (a) => waterfall(D, a)],
        ["#chartShap", () => shapChart(D)],
        ["#chartDrift", (a) => driftPanel(D, a)],
        ["#chartDaily", (a) => dailyChart(D, a)],
      ];
      charts.forEach(([sel, fn]) => onVisible($(sel).closest(".chart-card") || $(sel), () => fn(true), 0.2));
      coverageBars(D);
      $("details").addEventListener("toggle", () => shapChart(D));
      const redraw = () => { charts.forEach(([sel, fn]) => { if ($(sel).childElementCount) fn(false); }); coverageBars(D); };
      rerenders.push(redraw);
      let rt, lastW = innerWidth;
      addEventListener("resize", () => { if (innerWidth === lastW) return; lastW = innerWidth; clearTimeout(rt); rt = setTimeout(redraw, 200); });
    })
    .catch((err) => {
      $$(".chart").forEach((el) => (el.innerHTML = `<p style="padding:20px">Couldn't load results (${err.message}). Serve this folder over HTTP, e.g. <code>python -m http.server</code>.</p>`));
    });
})();
