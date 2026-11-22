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
The source ZIP's SHA and Koronus PMTiles bytes/SHA are checked before extraction in private ICM; the public workflow independently checks the two transferred PMTiles and their provenance.
Each output chunk is at most 45 MiB. Unit tests verify PMTiles v3 index/data
roundtrip, source SHA, path confinement, file allowlist, chunk reconstruction,
corruption rejection and deterministic reproducibility.

## Two-stage bootstrap without a personal access token

This follows Chicago's exact separation of **source Release → parts hosting**.

1. In **private ICM**, build the two PMTiles once from the verified
   `v0.2.140-rc.1` ZIP (requires only the standard token of that same
   private repository). The source build command is:
   `python3 tools/build_koronus_downloadable.py <path-to-full-icm-rc.zip> --source-only --out <source-output>`
   It creates `koronus.pmtiles`, `koronus-resources.pmtiles`,
   `SOURCE_PROVENANCE.json` and `SHA256SUMS.txt`.
2. A separate **draft source Release** in `moscow_test`, tag
   `koronus-downloadable-v1-src`, receives **only those four output files**.
   This transfer is one-time, by the repository owner, just like the first
   Chicago source PMTiles. Do not copy the ICM ZIP to the public repo.
3. After those SHA-pinned assets have been uploaded, publish the source Release.
   An explicit commit starting with `publish(koronus):` runs the independent
   `moscow_test` workflow. Its **own** `GITHUB_TOKEN` downloads
   `koronus-downloadable-v1-src`, verifies source provenance and every
   individual asset, reconstructs PMTiles in pieces no larger than 45 MiB,
   and creates an immutable `assets/koronus-downloadable-v1` branch.
4. Source release preparation is also opt-in: the explicit
   `bootstrap(koronus):` commit creates its draft only after tests pass.

**No `ICM_SOURCE_READ_TOKEN`, personal access token or cross-repository
secret is needed.** Until the one-time transfer of actual source PMTiles
takes place, only fixture-based unit tests run. The original public
Chicago hosting and `main` remain unchanged.

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
