import asyncio
import json
import logging
import sys
import uuid
from types import TracebackType
from typing import Any, Callable, Dict, Optional, Type

import websockets
from websockets import WebSocketClientProtocol

# setup logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("hydro_trader_client")


class Strategy:

    def __init__(self):
        self.player_id = None
        self.initial_state = None 
        self.current_state = None 

        self.reservoir_ids = []

    def got_initial_state(self):        
        print("We got both initial state and current state.")

        print("--state--")
        print(json.dumps(self.initial_state, indent=4))
        print("----")
        print(json.dumps(self.current_state, indent=4))


        self.reservoir_ids = list(self.initial_state["reservoirs"].keys())        


    def get_production_plan_and_power_price(self):
        """
        Returns a list of reservoirs to produce and the power price
        
        # full initial state: self.initial_state
        # full current state: self.current_state
        """

        print("timestep: {}, cash; {}. marked demand: {}".format(self.current_state["timestep"], self.current_state["cash"], self.current_state["marked_demand"]))
        

        plan = {
            "reservoir_ids": [], # the names of the reservoirs that should produce power
            "power_price": 0 # the power price
        }

        plan["reservoir_ids"].append("Vestarne") # always produce with Vestarne
        plan["reservoir_ids"] = self.reservoir_ids # produce all

        plan["power_price"] = 5.69
        return plan
    
    def game_over(self):
        print("Game Done : Succesfully")

    

class Client:
    def __init__(self, strategy, uri, player_name, game_id):
        self.uri = uri
        self.player_id = str(uuid.uuid4())
        self.player_name = player_name
        self.websocket = None
        self.strategy = strategy

        self.game_id = game_id
        self.game_uri = "{}/{}/{}".format(self.uri, self.game_id, self.player_id)

    async def send_json(self, data):
        await self.websocket.send(json.dumps(data))

    async def recv_json(self):
        message = await self.websocket.recv()
        return json.loads(message)

    def play(self):        
        asyncio.run(self.async_play())

    async def async_play(self):
        try:
            # Connect to the websocket (don't use 'with' here)
            self.websocket = await websockets.connect(self.game_uri)
            logger.info(f"Connected to server as player {self.player_name}")

            # send player info
            player_info = {
                "player_id": self.player_id,
                "player_name": self.player_name,
                "password": "123"
            }

            self.strategy.player_id = self.player_id

            # Use send() instead of send_json()
            await self.send_json(player_info)

            print("waiting on playerinit state")

            # get initial states
            self.strategy.initial_state = await self.recv_json()
            self.strategy.current_state = await self.recv_json()
            self.strategy.got_initial_state()

            # send ready 
            ready_msg = {"status": "ready"}
            await self.send_json(ready_msg)

            print("waiting on game start")

            # wait for game to start
            started_msg = await self.recv_json()
            if started_msg["status"] != "started":
                raise Exception("Game not started")

            print("game started")

            try:
                while True:                    
                    # get production plan and send
                    plan = self.strategy.get_production_plan_and_power_price()                    
                    await self.send_json(plan)

                    # get snapshot state
                    snapshot = await self.recv_json()
                    self.strategy.current_state = snapshot                                        

                    if snapshot["is_game_over"]:
                        self.strategy.game_over()
                        break


                    await asyncio.sleep(0.01)


            
            except Exception as e:
                logger.error(f"Failed to play: {e}")
                return False

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
        finally:
            if self.websocket:
                await self.websocket.close()


   




if __name__ == "__main__":

    no_produce_strategy = Strategy()

    uri = "ws://localhost:8000/ws"    
    player_name = "player1"
    game_id = "game1"

    client = Client(no_produce_strategy, uri, player_name, game_id)
    client.play()











