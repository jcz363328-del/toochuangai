import re
import sys
from pathlib import Path

ROOT = Path(".")
sys.path.insert(0, ".codex-vba-tools")
from oletools.olevba import VBA_Parser


def containing_procedure(lines: list[str], index: int) -> tuple[int, int]:
    start = index
    while start >= 0 and not re.match(
        r"^\s*(?:Public\s+|Private\s+|Friend\s+)?(?:Sub|Function)\b",
        lines[start],
        re.I,
    ):
        start -= 1
    end = index + 1
    while end < len(lines) and not re.match(
        r"^\s*End\s+(?:Sub|Function)\b", lines[end], re.I
    ):
        end += 1
    return max(start, 0), min(end + 1, len(lines))


terms = sys.argv[1:] or ["整理并导入赛狐订单"]
pattern = re.compile("|".join(map(re.escape, terms)), re.I)
workbooks = sorted(ROOT.glob("*.xlsm"))
if not workbooks:
    raise SystemExit("No .xlsm workbook found")

parser = VBA_Parser(str(workbooks[0]))
seen: set[tuple[str, int, int]] = set()
try:
    for _, stream_path, vba_filename, code in parser.extract_macros():
        lines = code.splitlines()
        for i, line in enumerate(lines):
            if not pattern.search(line):
                continue
            start, end = containing_procedure(lines, i)
            key = (stream_path, start, end)
            if key in seen:
                continue
            seen.add(key)
            print(
                f"===== {vba_filename} ({stream_path}) "
                f"lines {start + 1}-{end} ====="
            )
            print("\n".join(lines[start:end]))
            print()
finally:
    parser.close()
