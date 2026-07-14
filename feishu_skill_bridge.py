import os
import re


def _norm_abs(path_text):
    p = str(path_text or "").strip()
    if not p:
        return ""
    return os.path.abspath(os.path.expanduser(p))


def _split_env_paths(text):
    raw = str(text or "").strip()
    if not raw:
        return []
    out = []
    seen = set()
    for part in re.split(r"[;,]", raw):
        p = _norm_abs(part)
        if not p:
            continue
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out


def get_skill_root_candidates(project_base_dir):
    base_dir = _norm_abs(project_base_dir)
    home = _norm_abs("~")
    user_profile = _norm_abs(os.environ.get("USERPROFILE") or home)
    appdata = _norm_abs(os.environ.get("APPDATA") or "")
    candidates = [
        _norm_abs(os.environ.get("LARK_CLI_SKILLS_DIR") or ""),
        _norm_abs(os.path.join(base_dir, ".trae", "skills")),
        _norm_abs(os.path.join(base_dir, "skills")),
        _norm_abs(os.path.join(base_dir, "larksuite", "cli", "skills")),
        _norm_abs(os.path.join(base_dir, "larksuite-cli", "skills")),
        _norm_abs(os.path.join(user_profile, ".agents", "skills")),
        _norm_abs(os.path.join(user_profile, ".skills", "larksuite-cli")),
        _norm_abs(os.path.join(appdata, "npm", "node_modules", "@larksuite", "cli", "skills")),
    ]
    out = []
    seen = set()
    for p in candidates + _split_env_paths(os.environ.get("LARK_CLI_SKILLS_EXTRA_DIRS") or ""):
        p2 = _norm_abs(p)
        if not p2:
            continue
        k = p2.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(p2)
    return out


def bootstrap_lark_cli_skills_env(project_base_dir):
    current = str(os.environ.get("LARK_CLI_SKILLS_DIR") or "").strip()
    if current and os.path.isdir(_norm_abs(current)):
        return _norm_abs(current), "already_set"
    for p in get_skill_root_candidates(project_base_dir):
        if os.path.isdir(p):
            os.environ["LARK_CLI_SKILLS_DIR"] = p
            return p, "auto_set"
    return "", "not_found"
