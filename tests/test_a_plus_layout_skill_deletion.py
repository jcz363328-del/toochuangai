from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from 图片 import openrouter_image_site as site


def create_skill(
    root: Path,
    skill_id: str,
    owner: str,
    created_at: str,
    title: str,
) -> dict[str, object]:
    skill_dir = root / skill_id
    cases_dir = skill_dir / "cases"
    cases_dir.mkdir(parents=True)
    (cases_dir / "01_case.png").write_bytes(b"case")
    (skill_dir / "layout_skeleton.png").write_bytes(b"skeleton")
    (skill_dir / "A_PLUS_LAYOUT_SKILL.md").write_text("skill", encoding="utf-8")
    manifest_path = skill_dir / "manifest.json"
    manifest = {
        "schema_version": site.A_PLUS_SKILL_SCHEMA_VERSION,
        "type": site.A_PLUS_SKILL_DB_TYPE,
        "skill_id": skill_id,
        "title": title,
        "created_at": created_at,
        "created_by": owner,
        "root_path": str(root),
        "manifest_path": str(manifest_path),
        "skeleton_path": str(skill_dir / "layout_skeleton.png"),
        "skill_prompt_path": str(skill_dir / "A_PLUS_LAYOUT_SKILL.md"),
        "source_files": [{"index": 1, "file": str(cases_dir / "01_case.png")}],
        "common": {"style": "test"},
        "skill_prompt": "test",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest


class APlusLayoutSkillDeletionTests(unittest.TestCase):
    def test_delete_removes_only_owned_skill_and_updates_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            alice_old = create_skill(
                root,
                "alice-old",
                "alice",
                "2026-07-20T10:00:00",
                "Alice 旧版式",
            )
            alice_new = create_skill(
                root,
                "alice-new",
                "alice",
                "2026-07-24T11:30:00",
                "Alice 新版式",
            )
            bob_skill = create_skill(
                root,
                "bob-skill",
                "bob",
                "2026-07-24T12:00:00",
                "Bob 版式",
            )

            with (
                patch.object(site, "A_PLUS_SKILL_ROOT", root),
                patch.object(site, "execute_db_non_query") as db_delete,
            ):
                deleted = site.delete_a_plus_layout_skill("alice", "alice-new")

                self.assertEqual(deleted["skill_id"], "alice-new")
                self.assertFalse(Path(alice_new["manifest_path"]).parent.exists())
                self.assertTrue(Path(alice_old["manifest_path"]).parent.exists())
                self.assertTrue(Path(bob_skill["manifest_path"]).parent.exists())
                self.assertEqual(
                    [skill["skill_id"] for skill in site.list_a_plus_layout_skills("alice")],
                    ["alice-old"],
                )
                pointer = json.loads(
                    site.get_a_plus_layout_skill_user_pointer_path("alice").read_text(encoding="utf-8")
                )
                self.assertEqual(pointer["skill_id"], "alice-old")

                db_delete.assert_called_once()
                query, parameters = db_delete.call_args.args
                self.assertIn("DELETE TOP (1) FROM [AI_skills]", query)
                self.assertEqual(parameters[0], site.A_PLUS_SKILL_DB_TYPE)
                self.assertEqual(parameters[1], str(root))
                self.assertEqual(parameters[2], "alice")
                self.assertEqual(parameters[3], date(2026, 7, 24))

    def test_user_cannot_delete_another_users_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bob_skill = create_skill(
                root,
                "bob-skill",
                "bob",
                "2026-07-24T12:00:00",
                "Bob 版式",
            )

            with (
                patch.object(site, "A_PLUS_SKILL_ROOT", root),
                patch.object(site, "execute_db_non_query") as db_delete,
            ):
                with self.assertRaisesRegex(RuntimeError, "当前账号"):
                    site.delete_a_plus_layout_skill("alice", "bob-skill")

                db_delete.assert_not_called()
                self.assertTrue(Path(bob_skill["manifest_path"]).parent.exists())

    def test_database_failure_restores_skill_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            alice_skill = create_skill(
                root,
                "alice-skill",
                "alice",
                "2026-07-24T12:00:00",
                "Alice 版式",
            )

            with (
                patch.object(site, "A_PLUS_SKILL_ROOT", root),
                patch.object(
                    site,
                    "execute_db_non_query",
                    side_effect=RuntimeError("database unavailable"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                    site.delete_a_plus_layout_skill("alice", "alice-skill")

                self.assertTrue(Path(alice_skill["manifest_path"]).is_file())
                self.assertEqual(
                    [skill["skill_id"] for skill in site.list_a_plus_layout_skills("alice")],
                    ["alice-skill"],
                )


if __name__ == "__main__":
    unittest.main()
