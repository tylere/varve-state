"""One-off: move source.coop archives from {product}/{compact-ts}/ to the current
layout {product}/{dataset}/{readable-ts}/ (tylere/varve#10, #15).

Usage: python migrate_source_coop.py copy|delete
  copy   copy each file to its new key, rewriting stac-item.json's id and asset hrefs
  delete delete the old keys, only if every new copy exists with a matching size
"""
import json
import sys

import boto3

OWNER, PRODUCT = "tyler", "varve-data-mirror-test"
PROXY = "https://data.source.coop"
MOVES = [  # (old folder, dataset, new folder)
    ("20261006T220753Z", "epa-national-kml-file", "2026-10-06T22-07-53Z"),
    ("20261013T003609Z", "epa-national-kml-file", "2026-10-13T00-36-09Z"),
    ("20261013T184700Z", "sentinel-2-l2a-13tde-20240731", "2026-10-13T18-47-00Z"),
]

s3 = boto3.client("s3", endpoint_url=PROXY, region_name="us-west-2")


def sizes(prefix: str) -> dict[str, int]:
    """File name → size for the objects directly under prefix/."""
    resp = s3.list_objects_v2(Bucket=OWNER, Prefix=f"{prefix}/")
    return {o["Key"].rsplit("/", 1)[1]: o["Size"] for o in resp.get("Contents", [])}


def copy() -> None:
    for old_ts, slug, new_ts in MOVES:
        old, new = f"{PRODUCT}/{old_ts}", f"{PRODUCT}/{slug}/{new_ts}"
        src = sizes(old)
        if not src:
            sys.exit(f"ERROR nothing at {old}/")
        for name in src:
            body = s3.get_object(Bucket=OWNER, Key=f"{old}/{name}")["Body"].read()
            if name == "stac-item.json":
                item = json.loads(body)
                item["id"] = f"{slug}-{new_ts}"
                for asset in item["assets"].values():
                    asset["href"] = asset["href"].replace(f"{PROXY}/{OWNER}/{old}/", f"{PROXY}/{OWNER}/{new}/")
                s3.put_object(Bucket=OWNER, Key=f"{new}/{name}",
                              Body=json.dumps(item, indent=2).encode(), ContentType="application/json")
            else:
                s3.put_object(Bucket=OWNER, Key=f"{new}/{name}", Body=body)
            print(f"copied {old}/{name} -> {new}/{name}")
        check(old, new)


def check(old: str, new: str) -> None:
    src, dst = sizes(old), sizes(new)
    data_mismatch = {n for n in src if n != "stac-item.json" and dst.get(n) != src[n]}
    if set(src) - set(dst) or data_mismatch:
        sys.exit(f"ERROR {new}/ incomplete: missing {sorted(set(src) - set(dst))}, size mismatch {sorted(data_mismatch)}")
    print(f"verified {new}/ ({len(dst)} files)")


def delete() -> None:
    for old_ts, slug, new_ts in MOVES:
        old, new = f"{PRODUCT}/{old_ts}", f"{PRODUCT}/{slug}/{new_ts}"
        check(old, new)
        for name in sizes(old):
            s3.delete_object(Bucket=OWNER, Key=f"{old}/{name}")
            print(f"deleted {old}/{name}")


if __name__ == "__main__":
    {"copy": copy, "delete": delete}[sys.argv[1]]()
