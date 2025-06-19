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

