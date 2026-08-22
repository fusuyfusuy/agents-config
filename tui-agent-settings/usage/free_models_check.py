#!/usr/bin/env python3
"""
free_models_check.py — Free models (OpenRouter + OpenCode) ranked by composite intelligence

Fetches the live OpenRouter model catalog (price $0) and the live OpenCode Go
model catalog (free = usage None, e.g. ox-alpha-free), keeps the FREE models,
attaches intelligence signals from Artificial Analysis (Intelligence Index)
and LMArena (ELO), builds a normalized composite score (z-scored per source,
averaged), and prints a table sorted by intelligence.

Stdlib only. Reuses parsers + cross-source matchers from ocgo_check.py.
No API keys. Console table by default; --json / --html flag the files.
"""
import argparse
import datetime as dt
import glob
import html
import json
import pathlib
import statistics
import sys

# ---- import ocgo_check's battle-tested parsers without duplicating them ----
HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
# repo root: llm-search has scripts/ one level down, agents-config has tui-agent-settings/usage/ two levels down
ROOT = HERE.parent
# walk up to find setup.sh / .git so the same file works in both repos
for _p in (HERE.parent, HERE.parent.parent, HERE.parent.parent.parent):
    if (_p / "setup.sh").exists() or (_p / ".git").exists():
        ROOT = _p
        break
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = ROOT / "outputs"

import ocgo_check as ogc  # pylint: disable=wrong-import-position,cyclic-import  # noqa: E402

OPENROUTER_API = ogc.OPENROUTER_API
OCGO_API = ogc.OCGO_API
AA_URL = ogc.AA_URL
LMARENA_URL = ogc.LMARENA_URL


def is_free_model(rec):
    """OpenRouter pricing $0 → free. Fields are strings like '0' or '0.0001'."""
    oid = rec.get("id", "") or ""
    if oid.endswith(":free"):
        return True
    p = rec.get("pricing", {}) or {}
    try:
        prompt = float(p.get("prompt", 0) or 0)
        completion = float(p.get("completion", 0) or 0)
    except Exception:
        return False
    return prompt == 0.0 and completion == 0.0


def base_id(oid):
    """Strip trailing :free tag so cross-source matching sees the real slug."""
    return oid.rsplit(":free", 1)[0] if oid.endswith(":free") else oid


def pick_latest_raw(name_part):
    """Newest snapshot in data/raw/ whose name contains name_part, or None."""
    # snapshots are named openrouter_models_YYYYMMDD.json etc. — suffix sorts lexically
    matches = sorted(glob.glob(str(RAW / f"*{name_part}*")))
    return pathlib.Path(matches[-1]) if matches else None


def render_html(rows, n_aa, n_lm):
    title = f"Free Models (OpenRouter + OpenCode) — Composite Intelligence ({dt.date.today().isoformat()})"
    trs = []
    top_id = rows[0]["model_id"] if rows and rows[0].get("composite") is not None else None
    for r in rows:
        b = r["benchmarks"]
        mid = html.escape(r["display"])
        prov = html.escape(r["provider"])
        aa = f"{b['aa_intelligence']:.1f}" if isinstance(b["aa_intelligence"], (int, float)) else "\u2014"
        aa_slug = html.escape(b["aa_slug"] or "")
        cod = f"{b['aa_coding']:.1f}" if isinstance(b["aa_coding"], (int, float)) else "\u2014"
        age = f"{b['aa_agentic']:.1f}" if isinstance(b["aa_agentic"], (int, float)) else "\u2014"
        elo = f"{b['lmarena_elo']:.0f}" if isinstance(b["lmarena_elo"], (int, float)) else "\u2014"
        rk = f"#{b['lmarena_rank']}" if isinstance(b["lmarena_rank"], int) else "\u2014"
        comp = f"{r['composite']:.2f}" if isinstance(r.get("composite"), (int, float)) else "\u2014"
        cov = "\u00b7".join(r.get("coverage", ["\u2014"]))
        ctx = f"{b['openrouter_context'] // 1000}k" if isinstance(b["openrouter_context"], (int, float)) else "\u2014"
        src_raw = r.get("source", "or")
        src = f'<span style="color:{"#3fb950" if src_raw=="oc" else "#58a6ff"};font-weight:600">{html.escape(src_raw)}</span>'
        cls = "top" if r["model_id"] == top_id else ""
        trs.append(
            f'<tr class="{cls}">'
            f'<td class="m">{mid}</td><td>{prov}</td><td>{src}</td>'
            f'<td class="n">{aa}<span class="mid">{aa_slug}</span></td>'
            f'<td class="n">{cod}</td><td class="n">{age}</td>'
            f'<td class="n">{elo}</td><td class="n">{rk}</td>'
            f'<td class="n">{comp}</td><td>{cov}</td><td class="n">{ctx}</td>'
            f"</tr>"
        )
    body = f"""
<h1>{html.escape(title)}</h1>
<p class="sub">Free models (<b>OpenRouter</b> prompt+completion <code>$0</code> + <b>OpenCode</b> <code>ox-alpha-free</code> etc.) ranked by normalized composite intelligence = mean of z-scored <a href="https://artificialanalysis.ai/leaderboards/models" style="color:#58a6ff">Artificial Analysis</a> Intelligence Index and <a href="https://lmarena.ai/leaderboard/text" style="color:#58a6ff">LMArena</a> ELO. <b>{len(rows)}</b> free models \u00b7 <b>{n_aa}</b> on AA \u00b7 <b>{n_lm}</b> on LMArena \u00b7 Generated {dt.datetime.now(dt.timezone.utc).isoformat()}</p>
<div class="card"><b>How to read:</b> <span style="color:#d29922">\u25a0 top</span> = highest composite intelligence. AA Intelligence/Coding/Agentic from artificialanalysis.ai; LMArena rank/ELO from lmarena.ai text leaderboard; context from OpenRouter. Cross-source scales are incomparable — the composite z-scores each source then averages available signals (a model in 0 sources \u2192 composite \u2014, at bottom).</div>
<div class="card">
<table id="tbl">
<thead><tr><th>model</th><th>provider</th><th>src</th><th>AA intel</th><th>AA cod</th><th>AA agent</th><th>LM ELO</th><th>LM rank</th><th>composite</th><th>coverage</th><th>ctx</th></tr></thead>
<tbody>{''.join(trs)}</tbody>
</table>
<div class="legend">Click headers to sort. \u2014 = not on that leaderboard. OpenRouter/OpenCode have no public bulk intelligence metric (per this repo's finding) — they contribute the free-model list + context; the composite uses AA + LMArena.</div>
</div>
<p class="note">Machine JSON: <a href="../data/free_models.json" style="color:#58a6ff">data/free_models.json</a>. Raw snapshots in <code>data/raw/</code> when run with <code>--fetch</code>. Stdlib only, no keys. Re-run: <code>python3 scripts/free_models_check.py</code> / <code>fcheck</code> / <code>fcheck --json --html --fetch</code>.</p>
<div class="footer"><span class="path">path: outputs/free_models.html</span><span class="work">Current work: composite rank of {len(rows)} free models (OR+OC) ({n_aa} on AA, {n_lm} on LMArena\u2014 top {html.escape(rows[0]['display']) if rows and rows[0].get('composite') is not None else 'none'}).</span></div>
<script>
(function(){{
  var tbl=document.getElementById('tbl');
  function getVal(tr,i){{
    var td=tr.children[i];
    var t=(td.innerText||'').replace(/[^0-9.\\-]/g,'').trim();
    var n=parseFloat(t);
    return isNaN(n)? (td.innerText||'').toLowerCase() : n;
  }}
  tbl.querySelectorAll('th').forEach(function(th,i){{
    th.addEventListener('click',function(){{
      var tbody=tbl.tBodies[0];
      var rows=[].slice.call(tbody.rows);
      var asc=th.asc=!th.asc;
      rows.sort(function(a,b){{
        var av=getVal(a,i), bv=getVal(b,i);
        if(typeof av==='number' && typeof bv==='number') return asc? av-bv : bv-av;
        return asc? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      }});
      rows.forEach(function(r){{tbody.appendChild(r);}});
    }});
  }});
}})();
</script>
"""
    css = """:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--txt:#e6edf3;--mut:#8b949e;--gr:#3fb950;--bl:#58a6ff;--yl:#d29922}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;padding:28px}
.wrap{max-width:1280px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}a{color:var(--bl)}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;cursor:pointer;user-select:none;white-space:nowrap}th:hover{color:var(--bl)}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.m{font-weight:600}.mid{display:block;color:var(--mut);font-size:10px;font-weight:400;white-space:nowrap}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0}
.sub{color:var(--mut);margin:0 0 14px;font-size:13px}
.legend{color:var(--mut);font-size:11px;margin-top:8px}.note{color:var(--mut);font-size:12px;margin-top:14px;border-top:1px solid var(--line);padding-top:10px}
.footer{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:center}
.footer .path{color:var(--mut);font-size:12px}.footer .work{color:var(--txt);font-size:12px;font-style:italic;max-width:62%}
tr.top{background:rgba(210,153,34,0.18);border-left:3px solid #d29922}
"""
    return f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>{css}</style></head><body><div class="wrap">{body}</div></body></html>\n'


def main():  # noqa: PLR0915
    ap = argparse.ArgumentParser(
        description="OpenRouter free models ranked by composite intelligence (AA Index + LMArena ELO, z-scored)"
    )
    ap.add_argument("--offline", action="store_true", help="use cached data/raw/ snapshots, no network")
    ap.add_argument("--fetch", action="store_true", help="save raw snapshots to data/raw/")
    ap.add_argument("--check", action="store_true", help="dry-run: fetch + print, no file writes")
    ap.add_argument("--json", action="store_true", help="write data/free_models.json")
    ap.add_argument("--html", action="store_true", help="write outputs/free_models.html")
    ap.add_argument("--verbose", action="store_true", help="verbose fetch logging")
    args = ap.parse_args()
    verbose = bool(args.verbose)
    offline = bool(args.offline)
    do_fetch = bool(args.fetch and not offline)
    do_write = not bool(args.check)

    DATA.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    print("Free models (OpenRouter + OpenCode) \u2014 composite intelligence")
    print(f"  date: {dt.datetime.now(dt.timezone.utc).isoformat()}")
    print(f"  mode: {'offline' if offline else 'live'}" + (" +fetch" if do_fetch else "") + (" check-only" if args.check else ""))

    # ---- 1. OpenRouter ----
    or_map = {}
    if offline:
        snap = pick_latest_raw("openrouter_models")
        if not snap:
            print("  ERROR: --offline but no data/raw/openrouter_models*.json found; run without --offline first.", file=sys.stderr)
            sys.exit(2)
        try:
            j = json.loads(snap.read_text(errors="replace"))
        except Exception as e:  # noqa: BLE001  (bad snapshot — report and continue with empty map)
            print(f"  WARN offline OR snapshot bad: {e}", file=sys.stderr)
            j = None
        print(f"  offline OR snapshot: {snap.name}")
        or_map = ogc.parse_openrouter(j, verbose=verbose) if j is not None else {}
    else:
        body = ogc.fetch(OPENROUTER_API, verbose=verbose)
        if body:
            try:
                j = json.loads(body)
                if do_fetch:
                    s = RAW / f"openrouter_models_{dt.date.today().isoformat().replace('-', '')}.json"
                    s.write_text(json.dumps(j, indent=2))
                    print(f"  saved OR -> {s.relative_to(ROOT)} ({len(body)} bytes)")
                or_map = ogc.parse_openrouter(j, verbose=verbose)
            except Exception as e:  # noqa: BLE001
                print(f"  WARN OR json: {e}", file=sys.stderr)
        else:
            print("  WARN OR fetch failed", file=sys.stderr)

    free_recs = [rec for rec in or_map.values() if is_free_model(rec)]
    for r in free_recs:
        r["_source"] = "OR"
    # Stable id order before composite sort — alphabetical within provider
    free_recs.sort(key=lambda r: (r.get("id", "")))
    print(f"  catalog: {len(or_map)} models in OR; free: {len(free_recs)}")

    # ---- 1b. OpenCode free models (ox-alpha-free etc.) ----
    oc_free_ids: list[str] = []
    oc_ids: list[str] = []
    if offline:
        snap = pick_latest_raw("opencode_go_models")
        if snap:
            try:
                j2 = json.loads(snap.read_text(errors="replace"))
                oc_ids = [m.get("id") for m in j2.get("data", []) if m.get("id")]
                print(f"  offline OC snapshot: {snap.name} ({len(oc_ids)} models)")
            except Exception as e:  # noqa: BLE001
                print(f"  WARN offline OC snapshot bad: {e}", file=sys.stderr)
                oc_ids = list(ogc.FALLBACK_PRICING.keys())
        else:
            oc_ids = list(ogc.FALLBACK_PRICING.keys())
            print("  OC: no offline snapshot available, using fallback catalog")
    else:
        body_oc = ogc.fetch(OCGO_API, verbose=verbose)
        if body_oc:
            try:
                j2 = json.loads(body_oc)
                if do_fetch:
                    s2 = RAW / f"opencode_go_models_{dt.date.today().isoformat().replace('-', '')}.json"
                    s2.write_text(json.dumps(j2, indent=2))
                    print(f"  saved OC -> {s2.relative_to(ROOT)} ({len(body_oc)} bytes)")
                oc_ids = [m.get("id") for m in j2.get("data", []) if m.get("id")]
                print(f"  OC catalog: {len(oc_ids)} models")
            except Exception as e:  # noqa: BLE001
                print(f"  WARN OC json: {e}", file=sys.stderr)
                oc_ids = list(ogc.FALLBACK_PRICING.keys())
        else:
            print("  WARN OC fetch failed, using fallback", file=sys.stderr)
            oc_ids = list(ogc.FALLBACK_PRICING.keys())
    for oid in oc_ids:
        pr = ogc.FALLBACK_PRICING.get(oid)
        is_free = (pr is not None and pr.get("usage") is None) or oid.lower().endswith("-free") or "free" in oid.lower()
        if is_free:
            oc_free_ids.append(oid)
    or_norms = {ogc.norm_id(base_id(r["id"])) for r in free_recs}
    oc_added = 0
    for oid in oc_free_ids:
        norm = ogc.norm_id(base_id(oid))
        if norm in or_norms:
            continue
        rec = {"id": oid, "context_length": None, "pricing": {"prompt": "0", "completion": "0"}, "_source": "OC"}
        free_recs.append(rec)
        or_norms.add(norm)
        oc_added += 1
    if oc_free_ids:
        print(f"  OpenCode free: {len(oc_free_ids)} found ({', '.join(oc_free_ids)}), {oc_added} added new (others already in OR)")
    else:
        print("  OpenCode free: none found")
    free_recs.sort(key=lambda r: (r.get("id", "")))
    print(f"  free total: {len(free_recs)} (OR {len(free_recs)-oc_added} + OC {oc_added})")

    # ---- 2. AA ----
    aa_map = {}
    if offline:
        snap = pick_latest_raw("artificial_analysis")
        if snap:
            try:
                aa_map = ogc.parse_aa(snap.read_text(errors="ignore"), verbose=verbose)
            except Exception as e:  # noqa: BLE001
                print(f"  WARN AA offline parse: {e}", file=sys.stderr)
            print(f"  AA: {len(aa_map)} entries ({snap.name})")
        else:
            print("  AA: no offline snapshot available")
    else:
        body = ogc.fetch(AA_URL, verbose=verbose)
        if body:
            html_txt = body.decode(errors="ignore")
            if do_fetch:
                s = RAW / f"artificial_analysis_{dt.date.today().isoformat().replace('-', '')}.html"
                s.write_text(html_txt)
                print(f"  saved AA -> {s.relative_to(ROOT)} ({len(html_txt)} bytes)")
            aa_map = ogc.parse_aa(html_txt, verbose=verbose)
            print(f"  AA: {len(aa_map)} models")
        else:
            print("  WARN AA fetch failed", file=sys.stderr)

    # ---- 3. LMArena ----
    lm_map = {}
    if offline:
        snap = pick_latest_raw("lmarena")
        if snap:
            try:
                lm_map = ogc.parse_lmarena(snap.read_text(errors="ignore"), verbose=verbose)
            except Exception as e:  # noqa: BLE001
                print(f"  WARN LMArena offline parse: {e}", file=sys.stderr)
            print(f"  LMArena: {len(lm_map)} entries ({snap.name})")
        else:
            print("  LMArena: no offline snapshot available")
    else:
        body = ogc.fetch(LMARENA_URL, verbose=verbose)
        if body:
            html_txt = body.decode(errors="ignore")
            if do_fetch:
                s = RAW / f"lmarena_{dt.date.today().isoformat().replace('-', '')}.html"
                s.write_text(html_txt)
                print(f"  saved LMArena -> {s.relative_to(ROOT)} ({len(html_txt)} bytes)")
            lm_map = ogc.parse_lmarena(html_txt, verbose=verbose)
            print(f"  LMArena: {len(lm_map)} entries")
        else:
            print("  WARN LMArena fetch failed", file=sys.stderr)

    # ---- 4. merge: attach intelligence to each free model ----
    rows = []
    for rec in free_recs:
        oid = rec.get("id", "") or ""
        b_id = base_id(oid)
        # AA lookup — provider-stripped base is the canonical slug; try it first
        aa_rec = ogc.find_aa_for_ocgo(b_id, aa_map) or ogc.find_aa_for_ocgo(oid, aa_map) if aa_map else None
        lm_rec = ogc.find_lm_for_ocgo(b_id, lm_map) or ogc.find_lm_for_ocgo(oid, lm_map) if lm_map else None

        aa_int = aa_rec.get("intelligenceIndex") if aa_rec and aa_rec.get("intelligenceIndex") is not None else None
        aa_cod = aa_rec.get("codingIndex") if aa_rec else None
        aa_age = aa_rec.get("agenticIndex") if aa_rec else None
        aa_tps = aa_rec.get("medianOutputTokensPerSecond") if aa_rec else None
        aa_ctx = aa_rec.get("contextWindowTokens") if aa_rec else None
        aa_slug = aa_rec.get("slug") if aa_rec else None

        lm_elo = lm_rec.get("elo") if lm_rec else None
        lm_rank = lm_rec.get("rank") if lm_rec else None
        lm_votes = lm_rec.get("votes") if lm_rec else None

        or_ctx = rec.get("context_length")
        src = rec.get("_source", "OR")
        if src == "OC":
            provider = "opencode"
        else:
            provider = oid.split("/")[0] if "/" in oid else (oid.split("-")[0] if "-" in oid else "\u2014")

        coverage = []
        if aa_int is not None:
            coverage.append("AA")
        if lm_elo is not None:
            coverage.append("LM")
        if not coverage:
            coverage = ["\u2014"]

        # provider column already shows it — strip "provider/" prefix from display
        display_short = b_id.split("/")[-1] if "/" in b_id else b_id
        rows.append(
            {
                "model_id": oid,
                "display": display_short,
                "display_full": b_id,
                "provider": provider,
                "source": src.lower(),  # "or" / "oc" for the new src column

                "benchmarks": {
                    "aa_slug": aa_slug,
                    "aa_intelligence": aa_int,
                    "aa_coding": aa_cod,
                    "aa_agentic": aa_age,
                    "aa_median_tps": aa_tps,
                    "aa_context": aa_ctx,
                    "lmarena_rank": lm_rank,
                    "lmarena_elo": lm_elo,
                    "lmarena_votes": lm_votes,
                    "openrouter_context": or_ctx,
                },
                "coverage": coverage,
            }
        )

    # ---- 5. normalized composite — mean of available z-scores ----
    aa_vals = [r["benchmarks"]["aa_intelligence"] for r in rows if r["benchmarks"]["aa_intelligence"] is not None]
    lm_vals = [r["benchmarks"]["lmarena_elo"] for r in rows if r["benchmarks"]["lmarena_elo"] is not None]

    aa_mean = statistics.fmean(aa_vals) if aa_vals else None
    aa_std = statistics.pstdev(aa_vals) if len(aa_vals) > 1 else (0.0 if aa_vals else None)
    lm_mean = statistics.fmean(lm_vals) if lm_vals else None
    lm_std = statistics.pstdev(lm_vals) if len(lm_vals) > 1 else (0.0 if lm_vals else None)

    if aa_vals:
        print(f"  AA Intelligence across {len(aa_vals)} free models: mean {aa_mean:.1f}  std {aa_std:.2f}")
    if lm_vals:
        print(f"  LMArena ELO across {len(lm_vals)} free models: mean {lm_mean:.1f}  std {lm_std:.2f}")
    if not aa_vals and not lm_vals:
        print("  Note: no free model found on AA or LMArena — composites will be \u2014", file=sys.stderr)
    if not aa_vals and not lm_vals:
        print("  OpenRouter has no public bulk intelligence metric (per this repo's finding) — composite falls back to ordering by OR context.", file=sys.stderr)

    for r in rows:
        zs = []
        a = r["benchmarks"]["aa_intelligence"]
        if a is not None and aa_std is not None and aa_std > 0:
            zs.append((a - aa_mean) / aa_std)  # type: ignore[operator]
        elif a is not None and aa_std == 0.0:
            zs.append(0.0)
        e = r["benchmarks"]["lmarena_elo"]
        if e is not None and lm_std is not None and lm_std > 0:
            zs.append((e - lm_mean) / lm_std)  # type: ignore[operator]
        elif e is not None and lm_std == 0.0:
            zs.append(0.0)
        r["composite"] = round(statistics.fmean(zs), 3) if zs else None

    # Sort: composite desc, then AA, then LM, then id. None composites last.
    def comp_key(r):
        c = r.get("composite")
        # largest composite → most negative key so it sorts first
        k_c = -(c) if isinstance(c, (int, float)) else 1e9  # None = huge key → last
        a = r["benchmarks"]["aa_intelligence"]
        k_a = -(a) if isinstance(a, (int, float)) else 1e9
        e = r["benchmarks"]["lmarena_elo"]
        k_e = -(e) if isinstance(e, (int, float)) else 1e9
        return (k_c, k_a, k_e, r["model_id"])

    rows_sorted = sorted(rows, key=comp_key)
    n_aa = sum(1 for r in rows if r["benchmarks"]["aa_intelligence"] is not None)
    n_lm = sum(1 for r in rows if r["benchmarks"]["lmarena_elo"] is not None)

    # ---- 6. console table (always, the default output) ----
    print("\n" + "=" * 114)
    print(f"{'#':<4} {'model':<46} {'provider':<16} {'src':<3} {'AA':>6} {'LMelo':>7} {'comp':>7} {'coverage':<10} {'ctx':>7}")
    print("-" * 114)
    for i, r in enumerate(rows_sorted, 1):
        b = r["benchmarks"]
        aa_s = f"{b['aa_intelligence']:.1f}" if isinstance(b["aa_intelligence"], (int, float)) else "\u2014"
        lm_s = f"{b['lmarena_elo']:.0f}" if isinstance(b["lmarena_elo"], (int, float)) else "\u2014"
        comp_val = r.get("composite")
        comp_s = f"{comp_val:.2f}" if isinstance(comp_val, (int, float)) else "\u2014"
        cov_s = "\u00b7".join(r["coverage"])
        ctx_val = b["openrouter_context"]
        ctx_s = f"{ctx_val // 1000}k" if isinstance(ctx_val, (int, float)) else "\u2014"
        src_raw = r.get("source", "or")
        src_pad = f"{src_raw:<3}"
        # color src for visibility — pad first so ANSI doesn't shift columns
        if src_raw == "oc":
            src_pad = f"\033[32m{src_pad}\033[0m"  # green for opencode
        else:
            src_pad = f"\033[36m{src_pad}\033[0m"  # cyan for openrouter
        # pad first, then wrap with ANSI — otherwise escape bytes count toward :<46 width and the top row shifts left
        name_pad = f"{r['display']:<46}"
        if i == 1 and isinstance(comp_val, (int, float)):
            name_pad = f"\033[1;35m{name_pad}\033[0m"
        print(f"{i:<4} {name_pad} {r['provider']:<16} {src_pad} {aa_s:>6} {lm_s:>7} {comp_s:>7} {cov_s:<10} {ctx_s:>7}")
    print("=" * 114)
    print(
        f"free: {len(rows_sorted)}  |  with AA: {n_aa}  with LM: {n_lm}  |  composite = mean(z(AA Intelligence), z(LMArena ELO)); \u2014 = not on that leaderboard"
    )

    # ---- 7. file outputs (only when --json/--html and not --check) ----
    if not do_write:
        print("\n(check-only, no files written)")
        return
    if args.json:
        OUT.mkdir(parents=True, exist_ok=True)
        DATA.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "sources": {
                "openrouter_api": OPENROUTER_API,
                "opencode_api": OCGO_API,
                "artificial_analysis": AA_URL,
                "lmarena": LMARENA_URL,
                "note": "free = OpenRouter prompt+completion $0 + OpenCode usage None (ox-alpha-free); composite = mean of per-source z-scores (AA Intelligence Index, LMArena ELO); cross-source scales incomparable; OpenRouter/OpenCode contribute list + context (no public bulk intelligence metric)",
            },
            "n_free": len(rows_sorted),
            "n_with_aa": n_aa,
            "n_with_lm": n_lm,
            "models": rows_sorted,
        }
        p = DATA / "free_models.json"
        p.write_text(json.dumps(payload, indent=2))
        print(f"\nwrote {p.relative_to(ROOT)}")
    if args.html:
        OUT.mkdir(parents=True, exist_ok=True)
        p = OUT / "free_models.html"
        p.write_text(render_html(rows_sorted, n_aa, n_lm))
        print(f"wrote {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
