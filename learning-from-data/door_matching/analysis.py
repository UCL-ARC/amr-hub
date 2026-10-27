import argparse
import re
from pathlib import Path
import pandas as pd

PATTERN = re.compile(r"\b(?:E\d{2})?[A-Z]{2}\d{2,3}[A-Z]?\b", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/data/doors.csv")
    ap.add_argument("--out", default="/outputs/door_matching")
    ap.add_argument("--key-column", default="door_key")
    ap.add_argument("--name-column", default="door_name")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(a.input)
    for c in (a.key_column, a.name_column):
        if c not in df:
            raise SystemExit(f"Missing column: {c}")

    def parse(v):
        m = PATTERN.search(" ".join(str(v).strip().upper().split()))
        return m.group(0).upper() if m else None

    r = pd.DataFrame(
        {
            "door_key": df[a.key_column],
            "door_name": df[a.name_column],
            "matched_code": df[a.name_column].map(parse),
        }
    )
    r["matched"] = r["matched_code"].notna()
    r.to_csv(out / "door_location_map.csv", index=False)
    print(f"Matched {int(r.matched.sum())}/{len(r)} door names")


if __name__ == "__main__":
    main()
