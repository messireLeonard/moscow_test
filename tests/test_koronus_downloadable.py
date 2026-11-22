import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZIP_STORED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_koronus_downloadable import (
    REQUIRED, BASE_VECTOR, build, sha, tileid,
    build_asset_pmtiles, verify_asset_pmtiles, read_release, verify_parts,
    stage_source, verify_staged_source, build_from_source_release, SOURCE_PROVENANCE_NAME
)


class KoronusChunkTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.source = self.root / "icm.zip"
        self.vector = b"PMTiles\x03" + bytes(120)
        self.assets = {path: ("payload:" + path).encode() for path in REQUIRED}
        self.assets["data/soi/systems-v1/sources/system-raakata--lod2.svg.gz"] = b"\x1f\x8b\x08raw"
        self.assets["data/soi/systems-v1/assets/" + "a" * 64 + ".z"] = bytes(range(255))
        self.repack()

    def repack(self, extra=None, omit=()):
        with ZipFile(self.source, "w", ZIP_STORED) as z:
            z.writestr("interactive-city-map/" + BASE_VECTOR, self.vector)
            for k, v in sorted({**self.assets, **(extra or {})}.items()):
                if k not in omit:
                    z.writestr("interactive-city-map/" + k, v)

    def kwargs(self):
        return {"expected_size": self.source.stat().st_size,
                "expected_sha": sha(self.source.read_bytes()),
                "vector_size": len(self.vector), "vector_sha": sha(self.vector),
                "part_size": 64}

    def test_standard_pmtiles_tileid_hilbert(self):
        self.assertEqual([tileid(1, x, y) for x, y in
                          [(0, 0), (0, 1), (1, 1), (1, 0)]], [1, 2, 3, 4])
        self.assertEqual(len({tileid(12, i, 0) for i in range(1000)}), 1000)

    def test_resource_pmtiles_full_binary_roundtrip(self):
        raw = build_asset_pmtiles(self.assets, source_sha="a"*64, vector_sha="b"*64)
        meta = verify_asset_pmtiles(raw, self.assets)
        self.assertEqual(len(meta["assets"]), len(self.assets))
        self.assertEqual(raw[96:102], bytes((1, 2, 1, 0, 12, 12)))

    def test_chicago_style_chunk_manifest_reassembles_exact_map_and_resources(self):
        out = self.root / "parts"
        report = build(self.source, out, **self.kwargs())
        self.assertEqual(report["schemaVersion"], 1)
        self.assertTrue(report["requiresICMCompanionLoader"])
        self.assertGreater(len(report["koronusResources"]["parts"]), 1)
        self.assertEqual(verify_parts(out, report["koronus"]), self.vector)
        unpacked = verify_parts(out, report["koronusResources"])
        verify_asset_pmtiles(unpacked, self.assets)
        self.assertTrue(all(len((out / p["name"]).read_bytes()) <= 64
                            for p in report["koronusResources"]["parts"]))
        self.assertTrue((out / "manifest.json").is_file())

    def test_repeated_build_is_byte_identical(self):
        out = self.root / "parts"
        a = build(self.source, out, **self.kwargs())
        data = {p.name: p.read_bytes() for p in out.iterdir()}
        b = build(self.source, out, **self.kwargs())
        self.assertEqual(a, b)
        self.assertEqual(data, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_chicago_public_source_release_bootstrap_uses_no_private_zip(self):
        source_out = self.root / "source-release"
        arguments = {k: v for k, v in self.kwargs().items() if k != "part_size"}
        provenance = stage_source(self.source, source_out, **arguments)
        self.assertTrue((source_out / "koronus.pmtiles").is_file())
        self.assertTrue((source_out / "koronus-resources.pmtiles").is_file())
        self.assertTrue((source_out / SOURCE_PROVENANCE_NAME).is_file())
        self.assertFalse(any("icm.zip" in p.name for p in source_out.iterdir()))
        self.assertEqual(provenance["sourceArchiveSHA256"], arguments["expected_sha"])
        vector, resource, validated = verify_staged_source(source_out, **arguments)
        self.assertEqual(vector, self.vector)
        self.assertEqual(provenance, validated)
        verify_asset_pmtiles(resource, self.assets)
        self.source.unlink()
        hosted = self.root / "hosted"
        catalog = build_from_source_release(source_out, hosted, part_size=64, **arguments)
        self.assertEqual(verify_parts(hosted, catalog["koronus"]), vector)
        self.assertEqual(verify_parts(hosted, catalog["koronusResources"]), resource)
        self.assertEqual(catalog["sourcePMTilesRelease"], "koronus-downloadable-v1-src")

    def test_source_release_rejects_corruption_without_any_private_credentials(self):
        staging = self.root / "source"
        args = {k: v for k, v in self.kwargs().items() if k != "part_size"}
        stage_source(self.source, staging, **args)
        resource = staging / "koronus-resources.pmtiles"
        resource.write_bytes(resource.read_bytes()[:-1] + b"z")
        with self.assertRaisesRegex(ValueError, "Source PMTiles checksum mismatch"):
            build_from_source_release(staging, self.root / "hosted", part_size=64, **args)

    def test_source_release_rejects_forged_provenance(self):
        staging = self.root / "source"
        args = {k: v for k, v in self.kwargs().items() if k != "part_size"}
        stage_source(self.source, staging, **args)
        p = staging / SOURCE_PROVENANCE_NAME
        document = __import__("json").loads(p.read_text())
        document["sourceCommit"] = "0" * 40
        p.write_text(__import__("json").dumps(document))
        with self.assertRaisesRegex(ValueError, "Source PMTiles provenance mismatch"):
            verify_staged_source(staging, **args)

    def test_companion_checks_all_binary_tile_hashes_independently(self):
        raw = bytearray(build_asset_pmtiles(self.assets))
        raw[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "Resource byte/hash roundtrip failed"):
            verify_asset_pmtiles(bytes(raw))

    def test_corrupted_downloaded_part_is_rejected(self):
        out = self.root / "parts"
        package = build(self.source, out, **self.kwargs())["koronusResources"]
        first = out / package["parts"][0]["name"]
        first.write_bytes(first.read_bytes()[:-1] + b"Z")
        with self.assertRaisesRegex(ValueError, "Part checksum mismatch"):
            verify_parts(out, package)

    def test_pinned_source_hash_and_missing_assets_rejected(self):
        with self.assertRaisesRegex(ValueError, "source release SHA mismatch"):
            read_release(self.source, **{**{k: v for k, v in self.kwargs().items() if k != "part_size"}, "expected_sha": "0"*64})
        self.repack(omit=("data/soi/canonical-v1/manifest.json",))
        with self.assertRaisesRegex(ValueError, "Missing source resources"):
            build(self.source, self.root / "bad", **self.kwargs())

    def test_omit_developer_data_and_reject_archive_traversal(self):
        self.repack(extra={"tests/test.mjs": b"forbidden", "sources/soi/secret.svg": b"not packaged"})
        _, selected = read_release(self.source, **{
            k: v for k, v in self.kwargs().items() if k != "part_size"
        })
        self.assertEqual(set(selected), set(self.assets))
        self.repack(extra={"data/soi/../forbidden": b"x"})
        with self.assertRaisesRegex(ValueError, "Unsafe source archive path"):
            build(self.source, self.root / "bad", **self.kwargs())


if __name__ == "__main__":
    unittest.main()
