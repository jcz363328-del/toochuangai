import sys,time,io,json
sys.path[:0]=['/tmp/a-plus-blank-fusion','/app']
from PIL import Image,ImageDraw,ImageChops
from unittest.mock import patch
from 图片 import openrouter_image_site as site
source=Image.new('RGB',(1464,2400),(255,232,236))
d=ImageDraw.Draw(source)
d.rectangle((0,0,1463,749),fill=(30,40,50))
d.rectangle((0,0,60,2399),fill=(70,20,50))
d.rectangle((1403,0,1463,2399),fill=(70,20,50))
d.rectangle((0,2280,1463,2399),fill=(35,45,55))
d.rectangle((700,1000,1150,1400),fill=(245,222,226))
d.text((180,900),'ORIGINAL LABEL',fill=(253,230,234),font_size=48)
t0=time.monotonic()
mask=site.build_first_screen_fill_mask(source)
bounds=site.find_first_screen_safe_region(mask)
assert mask.crop((700,1000,1151,1401)).getextrema()==(0,0)
assert mask.getpixel((100,1900))==255
assert mask.crop(bounds).getextrema()==(255,255)
original=io.BytesIO();source.save(original,format='PNG')
region=(bounds[2]-bounds[0],bounds[3]-bounds[1])
generated=Image.new('RGB',region,(245,230,240));draw=ImageDraw.Draw(generated)
for box,color in [((0,0,35,35),'red'),((region[0]-36,0,region[0]-1,35),'green'),((0,region[1]-36,35,region[1]-1),'blue'),((region[0]-36,region[1]-36,region[0]-1,region[1]-1),'yellow')]:draw.rectangle(box,fill=color)
buf=io.BytesIO();generated.save(buf,format='PNG')
with patch.object(site,'call_openrouter_images_api',return_value={'images':[site.image_bytes_to_data_url(buf.getvalue(),'image/png')]}):
 result=site.run_first_screen_selling_points_job({'uploaded_files':[{'data':original.getvalue(),'name':'base.png','type':'image/png'},{'data':buf.getvalue(),'name':'material.png','type':'image/png'}],'model':site.NANO_BANANA_MODEL})
data,_=site.load_image_bytes_from_url(result['images'][0]);output=Image.open(io.BytesIO(data)).convert('RGB')
diff=ImageChops.difference(source,output);diff.paste(0,bounds)
assert diff.getbbox() is None
source.save('/tmp/a-plus-blank-fusion/test-original.png');output.save('/tmp/a-plus-blank-fusion/test-composite.png')
print(json.dumps({'passed':True,'source_size':source.size,'safe_bounds':bounds,'seconds':round(time.monotonic()-t0,2),'external_pixels_unchanged':True}))
