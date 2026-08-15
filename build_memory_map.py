"""Build docs/memory-map.html — portfolio visualization of desk embeddings."""
from __future__ import annotations

import json
from pathlib import Path

from vector_memory import export_embedding_map, sync_desk_to_qdrant

ROOT = Path(__file__).resolve().parent
OUT_JSON = ROOT / "out" / "embedding_map.json"
OUT_HTML = ROOT / "docs" / "memory-map.html"


def main() -> None:
    sync_desk_to_qdrant()
    data = export_embedding_map(OUT_JSON)
    points = data.get("points") or []
    payload = json.dumps(data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Newsroom desk memory — embedding map</title>
  <style>
    :root {{
      --bg: #f6f1e8;
      --ink: #1c1917;
      --muted: #57534e;
      --line: #d6d3d1;
      --flaco: #0f766e;
      --mona: #b45309;
      --query: #1d4ed8;
      --other: #78716c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Helvetica Neue", sans-serif;
      color: var(--ink);
      background: var(--bg);
      line-height: 1.45;
    }}
    header {{
      padding: 2rem 1.5rem 1rem;
      max-width: 960px;
      margin: 0 auto;
    }}
    h1 {{
      font-family: Georgia, "Times New Roman", serif;
      font-weight: 600;
      font-size: clamp(1.6rem, 3vw, 2.2rem);
      margin: 0 0 0.5rem;
    }}
    .lede {{ color: var(--muted); max-width: 42rem; }}
    .grid {{
      display: grid;
      gap: 1.25rem;
      max-width: 960px;
      margin: 0 auto;
      padding: 0 1.5rem 3rem;
    }}
    @media (min-width: 860px) {{
      .grid {{ grid-template-columns: 1.4fr 1fr; }}
    }}
    .panel {{
      border: 1px solid var(--line);
      background: #fffdf8;
      padding: 1rem 1.1rem 1.2rem;
    }}
    .panel h2 {{
      font-size: 0.95rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
      margin: 0 0 0.75rem;
      font-weight: 600;
    }}
    svg {{ width: 100%; height: auto; display: block; background: #fff; border: 1px solid var(--line); }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 0.75rem 1.1rem; margin-top: 0.75rem; font-size: 0.9rem; }}
    .swatch {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 0.35rem; }}
    ol {{ margin: 0; padding-left: 1.2rem; color: var(--muted); }}
    li {{ margin-bottom: 0.55rem; }}
    code {{ font-size: 0.85em; background: #f5f5f4; padding: 0.05em 0.3em; }}
    .compare {{
      display: grid;
      gap: 0.75rem;
    }}
    @media (min-width: 600px) {{
      .compare {{ grid-template-columns: 1fr 1fr; }}
    }}
    .card {{
      border: 1px dashed var(--line);
      padding: 0.85rem;
      background: #fff;
    }}
    .card strong {{ display: block; margin-bottom: 0.35rem; }}
    footer {{
      max-width: 960px;
      margin: 0 auto;
      padding: 0 1.5rem 2.5rem;
      color: var(--muted);
      font-size: 0.85rem;
    }}
  </style>
</head>
<body>
  <header>
    <h1>How desk memory sees “eagle sighting”</h1>
    <p class="lede">
      Twelve Labs judges the <em>video pixels</em>. This map is the sponsor layer:
      Slack text, ticket aliases, and reject rules become number-lists (embeddings)
      stored in Qdrant. Nearby dots mean similar meaning — so a vague upload title
      can still land on <code>TICKET-FLACO-01</code>.
    </p>
  </header>

  <div class="grid">
    <section class="panel">
      <h2>Embedding map (2D sketch of nearness)</h2>
      <svg id="map" viewBox="0 0 640 420" role="img" aria-label="Scatter plot of memory embeddings"></svg>
      <div class="legend" id="legend"></div>
      <p class="lede" style="margin-top:0.75rem;font-size:0.9rem" id="caption"></p>
    </section>

    <section class="panel">
      <h2>Who does what</h2>
      <ol>
        <li><strong>Cognee-shaped memory</strong> chooses what to keep: tickets, aliases like “eagle sighting”, channel chatter, “never merge Mona into Flaco”.</li>
        <li><strong>Embedding model</strong> (free, on this PC) turns each memory card into a vector — a list of numbers.</li>
        <li><strong>Qdrant</strong> stores those vectors and finds nearest neighbors when you search.</li>
        <li><strong>Twelve Labs</strong> stays on video. After it decides, we save a short text note of that decision into the same memory.</li>
      </ol>

      <h2 style="margin-top:1.25rem">Why this helps the product</h2>
      <div class="compare">
        <div class="card">
          <strong>Without memory</strong>
          Vision alone can be slow or shallow; a filename like <code>eagle sighting.mp4</code> does not know Flaco is the desk ticket.
        </div>
        <div class="card">
          <strong>With memory + vision</strong>
          Qdrant already pulls Flaco aliases/channels; vision confirms the owl. Slack reply shows both layers — easier for judges to trust.
        </div>
      </div>
    </section>
  </div>

  <footer>
    Model: <span id="model"></span> · Collection: <span id="coll"></span> ·
    Generated for the Newsroom Entity Merge portfolio. Not a literal Cognee cloud deploy —
    same roles: memory orchestration + vector search, running locally without Docker.
  </footer>

  <script>
    const DATA = {payload};

    const colorFor = (p) => {{
      if (p.kind === "query") return "var(--query)";
      if (p.ticket === "TICKET-FLACO-01") return "var(--flaco)";
      if (p.ticket === "ART-MONA-220") return "var(--mona)";
      return "var(--other)";
    }};

    const xs = DATA.points.map(p => p.x);
    const ys = DATA.points.map(p => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const pad = 36;
    const W = 640, H = 420;
    const sx = (x) => pad + (W - 2*pad) * ((x - minX) / (maxX - minX || 1));
    const sy = (y) => H - pad - (H - 2*pad) * ((y - minY) / (maxY - minY || 1));

    const svg = document.getElementById("map");
    DATA.points.forEach((p) => {{
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", sx(p.x));
      c.setAttribute("cy", sy(p.y));
      c.setAttribute("r", p.kind === "query" ? 7 : 5);
      c.setAttribute("fill", colorFor(p));
      c.setAttribute("opacity", p.kind === "query" ? "1" : "0.85");
      c.setAttribute("stroke", p.kind === "query" ? "#1e3a8a" : "none");
      c.setAttribute("stroke-width", "1.5");
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = `[${{p.kind}}] ${{p.label}}`;
      c.appendChild(title);
      svg.appendChild(c);
      if (p.kind === "query") {{
        const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
        t.setAttribute("x", sx(p.x) + 9);
        t.setAttribute("y", sy(p.y) + 4);
        t.setAttribute("font-size", "11");
        t.setAttribute("fill", "#1e3a8a");
        t.textContent = p.label.length > 28 ? p.label.slice(0, 28) + "…" : p.label;
        svg.appendChild(t);
      }}
    }});

    document.getElementById("legend").innerHTML = `
      <span><i class="swatch" style="background:var(--flaco)"></i>Flaco ticket memories</span>
      <span><i class="swatch" style="background:var(--mona)"></i>Mona / art desk</span>
      <span><i class="swatch" style="background:var(--other)"></i>Slack chatter / other</span>
      <span><i class="swatch" style="background:var(--query)"></i>Search queries</span>
    `;
    document.getElementById("caption").textContent = DATA.caption || "";
    document.getElementById("model").textContent = DATA.model || "";
    document.getElementById("coll").textContent = DATA.collection || "";
  </script>
</body>
</html>
"""
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_HTML} ({len(points)} points)")


if __name__ == "__main__":
    main()
