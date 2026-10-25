# SterSU Cloud Theme Store

The cloud store is a signed-by-hash catalog hosted in this repository. Theme packages and preview media are stored directly in versioned repository directories. The catalog uses raw GitHub file URLs; new official theme Releases are no longer created.

> Cloud-theme publishing resumed on 2026-10-23 with the verified Shiroko dark theme by hyldhpx (beta0.0.1, package schema v7). The original embedded images are preserved; private author fields and device-local URIs are removed before publication. No additional artwork reuse license was supplied, so the entry uses `LicenseRef-All-Rights-Reserved` rather than assigning an open license.

## Trust model

- The Manager downloads only HTTPS resources hosted by GitHub or GitHub's content CDN.
- Every catalog entry must declare the exact package byte count and SHA-256.
- The Manager checks the final redirect host, byte count, SHA-256, ZIP paths, package schema, package version, embedded assets, and Manager compatibility before import.
- Applying a cloud theme first saves the current theme to the local library. A failed apply automatically restores that backup.
- No GitHub token or publishing credential is embedded in the APK.
- Creator approval is read from `creators/v1/creators.json`; local Manager settings never grant publishing rights.
- GitHub Actions rechecks the Issue author, creator registry, manifest, package hash, byte count, ZIP structure, compatibility range, and media after approval.

SHA-256 proves that the downloaded package matches the reviewed catalog. It does not replace catalog review. Only maintainers may merge catalog changes or run the publishing workflow.

## Creator access

1. Open **Theme center > My > Creator Center** and enter the GitHub account that will submit themes.
2. Create a creator application Issue from the **Access** page.
3. The repository owner `fixz232` reviews the application and adds the `creator-approved` label.
4. The moderation workflow verifies that the label was applied by `fixz232`, writes the Issue author to `creators/v1/creators.json`, and closes the application.
5. Refresh Creator Center. Submission tools unlock only when the downloaded registry contains that GitHub account.

Run **Moderate cloud theme creators and submissions** once with `workflow_dispatch` to create the moderation labels in a new repository. A creator approval grants no repository write permission and does not bypass per-theme review.

## Publishing a theme as an approved creator

1. In Creator Center, use **Create cloud-safe package from current theme**, or select any local file up to 500 MiB. The picker does not restrict the original filename, extension, or MIME type, but the bytes must contain a valid cloud-safe SterSU theme package. The Manager copies and validates one immutable snapshot, then computes its exact byte count and SHA-256. Local import supports up to 500 MiB, but repository publishing accepts files up to 100 MiB. Reduce embedded media if necessary; Git LFS pointers are not theme packages.
2. Export the validated snapshot as a standard `.kstheme` file and commit those exact bytes to a public GitHub repository under the approved creator's account. Paste the `https://raw.githubusercontent.com/<account>/<repository>/<ref>/<file>.kstheme` URL into Creator Center. The app and moderation workflow reject package URLs owned by another account.
3. Fill in the license, compatibility range, version, and an existing or custom category. Cover images and screenshots are optional; a theme can be submitted without any images. See **Preview images** below for recommendations and fallback behavior.
4. Run remote verification. The Manager downloads the repository file and requires its byte count and SHA-256 to match the selected local package.
5. Submit the generated GitHub Issue. The Issue author must be the approved creator recorded in the manifest.
6. `fixz232` reviews the visible metadata and adds `theme-approved` only when publication is allowed.
7. GitHub Actions repeats all security checks, commits the verified package and updated catalog together, adds a custom category when needed, updates the catalog, marks the Issue `theme-published`, and closes it.

The app intentionally does not upload directly to the central repository: doing so would require embedding a GitHub write token or an OAuth service. Creator-owned repositories keep publishing credentials outside the APK; legacy creator Release URLs remain accepted for compatibility while still providing a complete reviewed upload path.

The ordinary local export remains suitable for backup and device-to-device transfer, but it may preserve local `content://` references and private author fields for that purpose. Do not upload that file directly. The publishing workflow rejects device-specific URIs, a non-empty author real name, a non-`unspecified` gender, or any configured media that was not embedded in the cloud-safe package.

## Preview images (optional)

- Both the cover and screenshots may be left blank. No image is required to submit a theme.
- A horizontal collage of **Home, Superuser, Modules, and Settings** is recommended, matching the four-page preview layout. Individual screenshots are also accepted; four pages are not mandatory.
- There is no required resolution or aspect ratio. In particular, a 16:9 cover is not required. Keep the complete page content visible when preparing a collage.
- Provide up to eight unique, public HTTPS image URLs hosted on GitHub or its content CDN. A multi-page collage counts as one image. Each image or video asset may be up to 500 MiB.
- A blank or omitted `coverUrl` uses the first screenshot. If the cover is also blank or omitted and `screenshots` is an empty array, SterSU supplies its default cover. There is no need to upload a placeholder image.
- For a submission with no images, leave the cover blank in Creator Center; the generated manifest keeps `screenshots: []`. The published catalog still contains a valid `coverUrl` supplied by the fallback above.

## Maintainer publishing

1. Export a `.kstheme` package from **Theme center > Import and export**.
2. Optionally prepare a cover and up to eight screenshots or collages using the **Preview images** guidance above. No fixed aspect ratio is required. When entering the catalog directly, keep `screenshots: []` and use the public GitHub-hosted URL for this repository's `theme-store/assets/default-cover.png` as the `coverUrl` if no images are supplied.
3. Commit the package to a public GitHub repository and copy its raw file URL.
4. Ask a maintainer to run **Publish cloud theme** with the temporary URL, exact size, SHA-256, and package metadata. The workflow verifies the bytes and stores the verified package in `theme-store/packages/<theme-id>/v<versionCode>/<theme-id>-v<versionCode>.kstheme`. This manual workflow stages the package; catalog review is still required.
5. Add or update the entry in `catalog/v1/catalog.json` using that canonical URL. Increase `versionCode` whenever the package bytes, URL, hash, size, or version name changes.
6. Open a pull request. The catalog workflow validates the schema, URLs, compatibility range, remote media, package size, SHA-256, ZIP paths, and embedded `theme.json`.

Repository layout:

```text
theme-store/packages/<theme-id>/v<versionCode>/<theme-id>-v<versionCode>.kstheme
theme-store/assets/<theme-id>/v<versionCode>/cover.webp
theme-store/assets/<theme-id>/v<versionCode>/author.png
```

Use raw GitHub URLs for these files. Never overwrite a published package with different bytes: increase `versionCode` and create a new directory. The validator permits only the exact, byte-identical Release-to-repository relocation without a version bump. Existing Releases are retained for older clients.

The moderation workflow copies verified creator packages into this repository automatically. Keep preview media in `theme-store/assets/` when publishing manually. No GitHub write credentials are stored in the Manager.

## Public author data

Cloud entries contain only an explicit public author ID, display name, optional profile/avatar URLs, and an optional bio. Do not publish a real name, gender, private avatar, API token, device identifier, or other personal data. Local author profile fields inside the Manager are not uploaded automatically. The publishing validator rejects packages whose embedded `realName` is non-empty or whose embedded gender is not `unspecified`.

## Catalog fields

- `id`: stable lowercase theme identifier.
- `versionCode`: monotonically increasing package revision.
- `packageSchema` / `packageVersion`: must match the exported `.kstheme` package.
- `minManagerVersionCode` / `maxManagerVersionCode`: supported Manager range; use `null` for no upper limit.
- `sha256` / `sizeBytes`: exact package identity.
- `license`: SPDX license identifier for the theme assets.
- `status`: `published` or `deprecated`.
- `featured`: curated placement flag.
- `downloadCount`: preserved historical download count. GitHub raw files do not expose Release-style download counts; the legacy statistics workflow updates only entries still hosted in Releases.

Run the local validator before submitting:

```bash
python theme-store/scripts/validate_catalog.py \
  theme-store/catalog/v1/catalog.json \
  --schema theme-store/schemas/catalog-v1.schema.json
```

For a PR containing new repository assets, add `--check-remote --repository-root . --repository fixz232/SterSU-ThemeStore` to validate the checked-out files before they are published. Use `--check-remote` alone to verify live public downloads after pushing.

Validate creator moderation changes with:

```bash
python -m unittest discover -s theme-store/tests -p "test_*.py" -v
```
