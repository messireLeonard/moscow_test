#!/usr/bin/env python3
"""Immutable map-only Koronus V9 + Furibundus v4 release candidate builder.

Authoritative V9 source: koronus/v9/map-payload.json (unchanged).
New geometry: koronus/furibundus/v4/furibundus_v4_star_center.pmtiles.
Does not include ICM runtime, external style files, or scene mutations.
"""
import base64
import gzip
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

REPO = Path(__file__).resolve().parents[3]
V9 = REPO / 'koronus/v9/map-payload.json'
FURIBUNDUS = REPO / 'koronus/furibundus/v4/furibundus_v4_star_center.pmtiles'
OUTPUT = REPO / 'release'
FURIBUNDUS_TARGET = 'data/map-packages/koronus/furibundus_v4_star_center.pmtiles'
SOURCE_SHA = 'a7bce8b0c0a007f7e0702ca86e0cfa3c0ce997af'
FURIBUNDUS_SHA = '4852e73498ec531736ed7ecb6388f23112b33a66d3907587c18a37d104eba0c7'
RUNTIME_SHA = 'cdacec0e072801c213c3460b0fe05901aec1b7fe'

def sha256(blob):
    return hashlib.sha256(blob).hexdigest()

def verify_furibundus(blob):
    assert len(blob) == 639310 and sha256(blob) == FURIBUNDUS_SHA
    assert blob[:7] == b'PMTiles' and blob[7] == 3
    root_offset, root_length, metadata_offset, metadata_length, leaf_offset, leaf_length, tile_offset, tile_length, tile_addr, tile_entries, tile_blobs = struct.unpack_from('<11Q', blob, 8)
    assert root_offset == 127 and root_offset + root_length == metadata_offset
    assert metadata_offset + metadata_length == tile_offset
    assert tile_offset + tile_length == len(blob)
    assert leaf_offset == leaf_length == 0
    assert tile_addr == tile_entries == tile_blobs == 282
    assert tuple(blob[96:102]) == (1, 2, 2, 1, 9, 16)
    assert tuple(struct.unpack_from('<2i', blob, 119)) == (round(11.328774 * 1e7), round(1.627352 * 1e7))
    metadata = json.loads(gzip.decompress(blob[metadata_offset:metadata_offset + metadata_length]))
    assert len(metadata['vector_layers']) == 26
    assert any(layer['id'] == 'star_disc' for layer in metadata['vector_layers'])
    assert any(layer['id'] == 'asteroid_highlight' for layer in metadata['vector_layers'])
    assert any(layer['id'] == 'system_label' for layer in metadata['vector_layers'])
    return {'bytes': len(blob), 'sha256': sha256(blob), 'tileCount': tile_addr, 'sourceLayers': 26,
            'minZoom': 9, 'maxZoom': 16, 'starAnchor': [11.328774, 1.627352]}

def main():
    payload = json.loads(V9.read_text(encoding='utf-8'))
    assert payload['sourceCommit'] == SOURCE_SHA
    original = {key: base64.b64decode(encoded, validate=False) for key, encoded in payload['files'].items()}
    assert len(original) == 15
    assert all(p.startswith('data/') and '..' not in Path(p).parts and p.endswith(('.json', '.geojson', '.kml', '.pmtiles')) for p in original)
    city = json.loads(original['data/city-packages/koronus.json'])['cities'][0]
    assert city['cityId'] == 'koronus' and city['seedKml']['version'] == 15
    base_pm = original[city['bundledPath']]
    assert len(base_pm) == city['expectedBytes'] == 1501
    assert sha256(base_pm) == city['expectedSha256']
    assert base_pm.startswith(b'PMTiles')
    required = {city['bundledPath'], 'data/city-packages/koronus.json',
                'data/city-markers/koronus-screaming-vortex-v8.geojson',
                'data/map-packages/koronus/vortex.json',
                city['seedKml']['path'], *city['seedKml']['additionalPaths']}
    assert set(original) == required
    for name, contents in original.items():
        if name.endswith('.kml'):
            ET.fromstring(contents)
    sites = json.loads(original['data/city-markers/koronus-screaming-vortex-v8.geojson'])['features']
    assert len(sites) == 46
    assert len({str(f['id']) for f in sites}) == 46
    assert json.loads(original['data/map-packages/koronus/vortex.json'])['schemaVersion'] == 1
    furibundus_bytes = FURIBUNDUS.read_bytes()
    details = verify_furibundus(furibundus_bytes)
    files = {**original, FURIBUNDUS_TARGET: furibundus_bytes}
    assert len(files) == 16

    provenance = {
        'schemaVersion': 1,
        'scope': 'Koronus V9 map-only + Furibundus v4 overlay; no Foundry module',
        'previousCloudRelease': 'koronus-v9-locations-20261030',
        'koronusSourceCommit': SOURCE_SHA,
        'icmRuntime': {'repository': 'messireLeonard/interactive-city-map', 'pr': 501,
                       'testedCommit': RUNTIME_SHA, 'required': True,
                       'releaseStatus': 'DRAFT - NOT MERGED',
                       'foundryRuntime': 'NOT VERIFIED'},
        'furibundus': {**details, 'geography': 'experimental artwork footprint, not astronomical distances',
                       'modulePath': FURIBUNDUS_TARGET, 'embeddedStyleFile': False},
        'baseMapUnchanged': True,
        'sourceFiles': [{'path': name, 'bytes': len(data), 'sha256': sha256(data)}
                        for name, data in sorted(original.items())],
        'addedFiles': [{'path': FURIBUNDUS_TARGET, 'bytes': len(furibundus_bytes), 'sha256': FURIBUNDUS_SHA}]
    }
    files['PROVENANCE.json'] = (json.dumps(provenance, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    files['README.txt'] = (
        'Koronus V9 + Furibundus v4 PRE-RELEASE, map data only. No ICM module or separate MapLibre style.\n'
        'Contains all 15 original V9 map inputs unchanged and one extra PMTiles for Furibundus.\n'
        'Runtime requires ICM PR #501 at commit ' + RUNTIME_SHA + ' or a verified compatible successor.\n'
        'Unzip koronus-v9-furibundus-map.zip into Data/modules/interactive-city-map/ (remove koronus-v9/ archive prefix).\n'
        'The original Koronus PMTiles is unchanged; Furibundus is an additive resource.\n'
        'Global system marker/route visibility switching and inline styles are provided by ICM runtime, not by this archive.\n'
        'Do not replace an installed Foundry scene, duplicate seed KML markers, or blindly reimport saved routes.\n'
        'The Furibundus footprint and star-anchored position are experimental. Foundry visual/performance checks are still open.\n'
    ).encode('utf-8')
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / 'koronus.pmtiles').write_bytes(base_pm)
    (OUTPUT / 'furibundus_v4_star_center.pmtiles').write_bytes(furibundus_bytes)
    (OUTPUT / 'PROVENANCE.json').write_bytes(files['PROVENANCE.json'])
    archive = OUTPUT / 'koronus-v9-furibundus-map.zip'
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED, compresslevel=9) as zipfile:
        for name, blob in sorted(files.items()):
            info = ZipInfo('koronus-v9/' + name, date_time=(2026, 11, 8, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            zipfile.writestr(info, blob, compress_type=ZIP_DEFLATED, compresslevel=9)
    with ZipFile(archive) as zipfile:
        assert zipfile.testzip() is None
        assert len(zipfile.namelist()) == 18
        assert not any(name.endswith(('.mjs', 'module.json')) for name in zipfile.namelist())
        assert zipfile.read('koronus-v9/' + FURIBUNDUS_TARGET) == furibundus_bytes
        assert zipfile.read('koronus-v9/data/map-packages/koronus.pmtiles') == base_pm
    (OUTPUT / 'SHA256SUMS.txt').write_text(''.join(
        sha256(path.read_bytes()) + '  ' + path.name + '\n'
        for path in sorted(OUTPUT.iterdir()) if path.is_file() and path.name != 'SHA256SUMS.txt'
    ), encoding='utf-8')
    print(json.dumps({'status': 'PASS: static only', 'v9FilesPreserved': 15,
                      'addedAsset': FURIBUNDUS_TARGET, 'archiveEntries': 18,
                      'furibundus': details, 'runtime': 'NOT VERIFIED',
                      'releaseFiles': [p.name for p in OUTPUT.iterdir()]}, indent=2))

if __name__ == '__main__':
    main()
