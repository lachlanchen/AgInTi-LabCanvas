#!/usr/bin/env python3
"""Download exact YXRA100 drawings and CAD from the supplier's public catalog."""

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

BASE = "https://a590136ec28bee41f.bj6.agentos-app.net"
ROOT = Path(__file__).resolve().parent
FILES = {
    "msqvn53v651c670c": "YXRA100_standard.step",
    "msqvjiy06f49145d": "YXRA100_100W_servo.step",
    "msqvjjedde4b3504": "YXRA100_57_motor.step",
    "msqvles37005fbba": "YXRA100_optical_specification.pdf",
    "msqvkaq63fe44189": "YXRA100_40_servo_specification.pdf",
    "msqvkhib29847562": "YXRA100_42PUL_specification.pdf",
}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    with urlopen(BASE + "/api/list", timeout=45) as response:
        catalog = json.load(response)
    by_id = {row["id"]: row for row in catalog["files"]}
    records = []
    for file_id, filename in FILES.items():
        info = by_id[file_id]
        target = ROOT / filename
        url = f"{BASE}/api/file/{file_id}/download"
        if not target.exists() or target.stat().st_size != info["size"]:
            with urlopen(url, timeout=90) as response:
                data = response.read()
            if len(data) != info["size"]:
                raise RuntimeError(f"Incorrect size: {filename}")
            target.write_bytes(data)
        records.append({"file": filename, "source": url,
                        "catalog_name": info["name"], "bytes": target.stat().st_size,
                        "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        print(filename, target.stat().st_size, flush=True)
    (ROOT / "downloads.json").write_text(
        json.dumps({"supplier": "Beijing Yixuan Motion Control", "catalog": BASE,
                    "files": records}, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
