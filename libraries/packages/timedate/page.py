"""The timedate home page markup + styling (one self-contained HTML document).

Split out of app.py so the Flask wiring stays small and the look lives on its own. The
page is deliberately minimal and calm: a large monospace clock (HH:MM:SS) over a line of
day / month / year, centered on a soft gradient, in the Az'arch cyan (#06B8FD, the same
accent os-release uses for ANSI_COLOR). No frameworks, no external fonts or assets -- it
must render instantly offline the moment the browser lands on it.

The server seeds the first paint with the system-zone `now` (so there is no flash of a
wrong time); the inline script then advances the clock every second using
Intl.DateTimeFormat pinned to the SYSTEM zone name, and re-syncs to /api/now on a slow
interval so it corrects drift and picks up a timezone change without a reload.
"""

from __future__ import annotations

import datetime
import html
import json

# Az'arch accent (same cyan as os-release ANSI_COLOR "38;2;6;184;253"). Single source of
# truth for the page's highlight colour so the brand stays consistent.
ACCENT = "#06B8FD"


def render(*, zone_name: str, now: datetime.datetime) -> str:
    """Return the complete HTML document for the given system zone and seed time.

    `zone_name` is the IANA name (e.g. "Asia/Jerusalem") the browser formats in;
    `now` seeds the initial values so the page is correct before JS runs. Everything is
    inlined -- one response, no second request needed to look right."""
    # Values embedded for the first paint. The script overwrites them on its first tick.
    seed = {
        "zone": zone_name,
        "epoch_ms": int(now.timestamp() * 1000),
    }
    # Human seeds for the noscript / pre-JS render.
    hh = f"{now.hour:02d}"
    mm = f"{now.minute:02d}"
    ss = f"{now.second:02d}"
    day_name = now.strftime("%A")
    date_line = now.strftime("%d %B %Y")
    safe_zone = html.escape(zone_name)
    seed_json = json.dumps(seed)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{hh}:{mm} · Az'arch</title>
<style>
  :root {{
    --accent: {ACCENT};
    --fg: #e8eef4;
    --fg-dim: #8fa3b6;
    --bg-0: #0b0f14;
    --bg-1: #121822;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; }}
  body {{
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    font-family: "Cantarell", "Noto Sans", system-ui, -apple-system, sans-serif;
    color: var(--fg);
    background: radial-gradient(1200px 700px at 50% -10%, var(--bg-1) 0%, var(--bg-0) 60%),
                var(--bg-0);
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
    overflow: hidden;
  }}
  .card {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.4rem;
    padding: 3rem 3.5rem;
    user-select: none;
  }}
  .clock {{
    font-family: "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", ui-monospace,
                 monospace;
    font-weight: 600;
    font-size: clamp(3.2rem, 15vw, 9.5rem);
    line-height: 1;
    letter-spacing: 0.02em;
    display: flex;
    align-items: baseline;
    gap: 0.06em;
  }}
  .clock .sep {{
    color: var(--accent);
    animation: blink 2s steps(1, end) infinite;
  }}
  @keyframes blink {{ 50% {{ opacity: 0.25; }} }}
  .clock .seconds {{
    color: var(--fg-dim);
    font-size: 0.42em;
    align-self: flex-end;
    margin-bottom: 0.28em;
    margin-left: 0.12em;
    letter-spacing: 0.04em;
  }}
  .dayname {{
    font-size: clamp(1rem, 4vw, 1.7rem);
    font-weight: 600;
    letter-spacing: 0.28em;
    text-transform: uppercase;
    color: var(--accent);
  }}
  .date {{
    font-size: clamp(1.1rem, 5vw, 2.2rem);
    font-weight: 300;
    letter-spacing: 0.04em;
    color: var(--fg);
  }}
  .zone {{
    margin-top: 0.4rem;
    font-size: 0.85rem;
    letter-spacing: 0.12em;
    color: var(--fg-dim);
    text-transform: uppercase;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{ --fg: #1b2430; --fg-dim: #5a6b7b; --bg-0: #eef3f8; --bg-1: #ffffff; }}
  }}
</style>
</head>
<body>
  <main class="card" role="main" aria-label="Current time and date">
    <div class="clock" id="clock" aria-live="off">
      <span id="hh">{hh}</span><span class="sep">:</span><span id="mm">{mm}</span><span class="seconds" id="ss">{ss}</span>
    </div>
    <div class="dayname" id="dayname">{html.escape(day_name)}</div>
    <div class="date" id="date">{html.escape(date_line)}</div>
    <div class="zone" id="zone" title="System timezone">{safe_zone}</div>
  </main>

<script>
(function () {{
  "use strict";
  // Seeded by the server: the system IANA zone and the server epoch at render time.
  var state = {seed_json};

  // Offset between the server clock and this browser's clock, measured at page load and
  // refreshed by /api/now, so the displayed time follows the SERVER (system) wall clock
  // and zone even if the browser's own clock/zone is off. Start from the seed.
  var skewMs = state.epoch_ms - Date.now();

  var MONTHS = ["January","February","March","April","May","June","July","August",
                "September","October","November","December"];

  function two(n) {{ return (n < 10 ? "0" : "") + n; }}

  // Format the current instant (server-corrected) in the SYSTEM zone using Intl, which
  // knows every IANA zone and handles DST correctly. We read individual parts so we can
  // lay them out (HH : MM ss) exactly.
  function partsInZone() {{
    var when = new Date(Date.now() + skewMs);
    var fmt;
    try {{
      fmt = new Intl.DateTimeFormat("en-GB", {{
        timeZone: state.zone,
        hour12: false,
        weekday: "long",
        day: "2-digit", month: "long", year: "numeric",
        hour: "2-digit", minute: "2-digit", second: "2-digit"
      }});
    }} catch (e) {{
      // Unknown zone (shouldn't happen -- the server validated it) -> fall back to the
      // browser's local zone so the page still ticks rather than freezing.
      fmt = new Intl.DateTimeFormat("en-GB", {{
        hour12: false, weekday: "long", day: "2-digit", month: "long",
        year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit"
      }});
    }}
    var out = {{}};
    fmt.formatToParts(when).forEach(function (p) {{ out[p.type] = p.value; }});
    return out;
  }}

  var el = {{
    hh: document.getElementById("hh"),
    mm: document.getElementById("mm"),
    ss: document.getElementById("ss"),
    dayname: document.getElementById("dayname"),
    date: document.getElementById("date"),
    zone: document.getElementById("zone"),
    title: null
  }};

  function tick() {{
    var p = partsInZone();
    // Intl "24" hour can render "24" at midnight in some engines; normalise to "00".
    var hh = p.hour === "24" ? "00" : p.hour;
    el.hh.textContent = hh;
    el.mm.textContent = p.minute;
    el.ss.textContent = p.second;
    el.dayname.textContent = (p.weekday || "").toUpperCase();
    el.date.textContent = (p.day || "") + " " + (p.month || "") + " " + (p.year || "");
    el.zone.textContent = state.zone;
    document.title = hh + ":" + p.minute + " · Az'arch";
  }}

  // Re-sync to the server every 60s: corrects clock drift AND picks up a timezone change
  // (the server reads /etc/localtime live, so if the user changes the zone the page
  // follows within a minute, no reload). Never lets a fetch failure break the local tick.
  function resync() {{
    fetch("/api/now", {{ cache: "no-store" }})
      .then(function (r) {{ return r.ok ? r.json() : null; }})
      .then(function (d) {{
        if (!d) return;
        state.zone = d.zone;
        skewMs = d.epoch_ms - Date.now();
      }})
      .catch(function () {{ /* offline/hiccup: keep ticking on the last known skew/zone */ }});
  }}

  tick();
  setInterval(tick, 1000);
  setInterval(resync, 60000);
  // Re-sync immediately when the tab regains focus (e.g. new tab opened after a while).
  document.addEventListener("visibilitychange", function () {{
    if (!document.hidden) resync();
  }});
}})();
</script>
</body>
</html>
"""
