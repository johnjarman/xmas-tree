#! /usr/bin/python3

import asyncio
import json
import websockets
import colorzero
import time


class XmasTreeServer:
    def __init__(self):
        self.update_needed = False
        self.current_mode = 'manual'
        self.colour1 = colorzero.Color('#FA0')
        self.colour2 = colorzero.Color('#F00')
        self.brightness = 0.1
        self.last_time = time.time()

    async def tree_mainloop(self):
        while True:
            if self.current_mode == 'colourcycle':
                if time.time() - self.last_time > 0.1:
                    self.last_time = time.time()
                    self.colour2 += colorzero.Hue(deg=1)
                    print(self.colour2.html)
                    await self.send_ui_update({'colour2':self.colour2.html})

            await asyncio.sleep(0.01)

    async def consumer(self, message):
        msg = json.loads(message)
        print(msg)
        if 'mode' in msg.keys():
            self.current_mode = msg['mode']

        if 'colour1' in msg.keys():
            self.colour1 = colorzero.Color(msg['colour1'])

        if 'colour2' in msg.keys():
            self.colour2 = colorzero.Color(msg['colour2'])
            if self.current_mode != 'manual':
                await self.send_ui_update({'mode':'manual'})
                self.current_mode = 'manual'

        if 'brightness' in msg.keys():
            self.brightness = msg['brightness']

        if 'cmd' in msg.keys():
            if msg['cmd'] == 'request_update':
                await self.send_ui_update({
                    'mode':self.current_mode,
                    'colour1':self.colour1.html,
                    'colour2':self.colour2.html,
                    'brightness':self.brightness
                })

    async def send_ui_update(self, update):
        try:
            await self.websocket.send(json.dumps(update))
        except websockets.exceptions.ConnectionClosed:
            pass

    async def consumer_handler(self):
        async for message in self.websocket:
            await self.consumer(message)

    async def handler(self, websocket, path):
        self.websocket = websocket
        consumer_task = asyncio.create_task(self.consumer_handler())
        tree_task = asyncio.create_task(self.tree_mainloop())
        await asyncio.wait([consumer_task, tree_task])

        
tree_server = XmasTreeServer()

start_server = websockets.serve(tree_server.handler, 'localhost', 6789)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()