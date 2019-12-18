#! /usr/bin/python3

import asyncio
import json
import websockets
import colorzero
import datetime
import time
import itertools
from multiprocessing import Process, Queue
from queue import Full


class XmasTreeHardware(Process):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue
        self.last_msg = []

    def run(self):
        while True:
            msg = self.queue.get()
            if isinstance(msg, str):
                if msg == 'stop':
                    break

            frame = msg[0]
            brightness = msg[1]

            if self.last_msg == msg:
                print('ignore')

            else:
                self.last_msg = msg
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
                print(data)

                # Rate-limit SPI commands
                time.sleep(1)


class XmasTreeServer:
    def __init__(self):
        self.update_needed = False
        self.current_mode = 'manual'
        self.colour1 = colorzero.Color('#FB0')
        self.colour2 = colorzero.Color('#60F')
        self.brightness = 3
        self.hw_lock = False
        self.hw_queue = Queue(1)
        self.hw_process = XmasTreeHardware(self.hw_queue)
        self.hw_process.start()

        self.colour1_index = 0
        self.colour2_range = (1,25)

        # Array of colorzero.Color objects, one for each LED
        self.frame = [colorzero.Color('#000')] * 25

    async def frame_sender(self):
        while True:
            # Send tuple (frame, brightness) to hw_queue for update
            try:
                self.hw_queue.put((self.frame, self.brightness), False)
            except Full:
                pass

            await asyncio.sleep(0.1)

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

        self.frame = [colorzero.Color('#FFFFFF')] + [red, green, blue, yellow]*6
    
    def set_mode(self, mode):
        if mode != self.current_mode:
            # mode-change needed
            self.current_mode = mode

            if mode == 'colourcycle':
                asyncio.create_task(self.colour_cycle())

            elif mode == 'dawn-dusk':
                asyncio.create_task(self.dawn_dusk_cycle())

            elif mode == 'classic':
                self.set_classic_colours()

    async def set_colour2(self, colour, no_ui_update = False):
        self.colour2 = colour

        for i in range(*self.colour2_range):
            self.frame[i] = colour

        if no_ui_update:
            return

        await self.send_ui_update({'colour2':self.colour2.html})

    async def set_colour1(self, colour, no_ui_update = False):
        self.colour1 = colour

        self.frame[self.colour1_index] = colour

        if no_ui_update:
            return

        await self.send_ui_update({'colour1':self.colour2.html})

    async def consumer(self, message):
        msg = json.loads(message)
        print(msg)
        if 'mode' in msg.keys():
            self.set_mode(msg['mode'])

        if 'colour1' in msg.keys():
            await self.set_colour1(colorzero.Color(msg['colour1']), True)

        if 'colour2' in msg.keys():
            await self.set_colour2(colorzero.Color(msg['colour2']), True)

            if self.current_mode != 'manual':
                await self.send_ui_update({'mode':'manual'})
                self.current_mode = 'manual'

        if 'brightness' in msg.keys():
            self.brightness = int(msg['brightness'])

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
        await self.set_colour1(colorzero.Color('#FB0'))
        await self.set_colour2(colorzero.Color('#60F'))
        await consumer_task

if __name__ == '__main__':
    tree_server = XmasTreeServer()

    start_server = websockets.serve(tree_server.handler, '192.168.0.73', 6789)

    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()