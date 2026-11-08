#!/usr/bin/env python3
"""Publish one PMTiles for Koronus V9 + Furibundus v4, without merging Foundry runtime.

Authoritative old Koronus source: koronus/v9/map-payload.json (unmodified).
Authoritative detailed source: koronus/furibundus/v4/furibundus_v4_star_center.pmtiles.
Derived archive: data/map-packages/koronus.pmtiles (reproducible, exactly 283 tiles).
"""
import base64
import gzip
import hashlib
import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
from merge_pmtiles import merge_pmtiles, inspect_archive, EXPECTED_BASE_SHA256, EXPECTED_DETAIL_SHA256

ROOT=Path(__file__).resolve().parents[3]
V9=ROOT/'koronus/v9/map-payload.json'
DETAIL=ROOT/'koronus/furibundus/v4/furibundus_v4_star_center.pmtiles'
OUTPUT=ROOT/'release'
TARGET='data/map-packages/koronus.pmtiles'
CATALOG='data/city-packages/koronus.json'
SOURCE_COMMIT='a7bce8b0c0a007f7e0702ca86e0cfa3c0ce997af'
COMBINED_SHA256='11d2862209f298e6fa1b012de011e090ff25e4251ec6774cc53a31bea13ab6fb'
COMBINED_BYTES=640712
RUNTIME_PR=501

def sha(blob):return hashlib.sha256(blob).hexdigest()

def main():
    source=json.loads(V9.read_text(encoding='utf-8'))
    assert source['sourceCommit']==SOURCE_COMMIT
    raw={path:base64.b64decode(b64,validate=False) for path,b64 in source['files'].items()}
    assert len(raw)==15 and TARGET in raw and CATALOG in raw
    assert all(name.startswith('data/') and '..' not in Path(name).parts for name in raw)
    city_original=json.loads(raw[CATALOG]);entry=city_original['cities'][0]
    assert entry['cityId']=='koronus' and entry['seedKml']['version']==15
    assert len(raw[TARGET])==entry['expectedBytes']==1501 and sha(raw[TARGET])==entry['expectedSha256']==EXPECTED_BASE_SHA256
    expected={TARGET,CATALOG,'data/city-markers/koronus-screaming-vortex-v8.geojson','data/map-packages/koronus/vortex.json',entry['seedKml']['path'],*entry['seedKml']['additionalPaths']}
    assert set(raw)==expected,'original V9 payload file-contract mismatch'
    for name,contents in raw.items():
        if name.endswith('.kml'):ET.fromstring(contents)
    vortex=json.loads(raw['data/map-packages/koronus/vortex.json'])
    assert vortex['schemaVersion']==1 and vortex['regionMinZoom']==5
    sites=json.loads(raw['data/city-markers/koronus-screaming-vortex-v8.geojson'])['features']
    assert len(sites)==46 and len({s['id'] for s in sites})==46
    detail=DETAIL.read_bytes()
    assert len(detail)==639310 and sha(detail)==EXPECTED_DETAIL_SHA256
    original_info=inspect_archive(raw[TARGET]);detail_info=inspect_archive(detail)
    merged=merge_pmtiles(raw[TARGET],detail)
    assert len(merged)==COMBINED_BYTES and sha(merged)==COMBINED_SHA256
    unified_info=inspect_archive(merged)
    assert unified_info['tile_count']==283
    assert unified_info['header']['min_zoom']==0 and unified_info['header']['max_zoom']==16
    assert len(unified_info['metadata']['vector_layers'])==26
    for input_info in (original_info,detail_info):
        assert all(unified_info['tiles'][tid]==blob for tid,blob in input_info['tiles'].items())
    updated=json.loads(raw[CATALOG]);city=updated['cities'][0]
    city.update({'packageVersion':'2026.11.09-1','dataRevision':'koronus-v9-furibundus-unified-v1',
                 'storageFileName':'koronus-20261109-11d28622.pmtiles.glb',
                 'expectedBytes':COMBINED_BYTES,'expectedSha256':COMBINED_SHA256})
    files=dict(raw)
    files[TARGET]=merged
    files[CATALOG]=(json.dumps(updated,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
    assert len(files)==15 and files[TARGET]==merged
    assert all(files[name]==contents for name,contents in raw.items() if name not in (TARGET,CATALOG))
    provenance={
        'schemaVersion':1,'scope':'Koronus V9 + Furibundus v4 as ONE PMTiles; map data only',
        'sourceCommit':SOURCE_COMMIT,'previousPublishedRelease':'koronus-v9-furibundus-rc-20261108',
        'singlePMTiles':True,'requiresICM':{'pr':RUNTIME_PR,'runtime':'shared protomaps source','foundry':'NOT VERIFIED'},
        'inputPMTiles':[{'name':'Koronus V9','bytes':len(raw[TARGET]),'sha256':EXPECTED_BASE_SHA256,'tileCount':1},
                        {'name':'Furibundus v4','bytes':len(detail),'sha256':EXPECTED_DETAIL_SHA256,'tileCount':282}],
        'result':{'path':TARGET,'bytes':len(merged),'sha256':COMBINED_SHA256,'tileCount':283,'layerCount':26,
                  'zoom':[0,16], 'sourceTilePayloadsPreserved':True,'centerOfStar':[11.328774,1.627352],
                  'artScale':'experimental'},
        'sourceFiles':[{'path':name,'bytes':len(data),'sha256':sha(data)} for name,data in sorted(raw.items())],
        'outputFiles':[{'path':name,'bytes':len(data),'sha256':sha(data)} for name,data in sorted(files.items())]
    }
    files['PROVENANCE.json']=(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    files['README.txt']=(
        'Koronus V9 + Furibundus v4 UNIFIED MAP PMTiles (pre-release). No Foundry module or external styles.\n'
        'Exactly one PMTiles file: data/map-packages/koronus.pmtiles, containing the original Koronus blank base and all Furibundus MVT tiles.\n'
        'Other KML, Screaming Vortex geometry, location IDs and authored routes are unchanged.\n'
        'To install: extract contents of the koronus-v9/ folder into Data/modules/interactive-city-map/.\n'
        'Requires ICM PR #501 compatible with unified PMTiles/shared protomaps source (do not use earlier separate-source commits).\n'
        'Original old PMTiles must be replaced, not installed alongside a separate Furibundus PMTiles.\n'
        'Furibundus appears at zoom >=11; route masking and marker visibility require the matching ICM runtime.\n'
        'Do not re-import saved KML objects into an existing world. Reload clients and verify live Foundry rendering.\n'
        'The Furibundus artwork uses an experimental non-astronomical map scale.\n').encode('utf-8')
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT/'koronus.pmtiles').write_bytes(merged)
    (OUTPUT/'PROVENANCE.json').write_bytes(files['PROVENANCE.json'])
    zipped=OUTPUT/'koronus-v9-unified-map.zip'
    with ZipFile(zipped,'w',ZIP_DEFLATED,compresslevel=9) as z:
        for name,blob in sorted(files.items()):
            info=ZipInfo('koronus-v9/'+name,date_time=(2026,11,9,0,0,0));info.compress_type=ZIP_DEFLATED
            z.writestr(info,blob,compress_type=ZIP_DEFLATED,compresslevel=9)
    with ZipFile(zipped) as z:
        assert z.testzip() is None and len(z.namelist())==17
        assert len([n for n in z.namelist() if n.endswith('.pmtiles')])==1
        assert z.read('koronus-v9/'+TARGET)==merged
        assert z.read('koronus-v9/'+CATALOG)==files[CATALOG]
        assert not any(n.endswith(('.mjs','module.json')) for n in z.namelist())
    (OUTPUT/'SHA256SUMS.txt').write_text(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in sorted(OUTPUT.iterdir()) if p.is_file() and p.name!='SHA256SUMS.txt'),encoding='utf-8')
    print(json.dumps({'status':'PASS: static only','inputFiles':15,'releaseZipEntries':17,
       'PMTiles':'one','bytes':len(merged),'sha256':COMBINED_SHA256,'mvtTiles':283,
       'unchangedNonPMTilesFiles':13,'foundry':'NOT VERIFIED','releaseFiles':sorted(p.name for p in OUTPUT.iterdir())},indent=2))

if __name__=='__main__':main()