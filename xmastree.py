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
import logging
import logging.handlers
import sys
from multiprocessing import Process, Queue
import queue
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
        self.connections = set()
        self.state = ''
        self.last_hour = [0,0]
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
                            if i != 3:
                                frame[i] = colorzero.Color('white')
                    
                    # Turn on or off as programmed
                    now = datetime.datetime.now()

                    if self.last_hour != [now.hour, now.minute]:
                        self.state = ''
                        self.last_hour = [now.hour, now.minute]

                    if [now.hour, now.minute] in self.off_times:
                        if self.state != 'off':
                            if self.brightness != 0:
                                self.last_brightness = self.brightness
                                self.brightness = 0
                            self.state = 'off'

                    elif [now.hour, now.minute] in self.on_times:
                        if self.state != 'on':
                            if self.brightness == 0:
                                self.brightness = self.last_brightness
                            self.state = 'on'

                    self.hw_queue.put((frame, self.brightness), False)
                    self.hw_done = False
            except (queue.Full, queue.Empty):
                pass
            await asyncio.sleep(0.01)

    async def colour_cycle(self):
        """ Cycle through hues """
        while self.current_mode == 'colourcycle':
            await self.set_colour2(self.colour2 + colorzero.Hue(deg=2))
            await asyncio.sleep(0.2)

    async def slow_cycle(self):
        """ Run a slow change of colour between some nice presets """
        colour_presets = [
            ['#FF0000', '#00FF00'], # Red/green
            ['#FFFFFF', '#0055FF'], # White/aqua
            ['#FF2400', '#2600FF'], # Orange/purple
            ['#003DFF', '#FF009E'], # Blue/pink
            ['#2600FF', '#FF2400'], # Purple/orange
            ['#00FF00', '#FF0000'], # Green/red
            ['#FF20BF', '#F56710']  # Warm white/pink
        ]
        while self.current_mode == 'slow-cycle':
            for preset in colour_presets:
                # Transition to next preset over about 5 mins

                gradient1 = self.colour1.gradient(colorzero.Color(preset[0]), steps=30)
                gradient2 = self.colour2.gradient(colorzero.Color(preset[1]), steps=30)

                for c1, c2 in zip(gradient1, gradient2):
                    if self.current_mode != 'slow-cycle':
                        break
                    await self.set_colour1(c1)
                    await self.set_colour2(c2)
                    await asyncio.sleep(10)

                # Stay on this preset for 5 mins
                if self.current_mode == 'slow-cycle':
                    await asyncio.sleep(300)
                else:
                    break
    
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

            elif mode == 'slow-cycle':
                asyncio.create_task(self.slow_cycle())

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

    async def load_defaults(self):
        # Load config from file
        try:
            with open('defaults.json', 'r') as json_file:
                defaults = json.load(json_file)
                logging.info("Loading defaults from defaults.json")
        except FileNotFoundError:
            # No config file found, so create it
            logging.warn("No config file found, using built-in defaults")
            defaults = {
                'current_mode':'slow-cycle',
                'colour1':'#FF2400',
                'colour2':'#2602FF',
                'brightness':3,
                'on_times':[[16,0]],
                'off_times':[[23,30]],
                'enable_sparkle':False
            }

            with open('defaults.json', 'w+') as json_file:
                json.dump(defaults, json_file)
                logging.info("Written built-in defaults to config file defaults.json")

        # Load in default values
        self.frame = [colorzero.Color(defaults['colour2'])] * 25
        self.frame[3] = colorzero.Color(defaults['colour1'])
        self.colour1 = colorzero.Color(defaults['colour1'])
        self.colour2 = colorzero.Color(defaults['colour2'])
        self.brightness = defaults['brightness']
        self.last_brightness = defaults['brightness']
        self.on_times = defaults['on_times']
        self.off_times = defaults['off_times']
        self.enable_sparkle = defaults['enable_sparkle']
        self.current_mode = ''
        await self.set_mode(defaults['current_mode'])

    async def save_defaults(self):
        defaults = {
            'colour1':self.colour1.html,
            'colour2':self.colour2.html,
            'brightness':self.brightness,
            'on_times':self.on_times,
            'off_times':self.off_times,
            'enable_sparkle':self.enable_sparkle,
            'current_mode':self.current_mode
        }
        
        with open('defaults.json', 'w+') as json_file:
            json.dump(defaults, json_file)
            logging.info("Saved defaults to defaults.json")


    async def consumer(self, message):
        msg = json.loads(message)
        logging.debug("Message received: {}".format(msg))
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

        if 'on_times' in msg.keys():
            on_times =  msg['on_times'].split(',')
            on_times_filtered = []
            for time in on_times:
                try:
                    hour, minute = time.split(':')
                    if int(hour) >= 0 and int(hour) <= 23 and int(minute) >= 0 and int(minute) <= 59:
                        on_times_filtered.append([int(hour),int(minute)])
                except (ValueError, IndexError):
                    pass
            self.on_times = on_times_filtered
            self.state = ''

        if 'off_times' in msg.keys():
            off_times =  msg['off_times'].split(',')
            off_times_filtered = []
            for time in off_times:
                try:
                    hour, minute = time.split(':')
                    if int(hour) >= 0 and int(hour) <= 23 and int(minute) >= 0 and int(minute) <= 59:
                        off_times_filtered.append([int(hour),int(minute)])
                except (ValueError, IndexError):
                    pass
            self.off_times = off_times_filtered
            self.state = ''

        if 'cmd' in msg.keys():
            if msg['cmd'] == 'request-update':
                await self.update_all()

            elif msg['cmd'] == 'save-defaults':
                await self.save_defaults()

            elif msg['cmd'] == 'load-defaults':
                await self.load_defaults()
                await self.update_all()

    async def update_all(self):
        on_times = []
        for t in self.on_times:
            on_times.append('{}:{:0>2}'.format(t[0], t[1]))
        off_times = []
        for t in self.off_times:
            off_times.append('{}:{:0>2}'.format(t[0], t[1]))
        await self.send_ui_update({
            'mode':self.current_mode,
            'colour1':self.colour1.html,
            'colour2':self.colour2.html,
            'brightness':self.brightness,
            'sparkle':self.enable_sparkle,
            'on_times':str(on_times).strip('[]').replace('\'',''),
            'off_times':str(off_times).strip('[]').replace('\'','')
        })

    async def send_ui_update(self, update):
        if self.connections:
            # Send update to each connected client
            await asyncio.wait([connection.send(json.dumps(update)) for connection in self.connections])
        
            logging.debug('Sent update {} to {} client(s)'.format(update, len(self.connections)))

        else:
            logging.debug("Didn't send update {}: no clients connected".format(update))

    async def handler(self, websocket, path):
        try:
            self.connections.add(websocket)
            logging.info("Client connected from {}".format(websocket.remote_address[0]))
            async for message in websocket:
                await self.consumer(message)
        except websockets.ConnectionClosed:
            logging.info("Client disconnected from {}".format(websocket.remote_address[0]))
        finally:
            self.connections.discard(websocket)

    async def start(self):
        await self.load_defaults()
        ip = '192.168.0.73'
        port = 6789
        await websockets.serve(self.handler, ip, port)
        logging.info('Server started at {}:{}'.format(ip, port))
        await self.frame_sender()


if __name__ == '__main__':
    # Set up logging
    log_queue = queue.Queue()
    queue_handler = logging.handlers.QueueHandler(log_queue)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
    file_handler = logging.FileHandler('xmastree.log')
    file_handler.setFormatter(formatter)
    queue_listener = logging.handlers.QueueListener(log_queue, file_handler)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(queue_handler)

    queue_listener.start()

    tree_server = XmasTreeServer()

    asyncio.run(tree_server.start())