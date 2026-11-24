import hashlib
import sys
from pathlib import Path
from urllib.parse import urlsplit
folder = Path(__file__).parent
root = folder.parents[1]
sys.path.insert(0, str(root / 'outputs/qa-browser-deps'))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=str(next((root / 'outputs/qa-browser-binaries/chromium-1255').rglob('chrome.exe'))), headless=True)
    page = browser.new_page(accept_downloads=True)
    errors = []
    page.on('pageerror', lambda error: (errors.append(str(error)), print('PAGE ERROR:', error, flush=True)))
    page.set_default_timeout(10000)
    def respond(route):
        path = urlsplit(route.request.url).path
        if path.startswith('/original/'):
            route.fulfill(content_type='image/png', body=(folder / Path(path).name).read_bytes())
        elif path in ('/first', '/second'):
            route.fulfill(content_type='text/html', body=(folder / f'{path[1:]}.html').read_text(encoding='utf-8'))
        else:
            route.fulfill(content_type='text/html', body='<iframe id="first" src="/first" height="200"></iframe><iframe id="second" src="/second" height="200"></iframe>')
    page.route('**/*', respond)
    page.goto('http://history.test/')
    for gallery, index, name in [('first', 0, 'a'), ('second', 0, 'b'), ('first', 1, 'c'), ('second', 0, 'b')]:
        page.frame_locator('#' + gallery).locator('.zoom-thumb').nth(index).click()
        for context_menu in (False, True):
            with page.expect_download() as download_info:
                if context_menu:
                    page.locator('#lashforge-fullscreen-image').click(button='right', modifiers=['Alt'])
                    page.locator('#lashforge-download-image').click()
                else:
                    page.locator('#lashforge-fullscreen-download').click()
            download = download_info.value
            assert download.suggested_filename == f'{name}-original.png', download.suggested_filename
            assert Path(download.path()).read_bytes() == (folder / f'{name}.png').read_bytes()
        page.locator('#lashforge-fullscreen-close').click()
        print(f'{gallery}/{index}: button and context-menu filename + original bytes verified', flush=True)
    assert not errors, errors
    print('PASS: 8 actual downloads match the selected original', flush=True)
    browser.close()
