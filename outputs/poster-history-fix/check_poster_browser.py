import io
from PIL import Image
from playwright.sync_api import sync_playwright, expect

def png(name,color):
 out=io.BytesIO();Image.new('RGB',(320,240),color).save(out,format='PNG')
 return {'name':name,'mimeType':'image/png','buffer':out.getvalue()}

with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1080})
 page.goto('http://127.0.0.1:18613/')
 inputs=page.locator('input[type=file]')
 expect(inputs).to_have_count(4)
 for i,color in enumerate(['blue','red','green','gold']):
  inputs.nth(i).set_input_files(png(f'role-{i+1}.png',color))
  expect(page.locator('.upload-frame-meta')).to_have_count(i+1)
  expect(inputs).to_have_count(4)
 expect(page.get_by_role('button',name='生成融合海报',exact=True)).to_be_enabled()
 def metas():return page.locator('.upload-frame-meta').evaluate_all('els=>els.map(e=>({name:e.dataset.filename,source:e.dataset.source,remove:e.dataset.removeKey}))')
 original=metas()
 assert [m['name'] for m in original]==[f'role-{i}.png' for i in range(1,5)],original
 assert all(m['remove'].startswith('clear_upload_poster_fusion_') for m in original)
 page.get_by_text('批量高清',exact=True).first.click()
 expect(page.get_by_text('上传与设置',exact=True)).to_be_visible()
 page.get_by_text('海报融合',exact=True).first.click()
 expect(page.locator('.upload-frame-meta')).to_have_count(4)
 assert metas()==original
 zones=page.locator('[data-testid=stFileUploaderDropzone]')
 zones.nth(1).click(button='right')
 menu=page.locator('.xiaoha-image-menu')
 expect(menu.get_by_role('button',name='移除图片',exact=True)).to_be_visible()
 page.screenshot(path='/tmp/poster-history-fix/reference-menu.png',full_page=True)
 menu.get_by_role('button',name='移除图片',exact=True).click()
 expect(page.locator('.upload-frame-meta')).to_have_count(3)
 expect(page.get_by_role('button',name='生成融合海报',exact=True)).to_be_disabled()
 assert metas()==[original[0],original[2],original[3]]
 page.get_by_text('批量高清',exact=True).first.click()
 expect(page.get_by_text('上传与设置',exact=True)).to_be_visible()
 page.get_by_text('海报融合',exact=True).first.click()
 expect(page.locator('.upload-frame-meta')).to_have_count(3)
 assert metas()==[original[0],original[2],original[3]]
 inputs.nth(1).set_input_files(png('reuploaded.png','purple'))
 expect(page.locator('.upload-frame-meta')).to_have_count(4)
 expect(page.get_by_role('button',name='生成融合海报',exact=True)).to_be_enabled()
 zones.nth(1).click(button='right')
 with page.expect_file_chooser() as chooser:
  page.locator('.xiaoha-image-menu').get_by_role('button',name='更换图片',exact=True).click()
 chooser.value.set_files(png('replacement.png','black'))
 expect(page.locator('.upload-frame-meta').nth(1)).to_have_attribute('data-filename','replacement.png')
 page.get_by_text('批量高清',exact=True).first.click()
 expect(page.get_by_text('上传与设置',exact=True)).to_be_visible()
 page.get_by_text('海报融合',exact=True).first.click()
 expect(page.locator('.upload-frame-meta').nth(1)).to_have_attribute('data-filename','replacement.png')
 current=metas()
 for i in (0,2,3):assert current[i]==original[i]
 for index in (3,2,0):
  zones.nth(index).click(button='right')
  page.locator('.xiaoha-image-menu').get_by_role('button',name='移除图片',exact=True).click()
  expect(page.locator('.upload-frame-meta')).to_have_count({3:3,2:2,0:1}[index])
 assert metas()[0]['name']=='replacement.png'
 assert page.locator('[data-testid=stException]').count()==0
 print('PASS: four uploads persist across navigation; reference delete stays removed; each role deletes independently; reupload and context-menu replacement persist; original role order preserved')
 browser.close()
