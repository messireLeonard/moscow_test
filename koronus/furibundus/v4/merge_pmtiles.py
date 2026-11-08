#!/usr/bin/env python3
"""Merge the two *authoritative PMTiles tile archives*, preserving each MVT tile byte-for-byte.

Inputs: the 1501-byte Koronus V9 blank vector base and Furibundus v4 star-centered MVT.
A new deterministic PMTiles v3 is generated. No original artifact is mutated.

Usage: python merge_pmtiles.py koronus_original.pmtiles furibundus_v4_star_center.pmtiles koronus_unified.pmtiles
"""
from __future__ import annotations
import gzip
import hashlib
import json
import struct
import sys
from pathlib import Path

EXPECTED_BASE_SHA256 = 'debb686abf8c2ec85d03ea52e30f32a6e190e5dfcd8752ec08f87af7a2130ed1'
EXPECTED_DETAIL_SHA256 = '4852e73498ec531736ed7ecb6388f23112b33a66d3907587c18a37d104eba0c7'


def _varint(buf: bytes, at: int) -> tuple[int,int]:
    value=0
    for shift in range(0,70,7):
        if at>=len(buf): raise ValueError('truncated varint')
        x=buf[at]; at+=1
        value|=(x&127)<<shift
        if x<128:return value,at
    raise ValueError('varint too long')


def _enc(value: int) -> bytes:
    if value<0:raise ValueError('negative varint')
    b=bytearray()
    while value>127:
        b.append((value&127)|128);value>>=7
    b.append(value)
    return bytes(b)


def _directory(data: bytes):
    b=gzip.decompress(data)
    n,at=_varint(b,0)
    ids=[];cur=0
    for _ in range(n):
        x,at=_varint(b,at);cur+=x;ids.append(cur)
    arrays=[]
    for _ in range(3):
        row=[]
        for _ in range(n):
            x,at=_varint(b,at);row.append(x)
        arrays.append(row)
    if at!=len(b):raise ValueError('extra directory bytes')
    runs,lengths,offsets=arrays
    result=[]
    for i in range(n):
        if i and offsets[i]==0:offset= result[-1][1]+result[-1][2]
        else:offset=offsets[i]-1
        if offset<0:raise ValueError('invalid tile offset')
        result.append((ids[i],offset,lengths[i],runs[i]))
    return result


def _directory_bytes(entries):
    out=bytearray(_enc(len(entries)))
    cur=0
    for tid,_,_,_ in entries:
        if tid<cur:raise ValueError('unsorted tile id')
        out+=_enc(tid-cur);cur=tid
    for _,_,_,runs in entries:out+=_enc(runs)
    for _,_,length,_ in entries:out+=_enc(length)
    for i,(_,offset,length,_) in enumerate(entries):
        previous=entries[i-1] if i else None
        out+=_enc(0 if previous and offset==previous[1]+previous[2] else offset+1)
    return gzip.compress(bytes(out),mtime=0,compresslevel=9)


def inspect_archive(b: bytes | Path):
    if isinstance(b,Path):b=b.read_bytes()
    if b[:7]!=b'PMTiles' or b[7]!=3:raise ValueError('not PMTiles v3')
    parts=struct.unpack_from('<11Q',b,8)
    root_off,root_len,meta_off,meta_len,leaf_off,leaf_len,data_off,data_len,addr_count,entry_count,content_count=parts
    if leaf_len:raise ValueError('leaf directories unsupported for this deterministic merge')
    if b[97:100]!=bytes([2,2,1]):raise ValueError('expected gzip MVT PMTiles')
    if data_off+data_len!=len(b):raise ValueError('archive truncation')
    if root_off+root_len>len(b) or meta_off+meta_len>len(b):raise ValueError('bad metadata offsets')
    directory=_directory(b[root_off:root_off+root_len])
    if len(directory)!=entry_count or sum(x[3] for x in directory)!=addr_count:raise ValueError('bad tile count')
    tiles={}
    for tileid,offset,length,run in directory:
        if run!=1:raise ValueError('non-unit run not supported')
        if tileid in tiles:raise ValueError('duplicate tile id')
        if length<=0 or offset+length>data_len:raise ValueError('tile bounds')
        tile=b[data_off+offset:data_off+offset+length]
        gzip.decompress(tile) # validate compression, not just header
        tiles[tileid]=tile
    if content_count!=len(set(tiles.values())):
        raise ValueError('content count mismatch')
    meta=json.loads(gzip.decompress(b[meta_off:meta_off+meta_len]))
    return {'tiles':tiles,'tile_count':len(tiles),'metadata':meta,
            'header':{'flags':list(b[96:102]),'min_zoom':b[100], 'max_zoom':b[101],
                      'bbox':list(struct.unpack_from('<4i',b,102)),
                      'center':[b[118],*struct.unpack_from('<2i',b,119)]}}


def _combine_tiles(base_tiles, detail_tiles):
    if set(base_tiles)&set(detail_tiles):
        raise ValueError('PMTiles tile-id collision; must combine MVT layers by z/x/y')
    return {**base_tiles, **detail_tiles}


def merge_pmtiles(base: bytes, detail: bytes) -> bytes:
    if hashlib.sha256(base).hexdigest()!=EXPECTED_BASE_SHA256:raise ValueError('base hash differs from authoritative Koronus V9')
    if hashlib.sha256(detail).hexdigest()!=EXPECTED_DETAIL_SHA256:raise ValueError('detail hash differs from approved Furibundus v4')
    a=inspect_archive(base)
    b=inspect_archive(detail)
    if a['header']['min_zoom']!=0 or b['header']['min_zoom']!=9 or b['header']['max_zoom']!=16:raise ValueError('unexpected zoom bounds')
    layers=b['metadata'].get('vector_layers',[])
    if len(layers)!=26 or len({x['id'] for x in layers})!=26:raise ValueError('wrong source layer set')
    md={**a['metadata']}
    md.update({'name':'Koronus Expanse / Furibundus unified PMTiles',
       'minzoom':'0','maxzoom':'16','vector_layers':layers,
       'description':'Koronus original basemap tile preserved; additive Furibundus v4 star-centered MVT. ICM controls style and routes.',
       'furibundus':{'artifact_version':'v4-star-center','bbox':b['metadata']['bounds'],
                     'center':b['metadata']['center'], 'source_sha256':EXPECTED_DETAIL_SHA256,
                     'experimental_scale':True}})
    # Keep original Koronus bounds and center unchanged, including its metadata padding value.
    all_tiles=_combine_tiles(a['tiles'],b['tiles'])
    blobbuf=bytearray(); entries=[]
    for tid,tile in sorted(all_tiles.items()):
        entries.append((tid,len(blobbuf),len(tile),1));blobbuf+=tile
    dr=_directory_bytes(entries)
    if len(dr)>16257:raise ValueError('root too large; implement leaf directories before extending')
    metagzip=gzip.compress(json.dumps(md,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode(),mtime=0,compresslevel=9)
    root_off=127;meta_off=root_off+len(dr);data_off=meta_off+len(metagzip)
    hdr=bytearray(127);hdr[:7]=b'PMTiles';hdr[7]=3
    hdr[8:96]=struct.pack('<11Q',root_off,len(dr),meta_off,len(metagzip),0,0,data_off,len(blobbuf),len(entries),len(entries),len(set(all_tiles.values())))
    hdr[96:102]=bytes([1,2,2,1,0,16])
    hdr[102:127]=base[102:127]  # original Koronus geographical coverage and map center
    return bytes(hdr)+dr+metagzip+blobbuf


def main():
    if len(sys.argv)!=4:raise SystemExit('Usage: merge_pmtiles.py Koronus.pmtiles Furibundus.pmtiles combined.pmtiles')
    base,detail,out=map(Path,sys.argv[1:]);combined=merge_pmtiles(base.read_bytes(),detail.read_bytes())
    out.write_bytes(combined)
    r=inspect_archive(combined)
    print(json.dumps({'bytes':len(combined),'sha256':hashlib.sha256(combined).hexdigest(),
                      'tile_count':r['tile_count'],'zoom':[r['header']['min_zoom'],r['header']['max_zoom']],
                      'source_layers':len(r['metadata']['vector_layers'])},indent=2))
if __name__=='__main__':main()