"""Read and cache Feishu assistant skill definitions."""

import os
import re
from datetime import datetime
from threading import Lock

from integrations.feishu.feishu_skill_bridge import bootstrap_lark_cli_skills_env, get_skill_root_candidates


class FeishuSkillCatalog:
    def __init__(self, base_dir, ttl_seconds=120):
        self.base_dir = base_dir
        self._ttl_seconds = ttl_seconds
        self._skills = {}
        self._loaded_at = 0.0
        self._lock = Lock()


    def parse_frontmatter(self, md_text):
        text = str(md_text or "")
        m = re.match(r'^\s*---\s*\n([\s\S]*?)\n---\s*\n?', text)
        if not m:
            return {}, text.strip()
        header = m.group(1) or ""
        body = text[m.end():].strip()
        meta = {}
        for line in header.splitlines():
            s = str(line or "").strip()
            if not s or ":" not in s:
                continue
            k, v = s.split(":", 1)
            key = str(k or "").strip().lower()
            val = str(v or "").strip().strip('"').strip("'")
            if key:
                meta[key] = val
        return meta, body

    def load(self, force_refresh=False):
        now_ts = datetime.now().timestamp()
        with self._lock:
            if (not force_refresh) and self._skills and (now_ts - float(self._loaded_at or 0.0) <= self._ttl_seconds):
                return dict(self._skills)
        base_dir = self.base_dir
        bootstrap_lark_cli_skills_env(base_dir)
        candidate_dirs = get_skill_root_candidates(base_dir)
        found = {}
        for root in candidate_dirs:
            if not root or (not os.path.isdir(root)):
                continue
            try:
                skill_dirs = [os.path.join(root, n) for n in os.listdir(root)]
            except Exception:
                skill_dirs = []
            for sd in skill_dirs:
                if not os.path.isdir(sd):
                    continue
                skill_file = os.path.join(sd, "SKILL.md")
                if not os.path.isfile(skill_file):
                    continue
                try:
                    with open(skill_file, "r", encoding="utf-8") as f:
                        raw = f.read()
                except Exception:
                    continue
                meta, body = self.parse_frontmatter(raw)
                name = str(meta.get("name") or os.path.basename(sd) or "").strip()
                if not name:
                    continue
                key = name.lower()
                if key in found:
                    continue
                found[key] = {
                    "name": name,
                    "description": str(meta.get("description") or "").strip(),
                    "detail": str(body or "").strip(),
                    "path": skill_file
                }
        with self._lock:
            self._skills.clear()
            self._skills.update(found)
            self._loaded_at = now_ts
            return dict(self._skills)

    def get(self, skill_name):
        name = str(skill_name or "").strip()
        if not name:
            return None
        all_skills = self.load(force_refresh=False)
        return all_skills.get(name.lower())

    def render_list(self):
        all_skills = self.load(force_refresh=True)
        if not all_skills:
            return "当前没有可用技能。请先把技能放到 .trae/skills/<skill-name>/SKILL.md，或配置环境变量 LARK_CLI_SKILLS_DIR 指向技能目录。"
        lines = ["已加载技能："]
        for k in sorted(all_skills.keys()):
            sk = all_skills.get(k) or {}
            nm = str(sk.get("name") or k)
            desc = str(sk.get("description") or "").strip()
            if desc:
                lines.append(f"- {nm}：{desc}")
            else:
                lines.append(f"- {nm}")
        lines.append("用法：/skill 技能名 你的问题")
        return "\n".join(lines)

    def parse_invocation(self, text):
        t = str(text or "").strip()
        if not t:
            return {"mode": "", "skill": "", "question": ""}
        low = t.lower()
        if low in {"/skills", "skills", "技能列表"}:
            return {"mode": "list", "skill": "", "question": ""}
        m = re.match(r"^/(?:skill|技能)\s+([A-Za-z0-9._-]+)\s*(.*)$", t, flags=re.IGNORECASE)
        if m:
            return {"mode": "invoke", "skill": str(m.group(1) or "").strip(), "question": str(m.group(2) or "").strip()}
        m = re.match(r"^使用技能[:：\s]+([A-Za-z0-9._-]+)\s*[:：]?\s*(.*)$", t, flags=re.IGNORECASE)
        if m:
            return {"mode": "invoke", "skill": str(m.group(1) or "").strip(), "question": str(m.group(2) or "").strip()}
        return {"mode": "", "skill": "", "question": ""}
