#!/usr/bin/env python3
"""Build independently downloadable Koronus PMTiles using Chicago-style fixed-size parts.

Source: byte-pinned v0.2.140-rc.1 ICM release. The original vector PMTiles is
preserved; the SoI and Koronus map-owned resources become a separate PMTiles v3
binary asset archive (not a vector layer). Both have SHA256-protected manifests.
"""
import argparse
import gzip
import hashlib
import json
import struct
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

SOURCE_TAG = "v0.2.140-rc.1"
SOURCE_COMMIT = "2f7413498af25161e765ec803073261b880ab229"
SOURCE_BYTES = 129347313
SOURCE_SHA = "43e436b6325eceee2dcb75a59e9385ac0535393747f2e75382a6af19aefcf0b2"
BASE_VECTOR = "data/map-packages/koronus.pmtiles"
VECTOR_SIZE = 1964280
VECTOR_SHA = "d94f0ac84c187fc43711674a68a6bd376013e7bbc1d6086c27ecc603420a7dc7"
SOURCE_RELEASE_TAG = "koronus-downloadable-v1-src"
SOURCE_PROVENANCE_NAME = "SOURCE_PROVENANCE.json"
PART_SIZE = 45 * 1024 * 1024
VIRTUAL_Z = 12
PREFIX = "interactive-city-map/"
MAX_RESOURCES = 2048
MAX_RESOURCE_BYTES = 200 * 1024 * 1024
REQUIRED = (
    "data/soi/systems-v1/manifest.json",
    "data/soi/canonical-v1/manifest.json",
    "data/soi/continental-feather-v1.json",
    "data/soi/footfall-v2/footfall-30deg.svg",
    "data/soi/furibundus-rock-belt-v1/rocks.webp",
    "data/map-packages/koronus/vortex.json",
    "data/city-markers/koronus.kml",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def compact_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def varint(n):
    if n < 0:
        raise ValueError("negative varint")
    out = bytearray()
    while n >= 128:
        out.append((n & 127) | 128)
        n >>= 7
    out.append(n)
    return bytes(out)


def unvarint(buf, index):
    value, shift = 0, 0
    for _ in range(10):
        if index >= len(buf):
            raise ValueError("truncated directory")
        v = buf[index]
        index += 1
        value |= (v & 127) << shift
        if v < 128:
            return value, index
        shift += 7
    raise ValueError("malformed varint")


def hilbert(z, x, y):
    if not (0 <= z <= 15 and 0 <= x < 2**z and 0 <= y < 2**z):
        raise ValueError("virtual tile coordinate out of range")
    d = 0
    s = 1 << (z - 1)
    while s:
        rx = int(bool(x & s))
        ry = int(bool(y & s))
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        s //= 2
    return d


def tileid(z, x, y):
    return (4**z - 1) // 3 + hilbert(z, x, y)


def map_owned(path):
    return (path.startswith("data/soi/") or
            (path.startswith("data/city-markers/koronus") and
             path.endswith((".kml", ".geojson"))) or
            path == "data/map-packages/koronus/vortex.json")


def read_release(archive_path, expected_size=SOURCE_BYTES, expected_sha=SOURCE_SHA,
                 vector_size=VECTOR_SIZE, vector_sha=VECTOR_SHA):
    if archive_path.stat().st_size != expected_size:
        raise ValueError("source release size mismatch")
    if sha(archive_path.read_bytes()) != expected_sha:
        raise ValueError("source release SHA mismatch")
    vector, files = None, {}
    with ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Corrupted source release")
        for item in archive.infolist():
            if item.is_dir():
                continue
            name = item.filename
            if not name.startswith(PREFIX):
                raise ValueError("Invalid source archive root")
            rel = name[len(PREFIX):]
            if not rel or rel.startswith("/") or "\\" in rel or ".." in PurePosixPath(rel).parts:
                raise ValueError("Unsafe source archive path: " + rel)
            if rel == BASE_VECTOR:
                if vector is not None:
                    raise ValueError("Duplicate vector PMTiles")
                vector = archive.read(item)
            elif map_owned(rel):
                if rel in files:
                    raise ValueError("Duplicate resource file: " + rel)
                files[rel] = archive.read(item)
    if vector is None or len(vector) != vector_size or sha(vector) != vector_sha:
        raise ValueError("Incorrect source vector PMTiles size/SHA")
    if not vector.startswith(b"PMTiles\x03"):
        raise ValueError("Incorrect source vector PMTiles magic")
    if not 1 <= len(files) <= MAX_RESOURCES:
        raise ValueError("Unexpected count of map-owned resources")
    missing = set(REQUIRED) - files.keys()
    if missing:
        raise ValueError("Missing source resources: " + ", ".join(sorted(missing)))
    if sum(map(len, files.values())) > MAX_RESOURCE_BYTES:
        raise ValueError("Resource payload exceeds safety budget")
    return vector, files


def make_directory(entries):
    out = bytearray(varint(len(entries)))
    prev_id = 0
    for tid, _, _ in entries:
        out += varint(tid - prev_id)
        prev_id = tid
    for _ in entries:
        out += varint(1)
    for _, _, content in entries:
        out += varint(len(content))
    for i in range(len(entries)):
        out += varint(1 if i == 0 else 0)
    return bytes(out)


def build_asset_pmtiles(files, source_sha=SOURCE_SHA, vector_sha=VECTOR_SHA):
    if not 1 <= len(files) <= MAX_RESOURCES:
        raise ValueError("Invalid resource count")
    entries, index = [], {}
    for i, path in enumerate(sorted(files)):
        data = files[path]
        if not data:
            raise ValueError("Empty map resource: " + path)
        tid = tileid(VIRTUAL_Z, i, 0)
        entries.append((tid, path, data))
        index[path] = {"z": VIRTUAL_Z, "x": i, "y": 0,
                       "bytes": len(data), "sha256": sha(data)}
    entries.sort(key=lambda row: row[0])
    tile_data = b"".join(item[2] for item in entries)
    if len(tile_data) > MAX_RESOURCE_BYTES:
        raise ValueError("Asset PMTiles payload too large")
    directory = gzip.compress(make_directory(entries), mtime=0)
    metadata = gzip.compress(compact_json({
        "schemaVersion": 1,
        "kind": "icm-koronus-binary-resources",
        "tileCoordinates": "z12/x=lexical-resource-index/y=0",
        "sourceRelease": SOURCE_TAG,
        "sourceArchiveSHA256": source_sha,
        "vectorPMTilesSHA256": vector_sha,
        "assets": index
    }), mtime=0)
    if len(directory) > 16384:
        raise ValueError("Resource directory exceeds PMTiles root capacity")
    off_root = 127
    off_meta = off_root + len(directory)
    off_tile = off_meta + len(metadata)
    header = bytearray(127)
    header[:8] = b"PMTiles\x03"
    fields = ((8, off_root), (16, len(directory)), (24, off_meta),
              (32, len(metadata)), (40, off_tile), (48, 0),
              (56, off_tile), (64, len(tile_data)),
              (72, len(entries)), (80, len(entries)), (88, len(entries)))
    for offset, value in fields:
        struct.pack_into("<Q", header, offset, value)
    header[96] = 1  # clustered PMTiles
    header[97] = 2  # gzip internal directory and metadata
    header[98] = 1  # no tile compression: preserve exact source bytes
    header[99] = 0  # tile type UNKNOWN; this is NOT MapLibre MVT
    header[100] = VIRTUAL_Z
    header[101] = VIRTUAL_Z
    struct.pack_into("<iiii", header, 102, -1800000000, -850000000,
                     1800000000, 850000000)
    header[118] = VIRTUAL_Z
    return bytes(header) + directory + metadata + tile_data


def verify_asset_pmtiles(raw, files=None):
    if len(raw) < 127 or raw[:8] != b"PMTiles\x03":
        raise ValueError("Bad resource PMTiles magic")
    positions = [struct.unpack_from("<Q", raw, i)[0] for i in range(8, 96, 8)]
    root, rlen, meta, mlen, leaf, llen, tile, tlen, addressed, count, contents = positions
    if root != 127 or meta != root + rlen or leaf != tile or llen != 0 or tile != meta + mlen:
        raise ValueError("Incorrect resource PMTiles layout")
    if tile + tlen != len(raw) or count != contents or count != addressed:
        raise ValueError("Corrupt resource PMTiles byte count")
    if raw[96:102] != bytes((1, 2, 1, 0, VIRTUAL_Z, VIRTUAL_Z)):
        raise ValueError("Incorrect PMTiles header flags")
    meta_json = json.loads(gzip.decompress(raw[meta:meta + mlen]))
    if (meta_json.get("schemaVersion") != 1 or
            meta_json.get("kind") != "icm-koronus-binary-resources" or
            not isinstance(meta_json.get("assets"), dict) or
            not 1 <= len(meta_json["assets"]) <= MAX_RESOURCES or
            (files is not None and set(meta_json["assets"]) != set(files))):
        raise ValueError("Resource index differs from source")
    directory = gzip.decompress(raw[root:root + rlen])
    p = 0
    n, p = unvarint(directory, p)
    if n != count or n != len(meta_json["assets"]):
        raise ValueError("Directory entry count mismatch")
    ids, current = [], 0
    for _ in range(n):
        v, p = unvarint(directory, p)
        current += v
        ids.append(current)
    runs, lengths, offsets = [], [], []
    for bucket in (runs, lengths):
        for _ in range(n):
            v, p = unvarint(directory, p)
            bucket.append(v)
    for i in range(n):
        v, p = unvarint(directory, p)
        offsets.append(v - 1 if v else offsets[i - 1] + lengths[i - 1])
    if p != len(directory) or runs != [1] * n or len(set(ids)) != n:
        raise ValueError("Corrupt resource directory")
    decoded = {tid: raw[tile + offset:tile + offset + length]
               for tid, offset, length in zip(ids, offsets, lengths)}
    mapped_ids = set()
    for file_path, desc in meta_json["assets"].items():
        if not map_owned(file_path) or ".." in PurePosixPath(file_path).parts or "\\" in file_path:
            raise ValueError("Unsafe companion resource path: " + file_path)
        if not isinstance(desc, dict) or desc.get("z") != VIRTUAL_Z or desc.get("y") != 0:
            raise ValueError("Invalid resource tile locator: " + file_path)
        if not isinstance(desc.get("x"), int) or not 0 <= desc["x"] < n:
            raise ValueError("Invalid resource tile x: " + file_path)
        tid = tileid(desc["z"], desc["x"], desc["y"])
        if tid in mapped_ids or tid not in decoded:
            raise ValueError("Duplicate or missing resource tile: " + file_path)
        mapped_ids.add(tid)
        data = decoded[tid]
        if not data or sha(data) != desc.get("sha256") or len(data) != desc.get("bytes"):
            raise ValueError("Resource byte/hash roundtrip failed: " + file_path)
        if files is not None and data != files[file_path]:
            raise ValueError("Resource payload differs from source: " + file_path)
    if mapped_ids != set(decoded) or not set(REQUIRED).issubset(meta_json["assets"]):
        raise ValueError("Companion PMTiles missing required or contains unmapped resources")
    return meta_json



def source_record(logical_name, data):
    return {"name": logical_name, "bytes": len(data), "sha256": sha(data)}


def stage_source(source, out, expected_size=SOURCE_BYTES, expected_sha=SOURCE_SHA,
                 vector_size=VECTOR_SIZE, vector_sha=VECTOR_SHA):
    """Stage only two real PMTiles and their provenance for one-time upload.

    Never place the private ICM ZIP or developer source tree in the public repo.
    """
    vector, assets = read_release(source, expected_size, expected_sha, vector_size, vector_sha)
    resources = build_asset_pmtiles(assets, source_sha=expected_sha, vector_sha=vector_sha)
    verify_asset_pmtiles(resources, assets)
    out.mkdir(parents=True, exist_ok=True)
    paths = {"koronus": out / "koronus.pmtiles",
             "koronusResources": out / "koronus-resources.pmtiles"}
    paths["koronus"].write_bytes(vector)
    paths["koronusResources"].write_bytes(resources)
    provenance = {
        "schemaVersion": 1,
        "kind": "icm-koronus-source-pmtiles",
        "sourceTag": SOURCE_TAG,
        "sourceCommit": SOURCE_COMMIT,
        "sourceArchiveBytes": expected_size,
        "sourceArchiveSHA256": expected_sha,
        "koronus": source_record(paths["koronus"].name, vector),
        "koronusResources": source_record(paths["koronusResources"].name, resources),
        "resourceCount": len(assets),
        "resourceBytes": sum(map(len, assets.values())),
    }
    (out / SOURCE_PROVENANCE_NAME).write_bytes(
        json.dumps(provenance, sort_keys=True, ensure_ascii=False, indent=2).encode() + b"\n"
    )
    names = sorted(("koronus.pmtiles", "koronus-resources.pmtiles", SOURCE_PROVENANCE_NAME))
    (out / "SHA256SUMS.txt").write_text("".join(
        sha((out / name).read_bytes()) + "  " + name + "\n" for name in names),
        encoding="utf-8"
    )
    return provenance


def verify_staged_source(source_dir, expected_size=SOURCE_BYTES,
                         expected_sha=SOURCE_SHA, vector_size=VECTOR_SIZE,
                         vector_sha=VECTOR_SHA):
    """Validate files uploaded to the public source Release, not private access."""
    provenance_path = source_dir / SOURCE_PROVENANCE_NAME
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if (provenance.get("schemaVersion") != 1 or
            provenance.get("kind") != "icm-koronus-source-pmtiles" or
            provenance.get("sourceTag") != SOURCE_TAG or
            provenance.get("sourceCommit") != SOURCE_COMMIT or
            provenance.get("sourceArchiveBytes") != expected_size or
            provenance.get("sourceArchiveSHA256") != expected_sha):
        raise ValueError("Source PMTiles provenance mismatch")
    source_files = ("koronus.pmtiles", "koronus-resources.pmtiles")
    data = {}
    for kind, name in zip(("koronus", "koronusResources"), source_files):
        descriptor = provenance.get(kind)
        item = source_dir / name
        if not item.is_file() or not isinstance(descriptor, dict) or descriptor.get("name") != name:
            raise ValueError("Missing source PMTiles asset: " + name)
        raw = item.read_bytes()
        if len(raw) != descriptor.get("bytes") or sha(raw) != descriptor.get("sha256"):
            raise ValueError("Source PMTiles checksum mismatch: " + name)
        data[kind] = raw
    if len(data["koronus"]) != vector_size or sha(data["koronus"]) != vector_sha:
        raise ValueError("Vector source changed")
    if not data["koronus"].startswith(b"PMTiles\x03"):
        raise ValueError("Vector source PMTiles signature mismatch")
    metadata = verify_asset_pmtiles(data["koronusResources"])
    if (metadata.get("sourceRelease") != SOURCE_TAG or
            metadata.get("sourceArchiveSHA256") != expected_sha or
            metadata.get("vectorPMTilesSHA256") != vector_sha or
            provenance.get("resourceCount") != len(metadata["assets"]) or
            provenance.get("resourceBytes") != sum(e["bytes"] for e in metadata["assets"].values())):
        raise ValueError("Companion source archive binding mismatch")
    sums = source_dir / "SHA256SUMS.txt"
    if sums.exists():
        expected_sums = "".join(
            sha((source_dir / name).read_bytes()) + "  " + name + "\n"
            for name in sorted((*source_files, SOURCE_PROVENANCE_NAME))
        )
        if sums.read_text(encoding="utf-8") != expected_sums:
            raise ValueError("Source release SHA256SUMS mismatch")
    return data["koronus"], data["koronusResources"], provenance


def emit_parts(out, vector, resources, resource_count, resource_bytes,
               expected_sha=SOURCE_SHA, part_size=PART_SIZE):
    out.mkdir(parents=True, exist_ok=True)
    map_info = write_parts(out, "koronus.pmtiles", vector, part_size)
    res_info = write_parts(out, "koronus-resources.pmtiles", resources, part_size)
    payload = {
        "schemaVersion": 1,
        "packageVersion": "2026.11.22-koronus-downloadable-v1",
        "sourceRepository": "messireLeonard/interactive-city-map",
        "sourceTag": SOURCE_TAG,
        "sourceCommit": SOURCE_COMMIT,
        "sourceArchiveSha256": expected_sha,
        "sourcePMTilesRelease": SOURCE_RELEASE_TAG,
        "role": "external-map-assets",
        "rawBaseUrl": "https://raw.githubusercontent.com/messireLeonard/moscow_test/assets/koronus-downloadable-v1/hosted-assets/koronus-v1/",
        "koronus": map_info,
        "koronusResources": res_info,
        "resources": {"count": resource_count, "rawBytes": resource_bytes,
                      "format": "PMTiles v3 binary virtual-tile index"},
        "requiresICMCompanionLoader": True
    }
    (out / "manifest.json").write_bytes(json.dumps(
        payload, sort_keys=True, ensure_ascii=False, indent=2
    ).encode() + b"\n")
    if verify_parts(out, map_info) != vector or verify_parts(out, res_info) != resources:
        raise ValueError("Chunk reassembly corrupted authoritative PMTiles")
    names = sorted(p.name for p in out.iterdir()
                   if p.is_file() and p.name != "SHA256SUMS.txt")
    (out / "SHA256SUMS.txt").write_text("".join(
        sha((out / name).read_bytes()) + "  " + name + "\n" for name in names),
        encoding="utf-8"
    )
    return payload


def build_from_source_release(source_dir, out, part_size=PART_SIZE, **pin_overrides):
    """Chicago-style: split already hosted, verified source PMTiles."""
    vector, resources, provenance = verify_staged_source(source_dir, **pin_overrides)
    return emit_parts(out, vector, resources, provenance["resourceCount"],
                      provenance["resourceBytes"],
                      expected_sha=provenance["sourceArchiveSHA256"], part_size=part_size)


def write_parts(output, logical_name, content, part_size):
    if not 1 <= part_size <= PART_SIZE:
        raise ValueError("Part size outside GitHub-hostable budget")
    parts = []
    for index, offset in enumerate(range(0, len(content), part_size)):
        chunk = content[offset:offset + part_size]
        name = f"{logical_name}.part-{index:02d}"
        (output / name).write_bytes(chunk)
        parts.append({"name": name, "bytes": len(chunk), "sha256": sha(chunk)})
    if not parts:
        raise ValueError("Cannot package an empty archive")
    return {"logicalFileName": logical_name, "expectedBytes": len(content),
            "expectedSha256": sha(content), "parts": parts}


def verify_parts(output, record):
    chunks = []
    for item in record["parts"]:
        name = item["name"]
        if Path(name).name != name or ".." in name:
            raise ValueError("Unsafe part name")
        data = (output / name).read_bytes()
        if len(data) != item["bytes"] or sha(data) != item["sha256"]:
            raise ValueError("Part checksum mismatch: " + name)
        chunks.append(data)
    joined = b"".join(chunks)
    if len(joined) != record["expectedBytes"] or sha(joined) != record["expectedSha256"]:
        raise ValueError("Reassembled package checksum mismatch")
    return joined


def build(source, out, expected_size=SOURCE_BYTES, expected_sha=SOURCE_SHA,
          vector_size=VECTOR_SIZE, vector_sha=VECTOR_SHA, part_size=PART_SIZE):
    base, assets = read_release(
        source, expected_size=expected_size, expected_sha=expected_sha,
        vector_size=vector_size, vector_sha=vector_sha)
    packed = build_asset_pmtiles(assets, source_sha=expected_sha, vector_sha=vector_sha)
    verify_asset_pmtiles(packed, assets)
    return emit_parts(out, base, packed, len(assets), sum(map(len, assets.values())),
                      expected_sha=expected_sha, part_size=part_size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_zip", type=Path, nargs="?",
                        help="Local, SHA-pinned ICM source release ZIP (never uploaded to moscow_test)")
    parser.add_argument("--source-only", action="store_true",
                        help="Produce the two PMTiles for manual upload to moscow_test source Release")
    parser.add_argument("--from-source-release", type=Path,
                        help="Directory containing the two hosted source PMTiles and provenance")
    parser.add_argument("--out", type=Path, default=Path("dist/koronus-v1"))
    args = parser.parse_args()
    if args.from_source_release:
        if args.source_zip or args.source_only:
            parser.error("--from-source-release is exclusive with source_zip and --source-only")
        result = build_from_source_release(args.from_source_release, args.out)
    else:
        if not args.source_zip:
            parser.error("source_zip is required unless --from-source-release is used")
        result = (stage_source(args.source_zip, args.out) if args.source_only else
                  build(args.source_zip, args.out))
    print(json.dumps(result, ensure_ascii=False, indent=2))
