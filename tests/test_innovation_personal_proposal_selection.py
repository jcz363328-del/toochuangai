import unittest

from innovation.dashboard_rankings import select_personal_proposal_performers


class PersonalProposalSelectionTests(unittest.TestCase):
    def test_selects_effective_rate_top_three_only_from_total_top_five(self):
        rows = [
            ("A", "AI部", 20, 10, 0.50),
            ("B", "AI部", 19, 8, 0.80),
            ("C", "AI部", 18, 7, 0.70),
            ("D", "AI部", 17, 6, 0.60),
            ("E", "AI部", 16, 15, 0.90),
            ("F", "AI部", 15, 15, 1.00),
        ]

        selected = select_personal_proposal_performers(rows)

        self.assertEqual(["E", "B", "C"], [item["name"] for item in selected])
        self.assertNotIn("F", [item["name"] for item in selected])

    def test_keeps_everyone_tied_with_third_effective_rate(self):
        rows = [
            ("A", "AI部", 20, 10, 0.90),
            ("B", "AI部", 19, 9, 0.80),
            ("C", "AI部", 18, 8, 0.70),
            ("D", "AI部", 17, 7, 0.70),
            ("E", "AI部", 16, 3, 0.20),
            ("F", "AI部", 15, 15, 1.00),
        ]

        selected = select_personal_proposal_performers(rows)

        self.assertEqual(["A", "B", "C", "D"], [item["name"] for item in selected])

    def test_total_top_five_keeps_everyone_tied_at_fifth_place(self):
        rows = [
            ("F", "AI部", 10, 10, 1.0),
            ("E", "AI部", 10, 1, 0.1),
            ("D", "AI部", 10, 2, 0.2),
            ("C", "AI部", 10, 3, 0.3),
            ("B", "AI部", 10, 4, 0.4),
            ("A", "AI部", 10, 5, 0.5),
        ]

        selected = select_personal_proposal_performers(rows)

        self.assertEqual(["F", "A", "B"], [item["name"] for item in selected])

    def test_both_total_fifth_and_effective_third_allow_ties(self):
        rows = [
            ("A", "AI部", 20, 18, 0.9),
            ("B", "AI部", 19, 15, 0.8),
            ("C", "AI部", 18, 12, 0.7),
            ("D", "AI部", 17, 7, 0.4),
            ("E", "AI部", 16, 8, 0.5),
            ("F", "AI部", 16, 7, 0.7),
            ("G", "AI部", 15, 15, 1.0),
        ]

        selected = select_personal_proposal_performers(rows)

        self.assertEqual(["A", "B", "C", "F"], [item["name"] for item in selected])
        self.assertNotIn("G", [item["name"] for item in selected])


if __name__ == "__main__":
    unittest.main()
