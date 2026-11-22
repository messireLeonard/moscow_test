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
2. Run `powershell -NoProfile -ExecutionPolicy Bypass -File tools/transfer_koronus_source_to_moscow_test.ps1` (Windows built-in PowerShell) from
   this repository checkout on a machine with `gh auth login` already
   authorized for both repos. The script downloads from private ICM,
   checks all four expected file sizes and SHA256, checks the provenance,
   uploads only the verified files to the empty public draft, validates
   remote size and publishes it. **No new GitHub token or Actions secret.**
   A separate **draft source Release** in `moscow_test`, tag
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

Private ICM staging is implemented in branch `work/koronus-source-pmtiles-bootstrap-v1`, workflow `stage-koronus-source-pmtiles-v1.yml`. Its output is a private, non-production source-transfer release; it does not give the public workflow access to the private repository.

## Verified source Release — 2026-11-22

The immutable input Release `koronus-downloadable-v1-src` in this repository is published. All four release assets have been compared against the original private ICM source-transfer release and **their GitHub-reported sizes and SHA-256 digests match exactly**:

- `koronus.pmtiles`: 1,964,280 bytes; SHA-256 `d94f0ac84c187fc43711674a68a6bd376013e7bbc1d6086c27ecc603420a7dc7`.
- `koronus-resources.pmtiles`: 119,589,679 bytes; SHA-256 `523b9700d25097fafc68481d573a4022acf74fa9f1efb6d818041e8aaaf1c18a`.
- `SHA256SUMS.txt`: 266 bytes; SHA-256 `494f9eb5cfaa686db75a2f61d7cf6f7cfe626b46be02d3d3469dc8d4e0841d12`.
- `SOURCE_PROVENANCE.json`: 670 bytes; SHA-256 `f26a5c7dfd85936d9dc2e9c2572ee829a9b723f83e30fd8e36f22c38132470cd`.

A commit with the `publish(koronus):` prefix triggers real-source CI validation and creates the immutable segmented hosting branch if all checks pass. This does not merge the PR or modify the ICM production runtime.
