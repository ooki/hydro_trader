# hydro_trader
Hydro Trader is a framework for trading hydropower in a competitive setting.  
It consists of two parts, a server api that host a game and a client that can access and play the game.
The client should be extended by the player to perform better.

The game is played between N players, each competing in the same market, with the goal to have
as much money at the end of the time T.
The weather and market is simulated to be based in Norway.


# Game 
The player controls a network of hydro reservoirs. Each the player must:
1. Decide which reservoirs should produce electricity.
2. If producing electricity, what price do I demand for my power.

# 100% not finished!
The product should contain a apropriate number of bugs.

# To Run:
1. Start server ( uvicorn hydro_trader.server:app --host 0.0.0.0 --port 8000 )
2. Start client ( python ./hydro_trader/client.py )
3. start_game.py (password is 1234, python ./start_game.py -p 1234 )  

# Admin panel
You can access the admin panel at localhost:8000/admin   (default password is 1234 )

