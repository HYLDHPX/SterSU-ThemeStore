# SterSU Manager plugins

The Manager reads this directory from `fixz232/SterSU-ThemeStore/main/plugin-store`.
Plugin packages are data-only capability descriptors. The actual pages and
runtime implementation are supplied by a compatible Manager and ksud, not by
executable code downloaded from this directory.

## Catalog compatibility

- `catalog-v1.json` and `catalog-v1.sig` preserve the signed nine-plugin
  catalog for older Manager builds. The lost legacy key means this historical
  catalog cannot be edited or re-signed.
- `catalog-v2.json` and `catalog-v2.sig` provide the active five-plugin catalog.
- `image-tools`, `cpu-spoof`, `graphics-renderer`, and `ai-chat` were retired
  from the store on 2026-10-09. Their package files are no longer published.
- `pathmask-lkm` was removed from the store on 2026-10-15. Its package is no
  longer published; existing installed records and device configuration are
  retained so users are not disrupted by a catalog change.
- The v2 catalog is signed with the replacement Ed25519 key introduced on
  2026-10-07. Updated Managers trust both the replacement and legacy pinned
  public keys and bundle the signed v2 catalog for offline listing.
- Older Managers that know only the legacy key cannot validate the new v2
  signature; they must update to use this catalog. The original v1 files
  remain unchanged for signature compatibility, but retired package downloads
  are unavailable. Existing installed plugin records are preserved.
- Unsigned catalogs, unknown signing keys, mismatched catalog/signature pairs,
  and packages whose hashes do not match the signed catalog remain rejected.

## Signing key migration

The new `CATALOG_PUBLIC_KEY_B64` is an X.509 Ed25519 public key. Its DER
SHA-256 fingerprint is
`5b68acec11b652d26fe973d0d7c618595dd0c5661a1bf52c48c449e99de6e951`.
`LEGACY_CATALOG_PUBLIC_KEY_B64` is retained only for compatibility. The lost
legacy private key cannot be recovered from a signature or public key; do not
re-sign or regenerate the frozen v1 catalog.

Catalog signing is independent of Android APK signing. This migration does
not replace the APK installation certificate or the kernel's Manager identity.

## Publishing v2

1. Run `scripts/generate-plugin-store-v2.ps1` from the source repository to
   calculate the package hash and byte count and update both catalog copies.
2. Set `APKESU_PLUGIN_STORE_KEY` to the external PKCS#8 PEM file whose public
   key matches `CATALOG_PUBLIC_KEY_B64` in `PluginStore.kt`.
3. Run `python scripts/sign-plugin-store.py 2`. The script checks that the key
   matches the Manager pin and that the published and bundled JSON bytes match
   before writing either signature.
4. Verify the signed Git blob and all package hashes before publishing the
   catalog, signature, and package together in one commit.
5. Re-download the public files and verify them again.

Never commit the private key, copy the v1 signature onto v2, disable signature
checks, or replace the trusted public key without a separate migration plan.
The web-manager and stealth capabilities remain paired in
`remote-management-suite`; they are not separate independent downloads.
