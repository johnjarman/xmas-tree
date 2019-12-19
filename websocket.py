#! /usr/bin/python3

import asyncio
import json
import websockets
import colorzero
import datetime
import random
import time
import itertools
import copy
from multiprocessing import Process, Queue
from queue import Full, Empty
from gpiozero import SPIDevice


class XmasTreeHardware(Process):
    def __init__(self, queue, queue2):
        super().__init__()
        self.queue = queue
        self.queue2 = queue2
        self.last_msg = []
        self.spi_device = SPIDevice(mosi_pin=12, clock_pin=25)

    def run(self):
        while True:
            self.queue2.put('done')
            msg = self.queue.get()
            if isinstance(msg, str):
                if msg == 'stop':
                    break

            frame = msg[0]
            brightness = msg[1]

            # Construct SPI command (borrowed from tree.py)
            start_of_frame = [0]*4
            end_of_frame = [0]*5

            # Max brightness = 31

                        # SSSBBBBB (start, brightness)
            brightness = 0b11100000 | brightness

            pixels = [pixel.rgb_bytes[0:3] for pixel in frame]

            pixels = [[brightness, b, g, r] for r, g, b in pixels]
            pixels = [i for p in pixels for i in p]
            data = start_of_frame + pixels + end_of_frame
            self.spi_device._spi.transfer(data)


class XmasTreeServer:
    def __init__(self):
        self.update_needed = False
        self.current_mode = 'manual'

        # Array of colorzero.Color objects, one for each LED
        self.frame = [colorzero.Color('#000')] * 25
        self.set_colour1(colorzero.Color('#FB0'))
        self.set_colour2(colorzero.Color('#60F'))
        self.brightness = 3
        self.enable_sparkle = False
        self.hw_done = True
        self.last_time = 0
        self.hw_queue = Queue(1)
        self.hw_queue_2 = Queue(1)
        self.hw_process = XmasTreeHardware(self.hw_queue, self.hw_queue_2)
        self.hw_process.start()

    async def frame_sender(self):
        while True:
            # Send tuple (frame, brightness) to hw_queue for update
            try:
                if self.hw_queue_2.get(block=False) == 'done':
                    self.hw_done = True

                if self.hw_done:
                    frame = self.frame.copy()

                    if self.enable_sparkle and time.monotonic() - self.last_time > 0.5:
                        self.last_time = time.monotonic()
                        for j in range(random.randrange(1,4)):
                            i = random.randrange(0,25)
                            frame[i] = colorzero.Color('white')
                    
                    self.hw_queue.put((frame, self.brightness), False)
                    self.hw_done = False
            except (Full, Empty):
                pass
            await asyncio.sleep(0.01)

    async def colour_cycle(self):
        """ Cycle through hues """
        while self.current_mode == 'colourcycle':
            await self.set_colour2(self.colour2 + colorzero.Hue(deg=1))
            await asyncio.sleep(0.1)

    async def dawn_dusk_cycle(self):
        """ Run a slow change of colour through the day """
        while self.current_mode == 'dawn-dusk':
            t = datetime.datetime.now()
            
            # Define some colours for different hours
            colour_dict = {
                0 : '#000033',
                1 : '#000033',
                2 : '#000033',
                3 : '#000033',
                4 : '#330066',
                5 : '#663399',
                6 : '#9966cc',
                7 : '#cc6666',
                8 : '#cc99ff',
                9 : '#6666ff',
                10: '#0066ff',
                11: '#0099ff',
                12: '#00ffff',
                13: '#0066ff',
                14: '#3333ff',
                15: '#6633cc',
                16: '#996666',
                17: '#999933',
                18: '#ff9900',
                19: '#cc3399',
                20: '#660099',
                21: '#660066',
                22: '#330066',
                23: '#000066'
            }

            colour = colorzero.Color(colour_dict[t.hour])

            if t.hour == 23:
                t_next = 0
            else:
                t_next = t.hour + 1

            next_colour = colorzero.Color(colour_dict[t_next])

            color_gradient = (c for c in colour.gradient(next_colour, steps=60))
        
            await self.set_colour2(next(itertools.islice(color_gradient, t.minute, None)))
            await asyncio.sleep(30)
    
    def set_classic_colours(self):
        red = colorzero.Color('#FF0000')
        green = colorzero.Color('#00FF00')
        blue = colorzero.Color('#0000FF')
        yellow = colorzero.Color('#FFFF00')
        pink = colorzero.Color('#FF00FF')

        self.frame = [red, green, blue, yellow, pink]*5
    
    async def set_mode(self, mode):
        if mode != self.current_mode:
            # mode-change needed
            self.current_mode = mode

            if mode == 'colourcycle':
                asyncio.create_task(self.colour_cycle())

            elif mode == 'dawn-dusk':
                asyncio.create_task(self.dawn_dusk_cycle())

            elif mode == 'classic':
                self.set_classic_colours()

            elif mode == 'manual':
                await self.set_colour1(self.colour1)
                await self.set_colour2(self.colour2)

    async def set_colour2(self, colour, no_ui_update = False):
        self.colour2 = colour

        for i in itertools.chain(range(0, 3),range(4, 25)):
            self.frame[i] = colour

        if no_ui_update:
            return

        await self.send_ui_update({'colour2':self.colour2.html})

    async def set_colour1(self, colour, no_ui_update = False):
        self.colour1 = colour

        self.frame[3] = colour

        if no_ui_update:
            return

        await self.send_ui_update({'colour1':self.colour1.html})

    async def consumer(self, message):
        msg = json.loads(message)
        print(msg)
        if 'mode' in msg.keys():
            await self.set_mode(msg['mode'])

        if 'colour1' in msg.keys():
            await self.set_colour1(colorzero.Color(msg['colour1']), True)

        if 'colour2' in msg.keys():
            await self.set_colour2(colorzero.Color(msg['colour2']), True)

            if self.current_mode != 'manual':
                await self.send_ui_update({'mode':'manual'})
                self.current_mode = 'manual'

        if 'brightness' in msg.keys():
            self.brightness = int(msg['brightness'])

        if 'sparkle' in msg.keys():
            self.enable_sparkle = bool(msg['sparkle'])

        if 'cmd' in msg.keys():
            if msg['cmd'] == 'request_update':
                await self.send_ui_update({
                    'mode':self.current_mode,
                    'colour1':self.colour1.html,
                    'colour2':self.colour2.html,
                    'brightness':self.brightness,
                    'sparkle':self.enable_sparkle
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

    start_server = websockets.serve(tree_server.handler, '192.168.0.73', 6789)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()