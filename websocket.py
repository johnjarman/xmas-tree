#! /usr/bin/python3

import asyncio
import json
import websockets


class MessageHandler:
    def __init__(self):
        self.update_needed = False
        self.current_mode = 'manual'


    async def consumer(self, message):
        msg = json.loads(message)
        print(msg)
        if 'mode' in msg.keys():
            self.current_mode = msg['mode']
        elif self.current_mode != 'manual':
            self.update_needed = True

    async def producer(self):
        # Check if current state deviates from commanded state
        while True:
            if self.update_needed:
                self.update_needed = False
                return json.dumps({'mode':'manual'})
            await asyncio.sleep(0.01)

    async def consumer_handler(self):
        async for message in self.websocket:
            await self.consumer(message)

    async def producer_handler(self):
        while True:
            message = await self.producer()
            await self.websocket.send(message)

    async def handler(self, websocket, path):
        self.websocket = websocket
        consumer_task = asyncio.ensure_future(self.consumer_handler())
        producer_task = asyncio.ensure_future(self.producer_handler())
        done, pending = await asyncio.wait(
            [consumer_task, producer_task]
        )

        
msg_handler = MessageHandler()

start_server = websockets.serve(msg_handler.handler, 'localhost', 6789)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()