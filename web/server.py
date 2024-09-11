import asyncio
import os
import pathlib
import logging
from string import Template

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)

clients = set()

path_to_static_dir = pathlib.Path(__file__).parent.resolve() / "static"


async def index(request):
    del request
    path_to_index = path_to_static_dir / "index.html"
    return web.FileResponse(str(path_to_index))


async def visualizer(request):
    del request
    ip = os.getenv("WEB_SERVER_EXTERNAL_IP", "localhost")
    path_to_js = path_to_static_dir / "visualizer.js"
    content = Template(path_to_js.read_text())

    return web.Response(
        text=content.safe_substitute(server=ip), content_type="text/javascript"
    )


async def websocket_handler(request):
    web_socket = web.WebSocketResponse()
    await web_socket.prepare(request)
    clients.add(web_socket)

    async for msg in web_socket:
        if msg.type == aiohttp.WSMsgType.TEXT:
            if msg.data == "close":
                clients.discard(web_socket)
                await web_socket.close()
            else:
                for other_web_socket in filter(
                    lambda c: c != web_socket, clients.copy()
                ):
                    if other_web_socket.closed:
                        clients.discard(other_web_socket)
                        continue
                    await other_web_socket.send_str(msg.data)
        elif msg.type == aiohttp.WSMsgType.ERROR:
            print("ws connection closed with exception %s" % web_socket.exception())

    return web_socket


def create_runner():
    app = web.Application()
    app.add_routes(
        [
            web.get("/", index),
            web.get("/static/visualizer.js", visualizer),
            web.get("/ws", websocket_handler),
        ]
    )
    return web.AppRunner(app)


async def start_server(host="0.0.0.0", port=5555):
    logger.info(f"server is started: {host}:{port}")
    runner = create_runner()
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(start_server())
        loop.run_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    logging.basicConfig(
        format="[%(asctime)s] %(name)s %(levelname)s in "
        "%(filename)s:%(lineno)d : %(message)s"
    )
    logging.getLogger().setLevel(logging.INFO)
    main()
