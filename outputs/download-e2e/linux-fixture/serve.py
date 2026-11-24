import asyncio
import functools
import os
import sys
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]
sys.path[:0] = [str(ROOT)]
os.environ['TC_SINGLE_PORT'] = '1'
from aiohttp import web, ClientSession, WSMsgType
from 图片 import openrouter_image_site as site

handler = functools.partial(site.JimengStaticRequestHandler,
        upload_directory=str(FOLDER/'uploads'), history_directory=str(FOLDER/'history'))
static_server = ThreadingHTTPServer(('127.0.0.1',18582), handler)
threading.Thread(target=static_server.serve_forever, daemon=True).start()
foreign_server = ThreadingHTTPServer(('127.0.0.1',18583),functools.partial(SimpleHTTPRequestHandler,directory=str(FOLDER/'history/a')))
threading.Thread(target=foreign_server.serve_forever,daemon=True).start()

async def proxy(request):
    static = request.path.startswith(('/history_images/', '/jimeng_uploads/'))
    backend = f'http://127.0.0.1:{18582 if static else 18581}{request.rel_url}'
    if not request.path.startswith('/static/'):
        print('REQUEST',request.method,str(request.rel_url),flush=True)
    headers = {k:v for k,v in request.headers.items() if k.lower() not in ('host','content-length','connection','upgrade')}
    if request.headers.get('Upgrade','').lower() == 'websocket':
        protocols = [v.strip() for v in request.headers.get('Sec-WebSocket-Protocol','').split(',') if v.strip()]
        ws = web.WebSocketResponse(protocols=protocols)
        await ws.prepare(request)
        async with ClientSession() as session:
            async with session.ws_connect(backend, protocols=protocols, headers={'Origin':'http://127.0.0.1:18581'}) as upstream:
                async def relay(source, dest):
                    async for msg in source:
                        if msg.type == WSMsgType.TEXT: await dest.send_str(msg.data)
                        elif msg.type == WSMsgType.BINARY: await dest.send_bytes(msg.data)
                        elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR): break
                    await dest.close()
                await asyncio.gather(relay(ws,upstream), relay(upstream,ws))
        return ws
    async with ClientSession() as session:
        async with session.request(request.method, backend, headers=headers, data=await request.read()) as upstream:
            body = await upstream.read()
            if not request.path.startswith('/static/'):
                print('RESPONSE',upstream.status,str(request.rel_url),len(body),flush=True)
            response_headers = {k:v for k,v in upstream.headers.items() if k.lower() not in ('content-length','transfer-encoding','content-encoding','connection')}
            return web.Response(status=upstream.status, body=body, headers=response_headers)

app = web.Application()
app.router.add_route('*','/{tail:.*}', proxy)
web.run_app(app,host='0.0.0.0',port=18580,print=lambda *args: print(*args,flush=True))
