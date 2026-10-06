"""Compact private checkpoints; packing/unpacking runs in HA's executor."""
import base64
import json
import zlib

FORMAT = "zlib-json-v1"


def pack(snapshot):
    records = json.dumps(snapshot["records"], separators=(",", ":")).encode()
    return {**snapshot, "records_format": FORMAT,
            "records": base64.b64encode(zlib.compress(records)).decode()}


def unpack(saved):
    if not saved:
        return saved
    if saved.get("records_format") == FORMAT:
        records = json.loads(zlib.decompress(base64.b64decode(saved["records"])))
        return {k: v for k, v in {**saved, "records": records}.items() if k != "records_format"}
    return saved
