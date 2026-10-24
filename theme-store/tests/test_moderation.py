from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from moderation_common import (  # noqa: E402
    normalize_github_login,
    parse_issue_form,
    validate_registry,
)
from approve_creator import validate_creator_approval  # noqa: E402
from prepare_release import download_and_verify_package  # noqa: E402
from process_submission import (  # noqa: E402
    DEFAULT_COVER_URL,
    parse_manifest,
    update_catalog,
    validate_submission_event,
)
from validate_catalog import (  # noqa: E402
    ValidationFailure,
    validate_embedded_assets,
    validate_image,
    validate_semantics,
)


class ModerationTest(unittest.TestCase):
    def test_issue_form_parser_extracts_rendered_json(self) -> None:
        fields = parse_issue_form(
            "### Theme ID\n\naurora-night\n\n"
            "### Submission manifest\n\n```json\n{\"version\": 1}\n```\n"
        )
        self.assertEqual("aurora-night", fields["Theme ID"])
        self.assertEqual('{"version": 1}', fields["Submission manifest"])

    def test_github_login_rejects_consecutive_hyphens(self) -> None:
        with self.assertRaises(ValidationFailure):
            normalize_github_login("bad--login")

    def test_registry_rejects_duplicate_case_insensitive_login(self) -> None:
        registry = self.valid_registry()
        registry["creators"].append(
            {
                "github": "ALICE-theme",
                "displayName": "Duplicate",
                "approvedAt": 2,
                "status": "approved",
            }
        )
        with self.assertRaises(ValidationFailure):
            validate_registry(registry)

    def test_manifest_rejects_issue_author_mismatch(self) -> None:
        with self.assertRaises(ValidationFailure):
            parse_manifest(json.dumps(self.valid_manifest()), "another-user")

    def test_manifest_rejects_release_owned_by_another_account(self) -> None:
        manifest = self.valid_manifest()
        manifest["theme"]["packageUrl"] = (
            "https://github.com/another-user/themes/releases/download/v1/theme.kstheme"
        )
        with self.assertRaises(ValidationFailure):
            parse_manifest(json.dumps(manifest), "alice-theme")

    def test_manifest_accepts_exact_500_mib_package(self) -> None:
        manifest = self.valid_manifest()
        manifest["theme"]["sizeBytes"] = 500 * 1024 * 1024

        parsed = parse_manifest(json.dumps(manifest), "alice-theme")

        self.assertEqual(500 * 1024 * 1024, parsed["sizeBytes"])

    def test_manifest_rejects_package_over_500_mib(self) -> None:
        manifest = self.valid_manifest()
        manifest["theme"]["sizeBytes"] = 500 * 1024 * 1024 + 1

        with self.assertRaises(ValidationFailure):
            parse_manifest(json.dumps(manifest), "alice-theme")

    def test_manifest_accepts_v4_through_v7_packages(self) -> None:
        manifest = self.valid_manifest()
        for version in range(4, 8):
            with self.subTest(version=version):
                manifest["theme"]["packageVersion"] = version
                parsed = parse_manifest(json.dumps(manifest), "alice-theme")
                self.assertEqual(version, parsed["packageVersion"])

    def test_manifest_rejects_future_package_version(self) -> None:
        manifest = self.valid_manifest()
        manifest["theme"]["packageVersion"] = 8
        with self.assertRaises(ValidationFailure):
            parse_manifest(json.dumps(manifest), "alice-theme")

    def test_catalog_accepts_v7_package(self) -> None:
        catalog = self.catalog_with_existing_theme()
        catalog["themes"][0]["packageVersion"] = 7
        validate_semantics(catalog, None)

    def test_release_accepts_v7_package(self) -> None:
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("theme.json", json.dumps({
                "schema": "io.github.fixz.apkesu.theme",
                "version": 7,
                "author": {"realName": "", "gender": "unspecified"},
            }))
        payload = package.getvalue()
        with tempfile.TemporaryDirectory() as directory, patch(
            "prepare_release.open_remote", return_value=io.BytesIO(payload)
        ):
            result = download_and_verify_package(
                theme_id="test-sidebar", version_code=1, package_version=7,
                source_url="https://github.com/owner/themes/releases/download/v1/test.kstheme",
                asset_name="test-sidebar-v1.kstheme", sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload), output_dir=Path(directory),
            )
            self.assertEqual(payload, result.read_bytes())

    def test_catalog_rejects_future_package_version(self) -> None:
        catalog = self.catalog_with_existing_theme()
        catalog["themes"][0]["packageVersion"] = 8
        with self.assertRaises(ValidationFailure):
            validate_semantics(catalog, None)

    def test_sidebar_accepts_embedded_image(self) -> None:
        metadata = {"sidebar": {"images": {"avatar": {"asset": {"path": "assets/avatar.png"}}}}}
        validate_embedded_assets(metadata, {"assets/avatar.png"}, "package")

    def test_sidebar_rejects_missing_embedded_image(self) -> None:
        metadata = {"sidebar": {"images": {"avatar": {"asset": {"path": "assets/missing.png"}}}}}
        with self.assertRaises(ValidationFailure):
            validate_embedded_assets(metadata, set(), "package")

    def test_sidebar_rejects_device_specific_image_uri(self) -> None:
        metadata = {"sidebar": {"images": {"avatar": {"uri": "content://local/avatar"}}}}
        with self.assertRaises(ValidationFailure):
            validate_embedded_assets(metadata, set(), "package")

    def test_sidebar_rejects_invalid_image_metadata(self) -> None:
        for sidebar in (None, [], {"images": []}, {"images": {"avatar": None}}):
            with self.subTest(sidebar=sidebar), self.assertRaises(ValidationFailure):
                validate_embedded_assets({"sidebar": sidebar}, set(), "package")

    def test_manifest_uses_first_screenshot_when_cover_is_blank(self) -> None:
        manifest = self.valid_manifest()
        manifest["theme"]["coverUrl"] = ""
        manifest["theme"]["screenshots"] = [
            "https://raw.githubusercontent.com/alice-theme/themes/main/screen.png"
        ]

        parsed = parse_manifest(json.dumps(manifest), "alice-theme")

        self.assertEqual(parsed["screenshots"][0], parsed["coverUrl"])

    def test_manifest_uses_default_cover_when_cover_is_missing(self) -> None:
        manifest = self.valid_manifest()
        del manifest["theme"]["coverUrl"]

        parsed = parse_manifest(json.dumps(manifest), "alice-theme")

        self.assertEqual(DEFAULT_COVER_URL, parsed["coverUrl"])

    def test_remote_image_accepts_exact_streaming_boundary(self) -> None:
        payload = b"\x89PNG\r\n\x1a\n" + b"x" * 24
        response = self.remote_response(payload)
        with patch("validate_catalog.MAX_IMAGE_BYTES", len(payload)), patch(
            "validate_catalog.open_remote",
            return_value=response,
        ):
            validate_image("https://example.com/cover.png")

    def test_submission_without_images_produces_a_valid_catalog(self) -> None:
        for cover in ("", " \t ", None, "omitted"):
            with self.subTest(cover=cover):
                manifest = self.valid_manifest()
                if cover == "omitted":
                    del manifest["theme"]["coverUrl"]
                else:
                    manifest["theme"]["coverUrl"] = cover
                manifest["theme"]["screenshots"] = []
                event = self.submission_event(manifest=manifest)
                submission = validate_submission_event(event, "fixz232", self.valid_registry())
                catalog = self.catalog_with_existing_theme()
                catalog["themes"] = []

                update_catalog(catalog, submission, "fixz232/SterSU-ThemeStore", 200)
                validate_semantics(catalog, None)

                self.assertEqual(DEFAULT_COVER_URL, catalog["themes"][0]["coverUrl"])
                self.assertEqual([], catalog["themes"][0]["screenshots"])

    def test_manifest_accepts_one_collage_without_a_separate_cover(self) -> None:
        collage = "https://raw.githubusercontent.com/alice-theme/themes/main/four-page-collage.jpg"
        manifest = self.valid_manifest()
        del manifest["theme"]["coverUrl"]
        manifest["theme"]["screenshots"] = [collage]

        parsed = parse_manifest(json.dumps(manifest), "alice-theme")

        self.assertEqual(collage, parsed["coverUrl"])
        self.assertEqual([collage], parsed["screenshots"])

    def test_manifest_accepts_eight_optional_screenshots(self) -> None:
        screenshots = [
            f"https://raw.githubusercontent.com/alice-theme/themes/main/screen-{index}.png"
            for index in range(8)
        ]
        manifest = self.valid_manifest()
        manifest["theme"]["screenshots"] = screenshots

        parsed = parse_manifest(json.dumps(manifest), "alice-theme")

        self.assertEqual(screenshots, parsed["screenshots"])

    def test_manifest_rejects_too_many_or_duplicate_screenshots(self) -> None:
        screenshot = "https://raw.githubusercontent.com/alice-theme/themes/main/screen.png"
        too_many = [
            f"https://raw.githubusercontent.com/alice-theme/themes/main/screen-{index}.png"
            for index in range(9)
        ]
        for screenshots in (too_many, [screenshot, screenshot]):
            with self.subTest(screenshots=screenshots):
                manifest = self.valid_manifest()
                manifest["theme"]["screenshots"] = screenshots

                with self.assertRaises(ValidationFailure):
                    parse_manifest(json.dumps(manifest), "alice-theme")

    def test_remote_image_rejects_first_byte_over_limit(self) -> None:
        payload = b"\x89PNG\r\n\x1a\n" + b"x" * 25
        response = self.remote_response(payload)
        with patch("validate_catalog.MAX_IMAGE_BYTES", len(payload) - 1), patch(
            "validate_catalog.open_remote",
            return_value=response,
        ):
            with self.assertRaises(ValidationFailure):
                validate_image("https://example.com/cover.png")

    def test_creator_approval_rejects_non_fixz232_labeler(self) -> None:
        with self.assertRaises(ValidationFailure):
            validate_creator_approval(
                self.creator_event(sender="repository-bot"),
                "fixz232",
                100,
            )

    def test_creator_approval_rejects_missing_introduction(self) -> None:
        event = self.creator_event()
        event["issue"]["body"] = event["issue"]["body"].replace(
            "### Introduction\n\nOriginal themes.\n\n",
            "",
        )

        with self.assertRaises(ValidationFailure):
            validate_creator_approval(event, "fixz232", 100)

    def test_creator_approval_rejects_title_author_mismatch(self) -> None:
        event = self.creator_event()
        event["issue"]["title"] = "[Creator application] another-user"

        with self.assertRaises(ValidationFailure):
            validate_creator_approval(event, "fixz232", 100)

    def test_submission_rejects_non_fixz232_labeler(self) -> None:
        with self.assertRaises(ValidationFailure):
            validate_submission_event(
                self.submission_event(sender="repository-bot"),
                "fixz232",
                self.valid_registry(),
            )

    def test_submission_rejects_issue_and_manifest_author_mismatch(self) -> None:
        event = self.submission_event(issue_author="another-user")
        with self.assertRaises(ValidationFailure):
            validate_submission_event(event, "fixz232", self.valid_registry())

    def test_cloud_package_rejects_device_uri_even_with_embedded_asset(self) -> None:
        metadata = {
            "cards": {
                "lkm": {
                    "asset": {"path": "assets/lkm.png"},
                    "uri": "content://private/lkm.png",
                }
            }
        }
        with self.assertRaises(ValidationFailure):
            validate_embedded_assets(metadata, {"assets/lkm.png"}, "theme")

    def test_cloud_package_validates_component_switch_image(self) -> None:
        metadata = {
            "packageType": "component",
            "components": {
                "switchStyle": {
                    "style": self.valid_switch_component_style(),
                    "imageAsset": {"path": "assets/component_switch_image.png"},
                    "imageUri": None,
                }
            }
        }
        validate_embedded_assets(
            metadata,
            {"assets/component_switch_image.png"},
            "theme",
        )
        metadata["components"]["switchStyle"]["imageUri"] = "file:///private/image.png"
        with self.assertRaises(ValidationFailure):
            validate_embedded_assets(
                metadata,
                {"assets/component_switch_image.png"},
                "theme",
            )
        metadata["components"]["switchStyle"]["imageUri"] = None
        metadata["components"]["switchStyle"]["style"]["image_uri"] = "file:///private/nested.png"
        with self.assertRaises(ValidationFailure):
            validate_embedded_assets(
                metadata,
                {"assets/component_switch_image.png"},
                "theme",
            )
        metadata["components"]["switchStyle"]["style"]["image_uri"] = None
        metadata["components"]["switchStyle"]["style"]["source"] = "pixel"
        with self.assertRaises(ValidationFailure):
            validate_embedded_assets(
                metadata,
                {"assets/component_switch_image.png"},
                "theme",
            )

    def test_cloud_package_validates_v2_switch_images(self) -> None:
        off_path = "assets/component_switch_image.png"
        on_path = "assets/component_switch_image_on.png"
        off_bytes = b"validated v2 off image"
        on_bytes = b"validated v2 on image"
        style = self.valid_switch_component_style()
        style.update(
            {
                "version": 2,
                "image_sha256": hashlib.sha256(off_bytes).hexdigest(),
                "image_on_sha256": hashlib.sha256(on_bytes).hexdigest(),
                "image_on_mime": "image/png",
                "image_on_uri": None,
            }
        )
        metadata = {
            "components": {
                "switchStyle": {
                    "style": style,
                    "imageAsset": {"path": off_path},
                    "imageOnAsset": {"path": on_path},
                    "imageUri": None,
                    "imageOnUri": None,
                }
            }
        }
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr(off_path, off_bytes)
            archive.writestr(on_path, on_bytes)
        archive_bytes.seek(0)

        with zipfile.ZipFile(archive_bytes) as archive:
            validate_embedded_assets(metadata, {off_path, on_path}, "theme", archive)
            metadata["components"]["switchStyle"]["imageOnUri"] = "file:///private/on.png"
            with self.assertRaises(ValidationFailure):
                validate_embedded_assets(metadata, {off_path, on_path}, "theme", archive)

    def test_cloud_package_rejects_invalid_component_grid(self) -> None:
        style = self.valid_switch_component_style()
        style["track_on"]["width"] = 27
        metadata = {
            "packageType": "component",
            "components": {
                "switchStyle": {
                    "style": style,
                    "imageAsset": {"path": "assets/component_switch_image.png"},
                    "imageUri": None,
                }
            },
        }

        with self.assertRaises(ValidationFailure):
            validate_embedded_assets(
                metadata,
                {"assets/component_switch_image.png"},
                "theme",
            )

    def test_cloud_package_verifies_component_image_hash(self) -> None:
        image_path = "assets/component_switch_image.png"
        image_bytes = b"validated component image"
        style = self.valid_switch_component_style()
        style["image_sha256"] = hashlib.sha256(image_bytes).hexdigest()
        metadata = {
            "packageType": "component",
            "components": {
                "switchStyle": {
                    "style": style,
                    "imageAsset": {"path": image_path},
                    "imageUri": None,
                }
            },
        }
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr(image_path, image_bytes)
        archive_bytes.seek(0)

        with zipfile.ZipFile(archive_bytes) as archive:
            validate_embedded_assets(metadata, {image_path}, "theme", archive)
            style["image_sha256"] = "b" * 64
            with self.assertRaises(ValidationFailure):
                validate_embedded_assets(metadata, {image_path}, "theme", archive)

    def test_cloud_package_validates_embedded_font(self) -> None:
        font_path = "assets/font_custom.ttf"
        font_bytes = b"\x00\x01\x00\x00validated-font"
        font_hash = hashlib.sha256(font_bytes).hexdigest()
        metadata = {
            "version": 4,
            "font": {
                "preset": "custom",
                "name": "Example.ttf",
                "asset": {"path": font_path},
                "sha256": font_hash,
                "sizeBytes": len(font_bytes),
            },
        }
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr(font_path, font_bytes)
        archive_bytes.seek(0)

        with zipfile.ZipFile(archive_bytes) as archive:
            validate_embedded_assets(metadata, {font_path}, "theme", archive)

        metadata["font"]["sha256"] = "b" * 64
        archive_bytes.seek(0)
        with zipfile.ZipFile(archive_bytes) as archive:
            with self.assertRaises(ValidationFailure):
                validate_embedded_assets(metadata, {font_path}, "theme", archive)

    def test_catalog_adds_custom_category_and_preserves_owner(self) -> None:
        catalog = {
            "schema": "io.github.fixz.apkesu.theme-catalog",
            "version": 1,
            "generatedAt": 0,
            "categories": [],
            "themes": [],
        }
        submission = parse_manifest(json.dumps(self.valid_manifest()), "alice-theme")
        tag, asset = update_catalog(catalog, submission, "fixz232/SterSU-ThemeStore", 100)

        self.assertEqual("theme-aurora-night-v1", tag)
        self.assertEqual("aurora-night-v1.kstheme", asset)
        self.assertEqual([{"id": "appearance", "name": "Appearance"}], catalog["categories"])
        self.assertEqual("alice-theme", catalog["themes"][0]["author"]["id"])

    def test_catalog_rejects_theme_id_takeover_without_mutating_catalog(self) -> None:
        catalog = self.catalog_with_existing_theme()
        before = json.loads(json.dumps(catalog))
        manifest = self.valid_manifest()
        manifest["theme"]["author"]["github"] = "mallory-theme"
        manifest["theme"]["packageUrl"] = (
            "https://github.com/mallory-theme/themes/releases/download/v1/theme.kstheme"
        )
        submission = parse_manifest(json.dumps(manifest), "mallory-theme")

        with self.assertRaises(ValidationFailure):
            update_catalog(catalog, submission, "fixz232/SterSU-ThemeStore", 200)

        self.assertEqual(before, catalog)

    def test_catalog_requires_higher_version_for_changed_metadata(self) -> None:
        catalog = self.catalog_with_existing_theme()
        manifest = self.valid_manifest()
        manifest["theme"]["description"] = "Changed without a version bump."
        submission = parse_manifest(json.dumps(manifest), "alice-theme")

        with self.assertRaises(ValidationFailure):
            update_catalog(catalog, submission, "fixz232/SterSU-ThemeStore", 200)

    def test_catalog_rejects_duplicate_category_name_with_new_id(self) -> None:
        catalog = self.catalog_with_existing_theme()
        before = json.loads(json.dumps(catalog))
        manifest = self.valid_manifest()
        manifest["theme"]["category"] = {
            "id": "appearance-copy",
            "name": "appearance",
        }
        submission = parse_manifest(json.dumps(manifest), "alice-theme")

        with self.assertRaises(ValidationFailure):
            update_catalog(catalog, submission, "fixz232/SterSU-ThemeStore", 200)

        self.assertEqual(before, catalog)

    def test_catalog_allows_exact_same_version_retry(self) -> None:
        catalog = self.catalog_with_existing_theme()
        before = json.loads(json.dumps(catalog))
        submission = parse_manifest(json.dumps(self.valid_manifest()), "alice-theme")

        update_catalog(catalog, submission, "fixz232/SterSU-ThemeStore", 200)

        self.assertEqual(before, catalog)

    def test_catalog_allows_exact_standalone_repository_migration(self) -> None:
        current = self.catalog_with_existing_theme()
        previous = json.loads(json.dumps(current))
        previous["themes"][0]["downloadUrl"] = previous["themes"][0][
            "downloadUrl"
        ].replace("/SterSU-ThemeStore/", "/ApkeSU/")

        validate_semantics(current, previous)

    def test_catalog_rejects_unrelated_repository_change_without_version_bump(self) -> None:
        previous = self.catalog_with_existing_theme()
        current = json.loads(json.dumps(previous))
        current["themes"][0]["downloadUrl"] = current["themes"][0][
            "downloadUrl"
        ].replace("/SterSU-ThemeStore/", "/AnotherStore/")

        with self.assertRaises(ValidationFailure):
            validate_semantics(current, previous)

    def valid_registry(self) -> dict:
        return {
            "schema": "io.github.fixz.apkesu.theme-creators",
            "version": 1,
            "generatedAt": 1,
            "reviewer": "fixz232",
            "creators": [
                {
                    "github": "alice-theme",
                    "displayName": "Alice",
                    "approvedAt": 1,
                    "status": "approved",
                }
            ],
        }

    @staticmethod
    def pixel_grid(width: int, height: int) -> dict:
        return {
            "width": width,
            "height": height,
            "pixels": [0] * (width * height),
        }

    @staticmethod
    def remote_response(payload: bytes) -> io.BytesIO:
        response = io.BytesIO(payload)
        response.headers = {}
        return response

    def valid_switch_component_style(self) -> dict:
        return {
            "schema": "io.github.fixz.apkesu.component-style",
            "version": 1,
            "kind": "switch_style",
            "id": "switch-test-style",
            "name": "Test switch",
            "author": "Alice",
            "updated_at": 1,
            "source": "image",
            "track_off": self.pixel_grid(28, 12),
            "track_on": self.pixel_grid(28, 12),
            "thumb_off": self.pixel_grid(12, 12),
            "thumb_on": self.pixel_grid(12, 12),
            "image_uri": None,
            "image_sha256": "a" * 64,
            "image_mime": "image/png",
            "image_scale": "crop",
            "image_opacity": 1.0,
            "palette": [0, 0xFFFFFFFF],
            "motion": {
                "enabled": False,
                "mode": "static",
                "duration_ms": 2400,
                "amplitude_cells": 1,
                "repeat": "reverse",
            },
        }

    def creator_event(self, *, sender: str = "fixz232") -> dict:
        return {
            "sender": {"login": sender},
            "label": {"name": "creator-approved"},
            "issue": {
                "title": "[Creator application] alice-theme",
                "user": {"login": "alice-theme"},
                "labels": [{"name": "creator-approved"}],
                "body": (
                    "### GitHub login\n\nalice-theme\n\n"
                    "### Public creator name\n\nAlice\n\n"
                    "### Introduction\n\nOriginal themes.\n\n"
                    "### Declarations\n\n- [x] one\n- [x] two\n- [x] three"
                ),
            },
        }

    def submission_event(
        self,
        *,
        sender: str = "fixz232",
        issue_author: str = "alice-theme",
        manifest: dict | None = None,
    ) -> dict:
        if manifest is None:
            manifest = self.valid_manifest()
        theme = manifest["theme"]
        return {
            "sender": {"login": sender},
            "label": {"name": "theme-approved"},
            "issue": {
                "title": "[Cloud theme] aurora-night - Aurora Night",
                "user": {"login": issue_author},
                "labels": [{"name": "theme-approved"}],
                "body": (
                    f"### Theme ID\n\n{theme['id']}\n\n"
                    f"### Category\n\n{theme['category']['id']} | {theme['category']['name']}\n\n"
                    f"### GitHub-hosted package URL\n\n{theme['packageUrl']}\n\n"
                    "### Submission manifest\n\n```json\n"
                    f"{json.dumps(manifest)}\n```\n\n"
                    "### Declarations\n\n- [x] one\n- [x] two\n- [x] three\n- [x] four"
                ),
            },
        }

    def catalog_with_existing_theme(self) -> dict:
        catalog = {
            "schema": "io.github.fixz.apkesu.theme-catalog",
            "version": 1,
            "generatedAt": 100,
            "categories": [],
            "themes": [],
        }
        submission = parse_manifest(json.dumps(self.valid_manifest()), "alice-theme")
        update_catalog(catalog, submission, "fixz232/SterSU-ThemeStore", 100)
        return catalog

    def valid_manifest(self) -> dict:
        return {
            "schema": "io.github.fixz.apkesu.theme-submission",
            "version": 1,
            "theme": {
                "id": "aurora-night",
                "name": "Aurora Night",
                "description": "A complete theme.",
                "category": {"id": "appearance", "name": "Appearance"},
                "tags": ["dark"],
                "versionCode": 1,
                "versionName": "1.0.0",
                "packageSchema": "io.github.fixz.apkesu.theme",
                "packageVersion": 4,
                "minManagerVersionCode": 32700,
                "maxManagerVersionCode": None,
                "coverUrl": "https://raw.githubusercontent.com/alice-theme/themes/main/cover.png",
                "screenshots": [],
                "packageUrl": "https://github.com/alice-theme/themes/releases/download/v1/theme.kstheme",
                "sha256": "a" * 64,
                "sizeBytes": 4096,
                "license": "CC-BY-4.0",
                "changelog": "Initial",
                "author": {
                    "github": "alice-theme",
                    "name": "Alice",
                    "profileUrl": "https://github.com/alice-theme",
                    "bio": "Creator",
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
