import unittest
from pathlib import Path


SOURCE = Path("图片/openrouter_image_site.py").read_text(encoding="utf-8-sig")


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
        function_start = SOURCE.index("def prepare_openrouter_uploaded_input")
        function_end = SOURCE.index("\ndef prepare_ark_seedream_uploaded_input", function_start)
        function_source = SOURCE[function_start:function_end]
        self.assertIn("len(image_bytes) <= OPENROUTER_SAFE_INPUT_TARGET_BYTES", function_source)


if __name__ == "__main__":
    unittest.main()
