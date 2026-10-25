from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from process_submission import parse_manifest
from repository_assets import MAX_REPOSITORY_FILE_BYTES, package_relative_path, repository_url, stage_package
from validate_catalog import ValidationFailure, open_asset, validate_package, validate_semantics
import test_moderation as fixtures


class RepositoryAssetsTest(unittest.TestCase):
    def test_raw_package_requires_creator_ownership_and_safe_path(self):
        manifest = fixtures.ModerationTest().valid_manifest()
        url = "https://raw.githubusercontent.com/alice-theme/themes/main/aurora.kstheme"
        manifest["theme"]["packageUrl"] = url
        self.assertEqual(url, parse_manifest(json.dumps(manifest), "alice-theme")["packageUrl"])
        for invalid in [
            url.replace("alice-theme", "another-user"),
            url.replace("/main/", "/main/../"),
            url.replace("/main/", "/main/%2e%2e/"),
            url.replace("/main/", "/main/a%2fb/"),
            url + "?download=1",
            "https://github.com/alice-theme/themes/blob/main/aurora.kstheme",
        ]:
            manifest["theme"]["packageUrl"] = invalid
            with self.subTest(url=invalid), self.assertRaises(ValidationFailure):
                parse_manifest(json.dumps(manifest), "alice-theme")

    def test_catalog_uses_canonical_repository_file(self):
        catalog = fixtures.ModerationTest().catalog_with_existing_theme()
        self.assertEqual(
            "https://raw.githubusercontent.com/fixz232/SterSU-ThemeStore/main/theme-store/packages/aurora-night/v1/aurora-night-v1.kstheme",
            catalog["themes"][0]["downloadUrl"],
        )

    def test_identical_release_rehosting_needs_no_version_bump(self):
        current = fixtures.ModerationTest().catalog_with_existing_theme()
        previous = copy.deepcopy(current)
        previous["themes"][0]["downloadUrl"] = "https://github.com/fixz232/SterSU-ThemeStore/releases/download/theme-aurora-night-v1/aurora-night-v1.kstheme"
        validate_semantics(current, previous)
        for field, value in [("sha256", "b" * 64), ("sizeBytes", 8192), ("packageVersion", 5)]:
            changed = copy.deepcopy(current)
            changed["themes"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValidationFailure):
                validate_semantics(changed, previous)

    def test_migration_rejects_wrong_tag_or_destination(self):
        current = fixtures.ModerationTest().catalog_with_existing_theme()
        previous = copy.deepcopy(current)
        previous["themes"][0]["downloadUrl"] = "https://github.com/fixz232/SterSU-ThemeStore/releases/download/theme-aurora-night-v2/aurora-night-v1.kstheme"
        with self.assertRaises(ValidationFailure):
            validate_semantics(current, previous)

    def test_staging_is_immutable_and_replayable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.kstheme"
            source.write_bytes(b"verified-original")
            path = stage_package(source, root, "aurora-night", 1)
            self.assertEqual(b"verified-original", path.read_bytes())
            self.assertEqual(path, stage_package(source, root, "aurora-night", 1))
            source.write_bytes(b"different-package")
            with self.assertRaises(ValidationFailure):
                stage_package(source, root, "aurora-night", 1)
            self.assertEqual(b"verified-original", path.read_bytes())

    def test_staging_rejects_oversized_file_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "too-big.kstheme"
            with source.open("wb") as handle:
                handle.truncate(MAX_REPOSITORY_FILE_BYTES + 1)
            with self.assertRaises(ValidationFailure):
                stage_package(source, root, "aurora-night", 1)
            self.assertFalse((root / "theme-store").exists())

    def test_local_validation_reads_unpublished_checkout_and_detects_hash_mismatch(self):
        fixture = fixtures.ModerationTest()
        theme = fixture.catalog_with_existing_theme()["themes"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / package_relative_path("aurora-night", 1)
            path.parent.mkdir(parents=True)
            path.write_bytes(b"tampered")
            with patch("validate_catalog.open_remote", side_effect=AssertionError("must validate local file")):
                with self.assertRaises(ValidationFailure):
                    validate_package(theme, root, "fixz232/SterSU-ThemeStore")

    def test_local_asset_path_cannot_escape_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in ["theme-store/assets/../secret", "theme-store/assets/%2e%2e/secret"]:
                with self.subTest(path=path), self.assertRaises(ValidationFailure):
                    open_asset("https://raw.githubusercontent.com/fixz232/SterSU-ThemeStore/main/" + path, Path(directory), "fixz232/SterSU-ThemeStore")


if __name__ == "__main__":
    unittest.main()
