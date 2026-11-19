/* Mapa de rutas con aviones animados (sin librerias).
   Lo usan el dashboard de Streamlit (dentro de un componente HTML) y dashboard.html.
   Fondo: Esri Dark Gray Canvas (necesita internet, no pide clave); arcos, aeropuertos y aviones en SVG.
   Uso:  MapaVuelos(elemento, {clave, z, lon, lat, arcos:[{a,b,color,ancho,tip}],
                               nodos:[{c,pax,rutas,tip}], aeropuertos:{IATA:{lat,lon,ciudad,pais}}, vacio})
   Clic en un aeropuerto: muestra solo sus rutas, con aviones de ida y de vuelta. */
(function () {
  "use strict";
  const AVION = "M11,0 L4,-1.6 L-2,-8.5 L-4.2,-8.5 L-1.2,-1.6 L-7,-1.4 L-9.5,-4.2 L-11,-4.2 L-9.6,0 " +
                "L-11,4.2 L-9.5,4.2 L-7,1.4 L-1.2,1.6 L-4.2,8.5 L-2,8.5 L4,1.6 Z";
  const ESRI = "https://services.arcgisonline.com/arcgis/rest/services/Canvas";
  const esc = s => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  let contador = 0;

  function proy(lon, lat, z) {
    const n = 256 * 2 ** z, s = Math.sin(lat * Math.PI / 180);
    return [(lon + 180) / 360 * n, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n];
  }

  function tooltipPropio() {   // si la pagina no tiene uno (componente de Streamlit)
    if (document.getElementById("tip")) return;
    const t = document.createElement("div"); t.id = "tip";
    t.style.cssText = "position:fixed;pointer-events:none;background:#131c2e;color:#e6edf7;border:1px solid #2a3b5c;" +
      "border-radius:8px;padding:8px 10px;font:12.5px/1.5 'Segoe UI',system-ui,sans-serif;z-index:50;display:none;" +
      "box-shadow:0 6px 24px rgba(0,0,0,.45);max-width:320px";
    document.body.appendChild(t);
    document.addEventListener("mousemove", e => {
      const el = e.target.closest && e.target.closest("[data-tip]");
      if (!el || e.buttons) { t.style.display = "none"; return; }
      t.innerHTML = el.getAttribute("data-tip"); t.style.display = "block";
      const w = t.offsetWidth, h = t.offsetHeight;
      t.style.left = Math.min(e.clientX + 14, innerWidth - w - 8) + "px";
      t.style.top = (e.clientY + 16 + h > innerHeight ? e.clientY - h - 12 : e.clientY + 16) + "px";
    });
  }

  function estilos() {
    if (document.getElementById("mv-estilos")) return;
    const s = document.createElement("style"); s.id = "mv-estilos";
    s.textContent = `
      .mv { position:relative; overflow:hidden; background:#0e1626; cursor:grab; user-select:none; touch-action:none; }
      .mv.arrastrando { cursor:grabbing; }
      .mv img { position:absolute; width:256px; height:256px; pointer-events:none; }
      .mv svg { position:absolute; inset:0; }
      .mv .arco { fill:none; stroke-linecap:round; opacity:.85; cursor:pointer; transition:opacity .2s; }
      .mv .arco:hover { opacity:1; }
      .mv .arco.apagado { opacity:.10; }
      .mv .aero { cursor:pointer; }
      .mv .aero:hover { stroke:#fff; stroke-width:2; }
      .mv .avion path { fill:#ffffff; stroke:#0b1220; stroke-width:.8; }
      .mv .avion { filter:drop-shadow(0 0 3px rgba(61,156,245,.95)); pointer-events:none; }
      .mv .zoom { position:absolute; top:12px; right:12px; display:flex; flex-direction:column; gap:4px; z-index:2; }
      .mv .zoom button { width:32px; height:32px; background:#1b2537; color:#e6edf7; border:1px solid #2a3b5c;
                         border-radius:6px; font-size:1.1rem; cursor:pointer; }
      .mv .creditos { position:absolute; right:6px; bottom:4px; font-size:.7rem; color:#9aa6b8;
                      background:rgba(11,18,32,.7); padding:1px 6px; border-radius:4px; z-index:2; font-family:sans-serif; }
      .mv .ayuda { position:absolute; left:12px; top:12px; z-index:2; background:rgba(19,28,46,.88); color:#cfe6ff;
                   border:1px solid #2a3b5c; border-radius:8px; padding:7px 11px; font:12.5px/1.45 'Segoe UI',system-ui,sans-serif;
                   max-width:330px; }
      .mv .ayuda b { color:#fff; }
      .mv .ayuda button { margin-left:8px; background:#3d9cf5; color:#06101f; border:none; border-radius:999px;
                          padding:2px 10px; font:600 12px 'Segoe UI',system-ui,sans-serif; cursor:pointer; }`;
    document.head.appendChild(s);
  }

  // Encuadre: el mayor zoom en que entran todos los aeropuertos mostrados
  function encuadre(el, cfg) {
    const W = el.clientWidth || 900, H = el.clientHeight || 560, A = cfg.aeropuertos;
    const cods = cfg.nodos.map(n => n.c).filter(c => A[c]);
    if (!cods.length) { const [cx, cy] = proy(cfg.lon, cfg.lat, cfg.z); return { z: cfg.z, cx, cy }; }
    for (let z = 7; z >= 2; z--) {
      const xy = cods.map(c => proy(A[c].lon, A[c].lat, z));
      const xs = xy.map(p => p[0]), ys = xy.map(p => p[1]);
      const ancho = Math.max(...xs) - Math.min(...xs), alto = Math.max(...ys) - Math.min(...ys);
      if ((ancho <= W - 100 && alto <= H - 60) || z === 2)
        return { z, cx: (Math.max(...xs) + Math.min(...xs)) / 2, cy: (Math.max(...ys) + Math.min(...ys)) / 2 - alto * .08 };
    }
  }

  function MapaVuelos(el, cfg) {
    estilos(); tooltipPropio();
    el.classList.add("mv");
    let S = el._mv;
    const clave = cfg.clave + "|" + cfg.nodos.map(n => n.c).sort().join(",");
    if (!S || S.clave !== clave) {            // otra vista u otras rutas: encuadrar
      S = el._mv = { clave, ...encuadre(el, cfg), foco: null, id: "mv" + (++contador) };
      if (!el._mvEventos) { el._mvEventos = true; eventos(el); }   // una sola vez por elemento
    }
    S.cfg = cfg;
    if (S.foco && !cfg.nodos.some(n => n.c === S.foco)) S.foco = null;
    dibujar(el);
  }

  function dibujar(el) {
    const S = el._mv, cfg = S.cfg, W = el.clientWidth || 900, H = el.clientHeight || 560, z = S.z, n = 2 ** z;
    const ox = W / 2 - S.cx, oy = H / 2 - S.cy, A = cfg.aeropuertos;
    let teselas = "";
    for (let x = Math.floor(-ox / 256); x <= Math.floor((W - ox) / 256); x++)
      for (let y = Math.max(0, Math.floor(-oy / 256)); y <= Math.min(n - 1, Math.floor((H - oy) / 256)); y++) {
        const xx = ((x % n) + n) % n, pos = `style="left:${x*256+ox}px;top:${y*256+oy}px" alt="" onerror="this.remove()"`;
        // Esri Dark Gray Canvas (sin clave): fondo + capa de nombres de paises y ciudades
        teselas += `<img src="${ESRI}/World_Dark_Gray_Base/MapServer/tile/${z}/${y}/${xx}" ${pos}>` +
                   `<img src="${ESRI}/World_Dark_Gray_Reference/MapServer/tile/${z}/${y}/${xx}" ${pos}>`;
      }
    const pt = c => { const [x, y] = proy(A[c].lon, A[c].lat, z); return [x + ox, y + oy]; };
    let svg = "", ayuda = "";
    if (!cfg.arcos.length) {
      svg = `<text x="${W/2}" y="${H/2}" text-anchor="middle" fill="#cfe6ff" font-size="15" font-family="sans-serif">${esc(cfg.vacio || "Sin rutas para mostrar.")}</text>`;
    } else {
      const foco = S.foco, toca = a => !foco || a.a === foco || a.b === foco;
      const k = z >= 5 ? 1 : .85, escala = z >= 5 ? 1.15 : z >= 4 ? 1 : .85;
      let arcos = "", aviones = "", defs = "";
      [...cfg.arcos].sort((p, q) => q.ancho - p.ancho).forEach((a, i) => {
        const [x1, y1] = pt(a.a), [x2, y2] = pt(a.b), dx = x2 - x1, dy = y2 - y1, dist = Math.hypot(dx, dy) || 1;
        let nx = -dy / dist, ny = dx / dist; if (ny > 0) { nx = -nx; ny = -ny; }        // curva hacia arriba
        const cx = (x1 + x2) / 2 + nx * dist * .22, cy = (y1 + y2) / 2 + ny * dist * .22;
        const ida = `M${x1},${y1} Q${cx},${cy} ${x2},${y2}`, vuelta = `M${x2},${y2} Q${cx},${cy} ${x1},${y1}`;
        const activo = toca(a);
        arcos += `<path class="arco${activo ? "" : " apagado"}" d="${ida}" stroke="${a.color}" stroke-width="${(a.ancho * k).toFixed(1)}" data-tip="${esc(a.tip)}"/>`;
        if (!activo) return;
        // un avion por ruta; con un aeropuerto elegido o pocas rutas, uno de ida y otro de vuelta
        const dur = Math.max(3.5, Math.min(14, dist / 55)), sentidos = foco || cfg.arcos.length <= 6 ? [ida, vuelta] : [i % 2 ? vuelta : ida];
        sentidos.forEach((d, j) => {
          const pid = `${S.id}-${i}-${j}`;
          defs += `<path id="${pid}" d="${d}"/>`;
          const desfase = ((i * 0.37 + j * 0.5) % 1) * dur;
          aviones += `<g class="avion"><g transform="scale(${escala})"><path d="${AVION}"/></g>
            <animateMotion dur="${dur.toFixed(1)}s" begin="-${desfase.toFixed(1)}s" repeatCount="indefinite" rotate="auto"><mpath href="#${pid}"/></animateMotion></g>`;
        });
      });
      const maxA = Math.max(...cfg.nodos.map(a => a.pax), 1);
      const conectados = new Set(foco ? cfg.arcos.filter(toca).flatMap(a => [a.a, a.b]) : []);
      let puntos = "";
      for (const nd of cfg.nodos) {
        const [x, y] = pt(nd.c), r = (z >= 5 ? 3.5 : 2.8) + (z >= 5 ? 13 : 10) * Math.sqrt(nd.pax / maxA);
        const visible = !foco || conectados.has(nd.c), elegido = nd.c === foco;
        const etiqueta = visible && (z >= 5 || nd.c === "LIM" || A[nd.c].pais !== "Perú" || (foco && conectados.has(nd.c)));
        puntos += `<circle class="aero" data-c="${nd.c}" cx="${x}" cy="${y}" r="${r.toFixed(1)}"
            fill="${elegido ? "#f0c247" : "rgba(230,237,247,.85)"}" fill-opacity="${visible ? 1 : .25}" stroke="#3d9cf5" stroke-width="1.2"
            data-tip="${esc(nd.tip + "<br><i>Clic para ver solo sus vuelos</i>")}"/>` +
          (etiqueta ? `<text x="${x}" y="${y - r - 5}" text-anchor="middle" fill="#e6edf7" font-size="11.5" font-weight="700" font-family="sans-serif"
            style="paint-order:stroke;stroke:#0b1220;stroke-width:3px;pointer-events:none">${nd.c}</text>` : "");
      }
      svg = `<defs>${defs}</defs>${arcos}${aviones}${puntos}`;
      if (foco) {
        const rutas = cfg.arcos.filter(toca).length, nd = cfg.nodos.find(x => x.c === foco);
        ayuda = `<div class="ayuda">✈ <b>${foco} · ${esc(A[foco].ciudad)}</b>: ${rutas} ruta${rutas > 1 ? "s" : ""}, ` +
                `${nd.pax.toLocaleString("en-US")} pasajeros<button data-accion="todo">Ver todas</button></div>`;
      } else {
        ayuda = `<div class="ayuda">Haz <b>clic en un aeropuerto</b> para ver solo sus vuelos.</div>`;
      }
    }
    el.innerHTML = `${teselas}<svg width="${W}" height="${H}">${svg}</svg>${ayuda}
      <div class="zoom"><button data-z="1" title="Acercar">+</button><button data-z="-1" title="Alejar">−</button><button data-z="0" title="Volver a la vista inicial">⟳</button></div>
      <div class="creditos">Esri, HERE, Garmin, © OpenStreetMap contributors</div>`;
  }

  function zoom(el, paso) {
    const S = el._mv;
    if (paso === 0) { Object.assign(S, encuadre(el, S.cfg)); S.foco = null; return dibujar(el); }
    const z = Math.min(10, Math.max(2, S.z + paso)); if (z === S.z) return;
    const f = 2 ** (z - S.z); S.cx *= f; S.cy *= f; S.z = z; dibujar(el);
  }

  function eventos(el) {
    let ini = null, ult = null, movido = false, pend = false;
    el.addEventListener("pointerdown", e => {
      if (e.target.closest(".zoom, .ayuda button")) return;
      ini = ult = [e.clientX, e.clientY]; movido = false; el.classList.add("arrastrando");
    });
    window.addEventListener("pointermove", e => {
      if (!ini) return;
      if (Math.hypot(e.clientX - ini[0], e.clientY - ini[1]) > 4) movido = true;
      if (!movido) return;
      el._mv.cx -= e.clientX - ult[0]; el._mv.cy -= e.clientY - ult[1]; ult = [e.clientX, e.clientY];
      if (!pend) { pend = true; requestAnimationFrame(() => { pend = false; dibujar(el); }); }
    });
    window.addEventListener("pointerup", e => {
      if (!ini) return;
      ini = null; el.classList.remove("arrastrando");
      if (movido) return;
      const c = e.target.closest && e.target.closest(".aero");     // clic sin arrastrar
      const S = el._mv;
      if (c) { S.foco = S.foco === c.dataset.c ? null : c.dataset.c; dibujar(el); }
    });
    el.addEventListener("click", e => {
      const b = e.target.closest(".zoom button"); if (b) return zoom(el, +b.dataset.z);
      if (e.target.closest(".ayuda button")) { el._mv.foco = null; dibujar(el); }
    });
    el.addEventListener("wheel", e => { e.preventDefault(); zoom(el, e.deltaY < 0 ? 1 : -1); }, { passive: false });
    window.addEventListener("resize", () => dibujar(el));
  }

  window.MapaVuelos = MapaVuelos;
})();
