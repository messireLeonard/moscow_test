# Koronus downloadable PMTiles v1 — Chicago-style hosting

This is a **non-production build experiment** based on the GitHub-hosted
Chicago PMTiles source used in `assets/trial-map-host-v1`. Chicago stores
`chicago.pmtiles.part-00`, `.part-01`, `.part-02` with 45 MiB maximum
chunk sizes and a manifest listing each chunk's SHA256 and length.

Source: SHA-pinned private ICM release `v0.2.140-rc.1`, exactly
129347313 bytes, SHA256
`43e436b6325eceee2dcb75a59e9385ac0535393747f2e75382a6af19aefcf0b2`.

## Output

- `koronus.pmtiles.part-00` — exact approved vector Koronus PMTiles,
  1964280 bytes, SHA256
  `d94f0ac84c187fc43711674a68a6bd376013e7bbc1d6086c27ecc603420a7dc7`.
- `koronus-resources.pmtiles.part-00/01/02...` — binary resource
  companion archive in standard PMTiles v3 structure, containing byte-for-byte
  `data/soi/**`, Koronus KML/GeoJSON and `vortex.json`. Files are
  mapped to virtual z12/x/y PMTiles tiles by a SHA-verified metadata index.
  Never pass this asset companion to MapLibre as a vector source.
- `manifest.json` — exact package and chunk lengths/SHA256, in the same
  `parts[]` format as Chicago. `SHA256SUMS.txt` for independent verification.

A new, immutable branch `assets/koronus-downloadable-v1` will host
`hosted-assets/koronus-v1/` once the real build is authorized and succeeds.
Existing Chicago hosting branch `assets/trial-map-host-v1` is not changed.
The source ZIP's SHA and Koronus PMTiles bytes/SHA are checked before extraction.
Each output chunk is at most 45 MiB. Unit tests verify PMTiles v3 index/data
roundtrip, source SHA, path confinement, file allowlist, chunk reconstruction,
corruption rejection and deterministic reproducibility.

## Private-source boundary

The original ICM repository is **private**, whereas `moscow_test` is public.
Its standard GitHub Actions token cannot read the ICM release. This build
requires a **read-only** repository secret `ICM_SOURCE_READ_TOKEN` in
`moscow_test`, granting read access to ICM releases (not write access).
No credentials or source assets are embedded in these commits.

Normal PR pushes run only independent unit tests. Publication requires an
explicit commit with prefix `publish(koronus):` and passing tests. The
publishing job checks the secret, fetches the private release, verifies its
fixed SHA-256, assembles the PMTiles pair, tests every chunk SHA, and creates
the hosting branch without overwriting any existing branch.

## Public chunk URLs
The published `manifest.json` will contain `rawBaseUrl`. The future ICM
chunk downloader must use this HTTPS base URL plus each allowlisted
`parts[].name`, verify every part's byte length and SHA-256, then verify
`expectedBytes` and `expectedSha256` on the reassembled PMTiles.
The branch name is fixed and the publisher refuses an existing hosting branch;
SHA validation remains mandatory, even if someone later changes the host.

## ICM dependency / next stage

This stage does not change the installed module or production maps.
ICM's current `CityPackageProbe` fetches a single `sourceUrl`, not
`parts[]`. Therefore chunk hosting alone does not make the Koronus install
work. After real chunk publication, ICM must implement streamed chunk download,
per-chunk SHA256 and total SHA verification, and install both primary vector
and resource companion PMTiles. SoI resource lookup must use companion PMTiles
`getMetadata()` and `getZxy()` instead of the current module-relative fetch.

Until this integration passes Foundry testing, continue using the complete
`v0.2.140-rc.1` when SoI detail is required. Do not promote the core-only
preview as a complete replacement.
