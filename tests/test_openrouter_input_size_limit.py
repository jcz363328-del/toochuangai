import unittest
import ast
from pathlib import Path


SOURCE = Path("Department/视觉设计部/xiaoha/openrouter_image_site.py").read_text(encoding="utf-8-sig")


class OpenRouterInputSizeLimitTests(unittest.TestCase):
    def test_raw_safe_target_fits_thirty_mb_after_base64(self):
        namespace = {}
        exec(
            "\n".join(
                line for line in SOURCE.splitlines()
                if line.startswith("OPENROUTER_MAX_INPUT_IMAGE_BYTES =")
                or line.startswith("OPENROUTER_SAFE_INPUT_TARGET_BYTES =")
            ),
            namespace,
        )
        safe_bytes = namespace["OPENROUTER_SAFE_INPUT_TARGET_BYTES"]
        encoded_length = 4 * ((safe_bytes + 2) // 3)
        self.assertLess(encoded_length, 30_000_000)

    def test_early_return_uses_base64_safe_target(self):
        entrypoint = next(
            node for node in ast.parse(SOURCE).body
            if isinstance(node, ast.FunctionDef) and node.name == "prepare_openrouter_uploaded_input"
        )
        self.assertEqual(ast.unparse(entrypoint.args.defaults[-1]), "OPENROUTER_SAFE_INPUT_TARGET_BYTES")
        implementation = Path("Department/视觉设计部/xiaoha/image_inputs.py").read_text(encoding="utf-8")
        function_source = implementation.split("def prepare_openrouter_uploaded_input(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("limit = max(OPENROUTER_INPUT_MIN_BUDGET_BYTES, int(max_bytes or 0))", function_source)
        self.assertIn("len(image_bytes) <= limit", function_source)


if __name__ == "__main__":
    unittest.main()
