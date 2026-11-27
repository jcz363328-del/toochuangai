"""Parse report card text and embedded image references."""

import re
from html.parser import HTMLParser


class CardSourceParser(HTMLParser):
    def __init__(self, image_paths, *, clean_text, normalize_path, image_name):
        super().__init__(convert_charrefs=True)
        self.clean_text = clean_text
        self.normalize_path = normalize_path
        self.image_name = image_name
        self.image_paths = list(image_paths or [])
        self.used_paths = set()
        self.image_cursor = 0
        self.skip_depth = 0
        self.segments = []
        self.text_parts = []

    def _append_text(self, text):
        if text:
            self.text_parts.append(str(text))

    def _flush_text(self):
        text = self.clean_text("".join(self.text_parts))
        self.text_parts = []
        if text:
            self.segments.append({"type": "text", "content": text})

    def _next_fallback_image(self):
        while self.image_cursor < len(self.image_paths):
            path = str(self.image_paths[self.image_cursor] or "").strip()
            self.image_cursor += 1
            if not path or path in self.used_paths:
                continue
            self.used_paths.add(path)
            return path
        return ""

    def _resolve_image_path(self, attrs):
        attrs = attrs or {}
        candidates = [
            attrs.get("src"),
            attrs.get("data-src"),
            attrs.get("data-local-image"),
            attrs.get("data-origin-src"),
        ]
        for raw in candidates:
            txt = str(raw or "").strip().strip("`").strip("\"'")
            if not txt:
                continue
            norm = self.normalize_path(txt)
            base = self.image_name(txt)
            for path in self.image_paths:
                if not path or path in self.used_paths:
                    continue
                if self.normalize_path(path) == norm or (base and self.image_name(path) == base):
                    self.used_paths.add(path)
                    return path
        return self._next_fallback_image()

    def handle_starttag(self, tag, attrs):
        tag = str(tag or "").lower()
        attrs_map = {str(k or "").lower(): v for k, v in (attrs or [])}
        if tag in {"script", "style", "svg"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "br":
            self._append_text("\n")
            return
        if tag == "img":
            image_path = self._resolve_image_path(attrs_map)
            self._flush_text()
            if image_path:
                self.segments.append({"type": "image", "path": image_path})
            return
        if tag in {"div", "p", "section", "article", "header", "footer", "blockquote", "pre", "table", "thead", "tbody", "tr"}:
            self._append_text("\n")
            return
        if tag in {"td", "th"}:
            self._append_text(" ")
            return
        if tag in {"strong", "b"}:
            self._append_text("**")
            return
        if tag in {"em", "i"}:
            self._append_text("*")
            return
        if tag == "li":
            marker = str(attrs_map.get("data-index") or "").strip() or "-"
            self._append_text("\n" + marker + " ")
            return
        if re.fullmatch(r"h[1-6]", tag):
            level = int(tag[-1])
            self._append_text("\n" + ("#" * max(1, level)) + " ")

    def handle_endtag(self, tag):
        tag = str(tag or "").lower()
        if tag in {"script", "style", "svg"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in {"div", "p", "section", "article", "header", "footer", "blockquote", "pre", "table", "thead", "tbody", "tr", "li", "ol", "ul"}:
            self._append_text("\n")
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._append_text("\n")
            return
        if tag in {"strong", "b"}:
            self._append_text("**")
            return
        if tag in {"em", "i"}:
            self._append_text("*")

    def handle_data(self, data):
        if self.skip_depth:
            return
        self._append_text(data)

    def close(self):
        super().close()
        self._flush_text()
