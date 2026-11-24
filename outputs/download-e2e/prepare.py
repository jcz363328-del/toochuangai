from pathlib import Path
from PIL import Image, ImageDraw
FOLDER = Path(__file__).resolve().parent
for sub, ext, color in [('a','png','#e25649'),('b','png','#2b80dd'),('c','jpg','#2aad70')]:
    directory = FOLDER/'history'/sub
    directory.mkdir(parents=True, exist_ok=True)
    image = Image.new('RGB',(2400,1600),color)
    draw = ImageDraw.Draw(image)
    for i in range(0,2400,37): draw.line((i,0,2400-i,1600),fill='white',width=3)
    draw.text((50,50),sub+' ORIGINAL 2400x1600',fill='black',stroke_width=3)
    image.save(directory/('photo.jpg' if ext=='jpg' else 'result.png'))
(FOLDER/'uploads').mkdir(exist_ok=True)
print('Prepared three original 2400x1600 images')
