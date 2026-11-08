# Koronus V9 / Furibundus v4 — unified PMTiles

Authoritative map sources remain distinct and reproducible:
- `koronus/v9/map-payload.json`: 15 unchanged V9 source records, including the original 1501-byte vector base and its map-owned KML.
- `koronus/furibundus/v4/furibundus_v4_star_center.pmtiles`: approved detail input, 282 MVT tiles and 26 source-layers.
- `koronus/furibundus/v4/merge_pmtiles.py`: deterministic PMTiles v3 merger, preserves source tile bytes.
- `koronus/furibundus/v4/build_release.py`: assembles one deployable PMTiles plus unchanged KML and Vortex resources.

**Deployable result:** exactly ONE `data/map-packages/koronus.pmtiles`, 640712 bytes, 283 tiles (z0, z9–16), 26 Furibundus source layers. SHA256:
`11d2862209f298e6fa1b012de011e090ff25e4251ec6774cc53a31bea13ab6fb`

The original Koronus z0 tile and all Furibundus tiles are copied verbatim. The artifact retains Koronus bounds and map center. The Furibundus star is anchored at the existing system marker coordinate [11.328774, 1.627352], with non-astronomical experimental scale.

Published map-only pre-release: https://github.com/messireLeonard/moscow_test/releases/tag/koronus-v9-unified-furibundus-rc-20261109

ICM integration: PR #501, branch `work/koronus-furibundus-pmtiles-lod-v1`; it uses the existing `protomaps` source, no secondary PMTiles or standalone style. It handles z11 camera threshold, global marker and clipped-route display. Do not install an older two-source build against this unified data.

Cloud Git retains the separately authored v4 input **for deterministic rebuilding**, but neither the release ZIP nor the deployed ICM module requires a separate Furibundus PMTiles.

Existing released tags remain immutable. No scene migration, GM/player runtime validation, actual Foundry preview or visual acceptance has been performed.
