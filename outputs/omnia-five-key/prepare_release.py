import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
spec = importlib.util.spec_from_file_location("patch_canvas", ROOT / "patch_canvas.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
NEW_MODULES = ["omnia_key_pool.py", "omnia_cost_ledger.py", "omnia_service.py",
               "balance_management.py", "balance_provider.py", "balance_view.py"]
MODIFIED = ["openrouter_image_site.py", "request_limits.py", "canvas_api_proxy.py"]
previous_outputs = {name: (ROOT / "local-release" / name).read_bytes()
                    for name in MODIFIED if (ROOT / "local-release" / name).exists()}

for target in ("local", "runtime", "image"):
    dest = ROOT / f"{target}-release"
    with (ROOT / f"before-{target}" / "canvas_api_proxy.py").open(encoding="utf-8-sig", newline="") as stream:
        canvas = module.patch(stream.read())
    with (dest / "canvas_api_proxy.py").open("w", encoding="utf-8", newline="") as stream:
        stream.write(canvas)
    for name in NEW_MODULES:
        shutil.copy2(PROJECT / "图片" / name, dest / name)
    manifest = []
    for name in MODIFIED + NEW_MODULES:
        compile((dest / name).read_text(encoding="utf-8-sig"), name, "exec")
        before = ROOT / f"before-{target}" / name
        manifest.append({"name": name, "before": hashlib.sha256(before.read_bytes()).hexdigest() if before.exists() else None,
                         "after": hashlib.sha256((dest / name).read_bytes()).hexdigest()})
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

for name in MODIFIED:
    current = PROJECT / "图片" / name
    assert current.read_bytes() in ((ROOT / "before-local" / name).read_bytes(),
                                    (ROOT / "local-release" / name).read_bytes(),
                                    previous_outputs.get(name)), "Local file changed during preparation"
    shutil.copy2(ROOT / "local-release" / name, current)
print("Three independently patched release trees prepared; local source updated")
