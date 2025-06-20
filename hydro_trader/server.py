import asyncio
import logging
from typing import Dict, Set, Any, List
from contextlib import asynccontextmanager
from copy import deepcopy
import os
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from starlette.middleware.sessions import SessionMiddleware


# Local imports
from hydro_trader.game import Game, PowerMarked
from hydro_trader.reservoirs import Reservoir, River, MontainWithSnow
from hydro_trader.simulation import Simulation




logger = logging.getLogger("hydro_trader.server")
logging.basicConfig(level=logging.INFO)


class Server:
    def __init__(self, game_id:str = "game1"):        
        self.game : Game = self._create_game()
        self.password = "123"
        self.admin_password = "1234"
        self.time_per_step = 1.0

        self._players : Set[str] = set()
        self._sockets : Dict[str, WebSocket] = {}
        self.update_events = {}

        self.game_id = game_id
        self.is_active = False
        self.is_accepting_new_players = True


    def _create_game(self):
        
        sim = Simulation(data_dir="data")
        sim.create_norwegian_environment()
        
        marked = PowerMarked(data_dir="data")
        game = Game(sim, marked)
        
        return game
    
    @asynccontextmanager
    async def game_loop_task(self, app: FastAPI):
                
        self._task = asyncio.create_task(self._run_game_loop())
        logger.info("Game server started")
        
        try:
            yield  # serve
        finally:
            # Shutdown: Cancel the task
            if self._task:
                self.is_active = False
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:                    
                    logger.info("Game loop task cancelled")

    async def _run_game_loop(self):
    
        first_timestep_wait = True
        while True:
            if self.is_active:                                

                if first_timestep_wait:
                    await asyncio.sleep(self.time_per_step) # first sleep -> extra first round
                    first_timestep_wait = False

                print("timestep: ", self.game.timestep)

                if self.game.is_game_over():
                    logger.info("Game over")
                    print("game over: ", self.game.is_game_over())
                    self.is_active = False
                    first_timestep_wait = True


                    for player_id in self._players:
                        self.update_events[player_id].set()
                        break


                # process the productions - if not first timestep
                self.game.process_timestep()

                # set all events
                for player_id in self._players:
                    self.update_events[player_id].set()
                
                await asyncio.sleep(self.time_per_step) # first sleep 


            else:
                await asyncio.sleep(0.1)

    
    async def reset_game(self):
        self.is_active = False
        self.is_accepting_new_players = False

        self.game = self._create_game()

        self.is_accepting_new_players = True
        for player_id in self._players:
            self.update_events[player_id].set()
            break

        self._players = set()
        self._sockets = {}
        self.update_events = {}

        



    async def setup_player(self, websocket: WebSocket, player_id: str, player_name:str):
        """Accept a websocket connection from *player_id*."""
                
        if player_id in self._players:            
            
            try:
                self._sockets[player_id].close()
            except Exception:
                pass

            del self._sockets[player_id] #            
            logger.info("Player %s reconnected", player_id)
        else:

            logger.info("Player %s connected (%d total)", player_id, len(self._sockets))
            self.game.add_player(player_id, player_name)        

        self._sockets[player_id] = websocket
        self._players.add(player_id)
        self.update_events[player_id] = asyncio.Event()


    async def disconnect(self, player_id):
        
        if player_id in self._players:
            try:
                await self._sockets[player_id].close()
            except Exception:
                pass

            del self._sockets[player_id] #            
            logger.info("Player %s disconnected", player_id)
            self._players.remove(player_id)
        
       
    async def send_initial_state(self, player_id: str):    

        if player_id not in self._players:
            raise HTTPException(status_code=400, detail="Invalid player ID")
        
        state = self.game.get_full_state(player_id)
        await self._sockets[player_id].send_json(state)

        logger.info("Initial state sent to player %s", player_id)

    async def send_timestep_state(self, player_id: str):

        if player_id not in self._players:
            raise HTTPException(status_code=400, detail="Invalid player ID")
        
        state = self.game.get_timestep_state(player_id)        
        await self._sockets[player_id].send_json(state)

        # logger.info("Timestep state sent to player %s", player_id)





# Set up templates
templates = Jinja2Templates(directory="templates")


game_server = Server()
app = FastAPI(title="Hydro-Trader Game-Server",
              lifespan=game_server.game_loop_task)

# Allow all CORS , this makes local browser based clients easier to develop
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

secret_key = os.environ.get("SECRET_KEY", str(uuid.uuid4()))
app.add_middleware(SessionMiddleware, secret_key=secret_key)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "Hydro Trader server is running"}

@app.post("/reset")
async def reset_game(pwd: str):
    if pwd != game_server.admin_password:
        raise HTTPException(status_code=403, detail="Invalid password")
    
    await game_server.reset_game()
    return {"status": "Game reset"}

@app.post("/start")
async def start_game(pwd: str, num_timesteps:int):
    
    if pwd != game_server.admin_password:
        raise HTTPException(status_code=403, detail="Invalid password")
    
    game_server.is_active = True
    game_server.game.n_timesteps = num_timesteps

    logger.info("Game started : for {} timesteps".format(num_timesteps))

    return {"status": "Game starting"}



@app.websocket("/ws/{game_id}/{player_id}")
async def handle_player_interaction(websocket: WebSocket, game_id: str, player_id: str):
    
    if game_server.game_id != game_id:
        raise HTTPException(status_code=400, detail="Invalid game ID")
    
    try:
        await websocket.accept()
        player_info = await websocket.receive_json()

        player_name = player_info["player_name"]
        player_id_copy = player_info["player_id"]
        password = player_info["password"]

        if password != game_server.password:
            raise HTTPException(status_code=403, detail="Invalid password")

        if player_id != player_id_copy:
            raise HTTPException(status_code=400, detail="Invalid player ID")

        await game_server.setup_player(websocket, player_id, player_name)        
        await game_server.send_initial_state(player_id)
        await game_server.send_timestep_state(player_id)

        # get ready message        
        ready_msg = await websocket.receive_json()
        if ready_msg["status"] != "ready":
            raise HTTPException(status_code=400, detail="Invalid ready message")
        
        # wait for game to start
        while not game_server.is_active:
            await asyncio.sleep(0.1)

        start_game_event = {"status": "started"}
        await websocket.send_json(start_game_event)
        
        while game_server.is_active:            

            input_t = await websocket.receive_json()            
            production_plan = input_t["reservoir_ids"]
            power_price = input_t["power_price"]

            game_server.game.set_production(player_id, production_plan, power_price)
            await game_server.update_events[player_id].wait()           
            if game_server.is_active:
                await game_server.send_timestep_state(player_id)            

            game_server.update_events[player_id].clear()

            await asyncio.sleep(0.01)        

        print("<game done>")
        

    except Exception as e:
        logger.error(f"Error with player {player_id}: {e}")
        await game_server.disconnect(player_id)

    await game_server.disconnect(player_id)



#----------------- ADMIN PAGE --------------------

@app.get("/admin")
async def admin_get(request: Request):
    authenticated = request.session.get('authenticated', False)
    return templates.TemplateResponse("admin.jinja", {"request": request, "authenticated": authenticated})

@app.post("/admin")
async def admin_post(request: Request, password: str = Form(...)):
    if password == game_server.admin_password:
        request.session['authenticated'] = True

        # add info for authenticated users
        n_players = len(game_server._players)
        game_id = game_server.game_id
        is_game_over = game_server.game.is_game_over()

        variables = {"n_players": n_players, "is_game_over": is_game_over, "game_id": game_id}
        variables["request"] = request
        variables["authenticated"] = True

        return templates.TemplateResponse("admin.jinja", variables)
    else:
        return templates.TemplateResponse("admin.jinja", {"request": request, "authenticated": False, "error": "Invalid password"})
    

@app.post("/admin/start")
async def admin_start(request: Request, num_timesteps: int = Form(20)):
    if not request.session.get('authenticated', False):
        return RedirectResponse(url="/admin", status_code=303)
    
    try:
        # Call the start game function with admin password and timesteps
        await start_game(game_server.admin_password, num_timesteps)
        message = f"Game started successfully for {num_timesteps} timesteps!"
        
        # Add info for authenticated users
        n_players = len(game_server._players)
        game_id = game_server.game_id
        is_game_over = game_server.game.is_game_over()
        
        variables = {
            "request": request, 
            "authenticated": True, 
            "message": message,
            "n_players": n_players, 
            "n_timesteps": num_timesteps, 
            "is_game_over": is_game_over, 
            "game_id": game_id
        }
        
        return templates.TemplateResponse("admin.jinja", variables)
    except Exception as e:
        return templates.TemplateResponse("admin.jinja", {"request": request, "authenticated": True, "error": str(e)})
    

@app.get("/admin/game-info")
async def admin_game_info(request: Request):
    if not request.session.get('authenticated', False):
        return {"error": "Not authenticated"}
    
    n_players = len(game_server._players)
    game_id = game_server.game_id
    is_game_over = game_server.game.is_game_over()
    n_timesteps = game_server.game.n_timesteps
    current_timestep = game_server.game.timestep
    is_active = game_server.is_active
    
    return {
        "n_players": n_players,
        "game_id": game_id,
        "is_game_over": is_game_over,
        "n_timesteps": n_timesteps,
        "current_timestep": current_timestep,
        "is_active": is_active
    }


@app.post("/admin/reset")
async def admin_reset(request: Request):
    if not request.session.get('authenticated', False):
        return RedirectResponse(url="/admin", status_code=303)
    
    try:
        # Reset the game server
        await game_server.reset_game()
        message = "Game server reset successfully!"
        
        # Add info for authenticated users
        n_players = len(game_server._players)
        game_id = game_server.game_id
        is_game_over = game_server.game.is_game_over()
        n_timesteps = game_server.game.n_timesteps
        current_timestep = game_server.game.timestep
        is_active = game_server.is_active
        
        variables = {
            "request": request, 
            "authenticated": True, 
            "message": message,
            "n_players": n_players,
            "game_id": game_id,
            "is_game_over": is_game_over,
            "n_timesteps": n_timesteps,
            "current_timestep": current_timestep,
            "is_active": is_active
        }
        
        return templates.TemplateResponse("admin.jinja", variables)
    except Exception as e:
        return templates.TemplateResponse("admin.jinja", {
            "request": request, 
            "authenticated": True, 
            "error": f"Error resetting game server: {str(e)}"
        })