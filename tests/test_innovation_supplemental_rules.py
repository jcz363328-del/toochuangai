import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGE_SOURCE = (ROOT / "innovation" / "templates" / "manage.html").read_text(encoding="utf-8")


class InnovationSupplementalRulesTests(unittest.TestCase):
    def test_supplemental_rules_button_opens_its_modal(self):
        self.assertIn('data-bs-target="#supplementalRulesModal"', MANAGE_SOURCE)
        self.assertIn('<i class="bi bi-journal-text"></i> 补充条例', MANAGE_SOURCE)
        self.assertIn('id="supplementalRulesModal"', MANAGE_SOURCE)
        self.assertIn('modal-dialog modal-lg modal-dialog-scrollable', MANAGE_SOURCE)

    def test_both_guidance_buttons_are_available_at_each_score_field(self):
        handle_score = MANAGE_SOURCE.split(
            '<div class="mb-3" id="scoreGroup">', 1
        )[1].split('<select class="form-select" id="handleScore"', 1)[0]
        committee_score = MANAGE_SOURCE.split(
            '<label for="committeeScoreSelect"', 1
        )[1].split('<select class="form-select" id="committeeScoreSelect"', 1)[0]

        for location, source in (
            ("handle score", handle_score),
            ("committee score", committee_score),
        ):
            with self.subTest(location=location):
                self.assertIn('data-stacked-modal-target="#scoreGuideModal"', source)
                self.assertIn("onclick=\"openStackedModal('scoreGuideModal')\"", source)
                self.assertIn('评分标准说明', source)
                self.assertIn('data-stacked-modal-target="#supplementalRulesModal"', source)
                self.assertIn("onclick=\"openStackedModal('supplementalRulesModal')\"", source)
                self.assertIn('补充条例', source)

    def test_scoring_references_stack_without_hiding_parent_modal(self):
        stack_helper = MANAGE_SOURCE.split(
            "function openStackedModal(modalId)", 1
        )[1].split("document.addEventListener('DOMContentLoaded'", 1)[0]
        self.assertIn("document.querySelectorAll('.modal.show')", stack_helper)
        self.assertIn("targetModal.style.zIndex = String(targetZIndex)", stack_helper)
        self.assertIn("topBackdrop.style.zIndex = String(targetZIndex - 5)", stack_helper)
        self.assertIn("document.body.classList.add('modal-open')", stack_helper)
        self.assertIn("stackedParent.focus()", stack_helper)
        self.assertNotIn("parentInstance.hide", stack_helper)

    def test_status_changes_preserve_handle_score_buttons(self):
        conditional_fields = MANAGE_SOURCE.split(
            "function updateHandleConditionalFields()", 1
        )[1].split("// 图片预览", 1)[0]
        self.assertIn("const labelText = document.getElementById('handleScoreLabelText')", conditional_fields)
        self.assertIn("labelText.textContent = '提案评分'", conditional_fields)
        self.assertIn("requiredMark.classList.add('d-none')", conditional_fields)
        self.assertNotIn("label.innerHTML", conditional_fields)

    def test_modal_contains_all_fourteen_rules(self):
        for rule_number in range(1, 15):
            with self.subTest(rule_number=rule_number):
                self.assertEqual(
                    MANAGE_SOURCE.count(f'data-rule-number="{rule_number}"'),
                    1,
                )

        expected_policy_text = (
            "24 小时内 5000+ 浏览量可以提创新",
            "对于 AI 工具（含美工/摄影工单系统）的提案",
            "统一按照 10 分处理",
            "提案需获得 11 票及以上方可通过",
            "算作重复提案",
            "计 30 分",
            "关于 SOP 类的提案",
            "对于工作流程性/新人带教类的 SOP",
            "属于业务原本就已执行，后续才梳理补落地的情况",
            "统一按 0 分处理",
        )
        for text in expected_policy_text:
            with self.subTest(text=text):
                self.assertIn(text, MANAGE_SOURCE)


if __name__ == "__main__":
    unittest.main()
