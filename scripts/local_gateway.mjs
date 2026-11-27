import http from "node:http";

const host = "127.0.0.1";
const port = 8000;
const assets = ["/infinite-canvas/", "/jimeng_uploads/", "/history_images/"];
const withSlash = new Set(["/lashforge", "/infinite-canvas"]);

function pathOf(request) {
  return request.url.split("?", 1)[0];
}

function upstream(request) {
  const path = pathOf(request);
  const target = path.startsWith("/lashforge/") ? 8501
    : assets.some(prefix => path.startsWith(prefix)) ? 8502 : 8100;
  return http.request({
    host,
    port: target,
    path: request.url,
    method: request.method,
    headers: {
      ...request.headers,
      "x-forwarded-host": request.headers.host || "localhost:8000",
      "x-forwarded-proto": "http",
      "x-forwarded-for": request.socket.remoteAddress,
    },
  });
}

const server = http.createServer((request, response) => {
  const path = pathOf(request);
  if (withSlash.has(path)) {
    response.writeHead(302, { location: path + "/" + request.url.slice(path.length) }).end();
    return;
  }
  const proxy = upstream(request);
  proxy.on("response", result => {
    response.writeHead(result.statusCode, result.headers);
    result.pipe(response);
  });
  proxy.on("error", () => {
    if (!response.headersSent) response.writeHead(502);
    response.end("Local service unavailable");
  });
  response.on("close", () => proxy.destroy());
  request.pipe(proxy);
});

server.on("upgrade", (request, socket, head) => {
  if (!pathOf(request).startsWith("/lashforge/")) {
    socket.end("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n");
    return;
  }
  const proxy = upstream(request);
  proxy.on("upgrade", (response, upstreamSocket, upstreamHead) => {
    let headers = `HTTP/1.1 ${response.statusCode} ${response.statusMessage}\r\n`;
    for (let i = 0; i < response.rawHeaders.length; i += 2) {
      headers += `${response.rawHeaders[i]}: ${response.rawHeaders[i + 1]}\r\n`;
    }
    socket.write(headers + "\r\n");
    if (upstreamHead.length) socket.write(upstreamHead);
    if (head.length) upstreamSocket.write(head);
    upstreamSocket.on("error", () => socket.destroy());
    socket.on("close", () => upstreamSocket.destroy());
    upstreamSocket.on("close", () => socket.destroy());
    socket.pipe(upstreamSocket).pipe(socket);
  });
  proxy.on("response", response => {
    response.resume();
    socket.end(`HTTP/1.1 ${response.statusCode} ${response.statusMessage}\r\nConnection: close\r\n\r\n`);
  });
  proxy.on("error", () => socket.destroy());
  socket.on("error", () => proxy.destroy());
  socket.on("close", () => proxy.destroy());
  proxy.end();
});

server.listen(port, host);
