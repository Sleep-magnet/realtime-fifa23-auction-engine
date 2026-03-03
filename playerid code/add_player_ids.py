import csv
import os
import sys

# ── CONFIG ────────────────────────────────────────────────────────────────────
MASTER_CSV = "players_cleaned.csv.csv"   # your master dataset with player_id
# ─────────────────────────────────────────────────────────────────────────────

def load_lookup(master_path):
    lookup = {}
    with open(master_path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row.get('name', '').strip()
            pid  = row.get('player_id', '').strip()
            if name and pid:
                lookup[name] = pid
    print(f"✅ Loaded {len(lookup)} players from master dataset")
    return lookup

def add_ids(squad_path, lookup):
    base     = os.path.splitext(squad_path)[0]
    out_path = base + "_with_ids.csv"

    rows = []
    with open(squad_path, 'r', encoding='utf-8') as f:
        reader    = csv.DictReader(f)
        fieldnames = list(reader.fieldnames) + ['Player ID']
        for row in reader:
            name = row.get('Player Name', '').strip()
            row['Player ID'] = lookup.get(name, 'NOT FOUND')
            rows.append(row)

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    found     = sum(1 for r in rows if r['Player ID'] != 'NOT FOUND')
    not_found = len(rows) - found
    print(f"\n📄 Input:   {squad_path}")
    print(f"💾 Output:  {out_path}")
    print(f"✅ Matched: {found}/{len(rows)} players")
    if not_found:
        print(f"⚠️  Not found ({not_found}):")
        for r in rows:
            if r['Player ID'] == 'NOT FOUND':
                print(f"   - {r['Player Name']}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not os.path.exists(MASTER_CSV):
        print(f"❌ Master CSV not found: {MASTER_CSV}")
        print("   Make sure players_cleaned.csv.csv is in the same folder as this script.")
        sys.exit(1)

    lookup = load_lookup(MASTER_CSV)

    # Accept file(s) from command line OR ask for input
    files = sys.argv[1:] if len(sys.argv) > 1 else []

    if not files:
        path = input("\nEnter squad CSV filename (e.g. FoxyRoxy_squad.csv): ").strip()
        files = [path]

    for squad_file in files:
        if not os.path.exists(squad_file):
            print(f"❌ File not found: {squad_file}")
            continue
        add_ids(squad_file, lookup)

    print("\n✅ Done!")