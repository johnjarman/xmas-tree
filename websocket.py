#! /usr/bin/python3

import asyncio
import json
import websockets
import colorzero
import datetime
import time
from multiprocessing import Process, Queue
from queue import Full


class XmasTreeHardware(Process):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def run(self):
        print('running')
        while True:
            msg = self.queue.get()
            if isinstance(msg, str):
                if msg == 'stop':
                    break
            print('trig')
            time.sleep(1)


class XmasTreeServer:
    def __init__(self):
        self.update_needed = False
        self.current_mode = 'manual'
        self.colour1 = colorzero.Color('#FB0')
        self.colour2 = colorzero.Color('#60F')
        self.brightness = 0.1
        self.hw_lock = False
        self.hw_queue = Queue(1)
        self.hw_process = XmasTreeHardware(self.hw_queue)
        self.hw_process.start()

        self.frame = []

    #def __del__(self):
    #    self.hw_queue.put('stop')
    #    self.hw_process.join()
    #    print('shutdown hw thread')

    async def frame_sender(self):
        while True:
            try:
                self.hw_queue.put(14, False)
            except Full:
                print('full')
            await asyncio.sleep(0.1)

    async def colour_cycle(self):
        """ Cycle through hues """
        while self.current_mode == 'colourcycle':
            self.colour2 += colorzero.Hue(deg=1)
            await self.send_ui_update({'colour2':self.colour2.html})
            await asyncio.sleep(0.1)

    async def dawn_dusk_cycle(self):
        """ Run a slow change of colour through the day """
        pass

    def set_mode(self, mode):
        if mode != self.current_mode:
            # mode-change needed
            self.current_mode = mode

            if mode == 'colourcycle':
                asyncio.create_task(self.colour_cycle())

    async def set_colour2(self, colour):
        pass

    async def consumer(self, message):
        msg = json.loads(message)
        print(msg)
        if 'mode' in msg.keys():
            self.set_mode(msg['mode'])

        if 'colour1' in msg.keys():
            self.colour1 = colorzero.Color(msg['colour1'])

        if 'colour2' in msg.keys():
            self.colour2 = colorzero.Color(msg['colour2'])
            asyncio.create_task(self.set_colour2(self.colour2))
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
        asyncio.create_task(self.frame_sender())
        await consumer_task

if __name__ == '__main__':
    tree_server = XmasTreeServer()

    start_server = websockets.serve(tree_server.handler, 'localhost', 6789)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()