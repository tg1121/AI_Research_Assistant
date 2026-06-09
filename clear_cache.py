"""
Cache-busting script — run once after adding \f page markers to the parser.

Clears:
  Local  : marker_output/*.md, outputs/*.json, graph_cache/*.json
  Supabase: parsed_docs table, output_cache table
"""

import os
import glob

# ── Local files ───────────────────────────────────────────────────────────────

DIRS = [
    ("marker_output", "*.md"),
    ("outputs",       "*.json"),
    ("graph_cache",   "*.json"),
]

for folder, pattern in DIRS:
    files = glob.glob(os.path.join(folder, pattern))
    for f in files:
        os.remove(f)
        print(f"  deleted {f}")
    print(f"[local] {folder}/ — removed {len(files)} file(s)")

# ── Supabase ──────────────────────────────────────────────────────────────────

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("\n[supabase] SUPABASE_URL / SUPABASE_KEY not set — skipping remote cache.")
else:
    from supabase import create_client
    sb = create_client(url, key)

    for table in ("parsed_docs", "output_cache"):
        try:
            # delete all rows — Supabase requires a filter; neq on id covers all rows
            sb.table(table).delete().neq("id", -1).execute()
            print(f"[supabase] {table} — cleared")
        except Exception as e:
            # fallback: some tables use different PK names
            try:
                sb.table(table).delete().neq("paper_id", "").execute()
                print(f"[supabase] {table} — cleared (paper_id filter)")
            except Exception as e2:
                print(f"[supabase] {table} — ERROR: {e2}")

print("\nDone. All caches cleared — re-upload papers to regenerate with page markers.")
