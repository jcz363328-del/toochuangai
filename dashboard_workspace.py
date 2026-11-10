from html.parser import HTMLParser
from urllib.parse import urlsplit, parse_qsl, urlencode
from functools import lru_cache

from jinja2 import meta, nodes


CARD_CLASSES = {'module-card', 'dept-feature-card', 'quick-card', 'mini-card'}
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


def feature_anchor(title):
    value = 2166136261
    for character in title.strip():
        value = ((value ^ ord(character)) * 16777619) & 0xffffffff
    return 'workspace-feature-' + format(value, 'x')


@lru_cache(maxsize=16)
def template_catalog_context(source):
    from jinja2 import Environment
    tree = Environment().parse(source)
    flags = {name: True for name in meta.find_undeclared_variables(tree) if name.startswith('can_')}
    permissions = set()
    for comparison in tree.find_all(nodes.Compare):
        if isinstance(comparison.expr, nodes.Const) and isinstance(comparison.expr.value, str):
            for operand in comparison.ops:
                if operand.op == 'in' and isinstance(operand.expr, nodes.Getattr) and operand.expr.attr == 'fnames':
                    permissions.add(comparison.expr.value)
    return flags, permissions


class FeatureParser(HTMLParser):
    def __init__(self, href):
        super().__init__()
        self.href = href
        self.items = []
        self.stack = []
        self.scopes = []
        self.card = None
        self.index = -1

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        classes = set(attrs.get('class', '').split())
        if self.card is None and classes & CARD_CLASSES:
            self.index += 1
            self.card = {'depth': len(self.stack), 'title': attrs.get('data-menu', ''), 'named': bool(attrs.get('data-menu')), 'links': [], 'icon': '', 'permission': attrs.get('data-permission', ''), 'scopePermission': next((scope['permission'] for scope in reversed(self.scopes) if scope['permission']), ''), 'disabled': attrs.get('data-allowed') == 'false' or any(scope['disabled'] for scope in self.scopes), 'action': False, 'anchor': attrs.get('id')}
            if attrs.get('data-href'):
                self.card['links'].append(attrs['data-href'])
        if self.card is not None:
            if tag == 'i' and not self.card['icon']:
                self.card['icon'] = attrs.get('class', '')
            if tag == 'a' and attrs.get('href'):
                self.card['links'].append(attrs['href'])
            if tag == 'button' and attrs.get('onclick') and 'disabled' not in attrs:
                self.card['action'] = True
        if tag not in VOID_TAGS:
            self.stack.append((tag, classes))
            self.scopes.append({'disabled': attrs.get('data-allowed') == 'false', 'permission': attrs.get('data-permission', '')})

    def handle_data(self, data):
        if self.card and not self.card['named'] and any(tag == 'h3' or classes & {'quick-name', 'mini-name'} for tag, classes in self.stack[self.card['depth']:]):
            self.card['title'] += data

    def handle_endtag(self, tag):
        if not self.stack:
            return
        if self.stack[-1][0] == tag:
            self.stack.pop()
            self.scopes.pop()
        if self.card is not None and len(self.stack) == self.card['depth']:
            card = self.card
            self.card = None
            if card['disabled']:
                return
            links = list(dict.fromkeys(card['links']))
            if card['action']:
                links.append(self.href + '#' + (card['anchor'] or feature_anchor(card['title'])))
            for href in links:
                url = urlsplit(href)
                if not url.path.startswith('/') or url.netloc or url.scheme:
                    continue
                query = urlencode([(key, value) for key, value in parse_qsl(url.query) if key != 'source'])
                target = url.path + ('?' + query if query else '') + ('#' + url.fragment if url.fragment else '')
                self.items.append({'menu': card['title'].strip(), 'href': target, 'permission': card['permission'], 'scopePermission': card['scopePermission'], 'iconClass': card['icon'] or 'fa-solid fa-circle-dot', 'id': card['title'].strip() + '::' + target})


def extract_features(html, href):
    parser = FeatureParser(href)
    parser.feed(html)
    return list({(item['menu'], item['href']): item for item in parser.items if item['menu']}.values())
