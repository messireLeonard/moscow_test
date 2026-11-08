# Koronus V9 / Furibundus v4 cloud release candidate

Base cloud repository commit: af5afa51d23145e308f115a477b2901d90b03248.
Original map data: koronus/v9/map-payload.json (15 source files, unchanged).
New binary resource: koronus/furibundus/v4/furibundus_v4_star_center.pmtiles
- Size: 639310 bytes
- SHA-256: 4852e73498ec531736ed7ecb6388f23112b33a66d3907587c18a37d104eba0c7
- Git blob SHA-1: dd0265be57838fc34e9e2b6304125eaae9f212f5
- 282 MVT tiles, 26 source layers, 4110 authored geometries, zoom 9-16.
- Star-system anchor [11.328774, 1.627352].
- Experimental artwork footprint, not astronomical distances.

This is an additive map DATA resource only, with no separate MapLibre style JSON or module code.
The required runtime is ICM PR #501 at cdacec0e072801c213c3460b0fe05901aec1b7fe or an independently verified compatible successor.
No existing Koronus KML, marker IDs, global route records, or base koronus.pmtiles changed.
The builder emits a versioned pre-release; old releases remain immutable. Foundry visual/GM/player validation is still open.
