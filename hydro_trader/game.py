import os
import csv
import json
import random
import asyncio
from copy import deepcopy
from typing import Dict, List, Set, Any
from collections import defaultdict



from copy import deepcopy

from hydro_trader.simulation import Simulation
from hydro_trader.reservoirs import Reservoir, River, MontainWithSnow

class PowerMarked:
    def __init__(self, data_dir):
        self.data_dir = data_dir

        self.max_price_per_kwh = 10.0

        self.marked_demand_data = []

        self.demand_factor = 900.0 # multiplier per player in MWh
        self.n_players = 0
        self.timestep = 0
        self.current_bids_by_player = {}

        self.earnings_report_by_player = {}

        self.accepted_bids = []

        self._read_marked_file()

    def _read_marked_file(self):

        marked_file = os.path.join(self.data_dir, "power_demand.csv")
        if not os.path.isfile(marked_file):
            return False

        with open(marked_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.marked_demand_data.append(float(row['demand']))

        return True

    def get_production_demand(self):
        if self.timestep < len(self.marked_demand_data):
            return self.marked_demand_data[self.timestep] * self.n_players * self.demand_factor
        
        return 0.0

    def add_player_bid(self, player_id, power_amount_mwh, power_price_kWh):

        price = min(power_price_kWh, self.max_price_per_kwh)
        price = max(0.000001, price)
        self.current_bids_by_player[player_id] = (price, power_amount_mwh)

    def process_bids(self):
        """
        Process the bids for the current timestep.
        """
        self.accepted_bids = []

        # Sort bids by price in ascending order : add a epsilon to break ties
        epsilon = 0.00001
        bids_to_sort = []
        for player_id, (bid, amount) in self.current_bids_by_player.items():
            bids_to_sort.append((bid+(random.random() * epsilon), player_id, bid, amount))


        # zero afterwards
        self.current_bids_by_player = {}

        sorted_bids = sorted(bids_to_sort, key=lambda x: x[0])
        
        # Calculate total production and price
        total_production = 0.0
        total_price = 0.0
        todays_marked_demand = self.get_production_demand()

        # zero earnings
        
        self.earnings_report_by_player = {}
        
        # Process bids
        for _, player_id, price, amount in sorted_bids:

            # if we still have some demand left produce as much as possible
            # we dont need the entire bid, produce and pay for the part we used
            if total_production + amount > todays_marked_demand:
                amount = todays_marked_demand - total_production
                                    

            # Add to total production and price
            total_production += amount
            player_earnings = amount * price * 1000.0 # kWh to MWh
            total_price += player_earnings

            self.accepted_bids.append((player_id, player_earnings, amount))
            
            # Add earnings report for this player
            self.earnings_report_by_player[player_id] = (player_earnings, amount)


        # Calculate average price
        if total_production > 0:
            average_price = total_price / total_production
        else:
            average_price = 0.0
        
        return average_price    

    

class Game:
    def __init__(self, simulation:Simulation, power_marked:PowerMarked):
        self.base_simulation = simulation
        self.power_marked = power_marked
        self.n_timesteps = -1        

        self.simulations = {} # player_id -> simulation
        self.names = {} # player_id -> player_name
        self.cash = defaultdict(float) # player_id -> cash
        self.production = {} # player_id -> production : a set of reservoirs that should produce this timestep
        self.price_of_power = {} # player_id -> price_of_power

        self.current_day_production_demand = 0 # to be read from marked file 
        self.penalty_convertion_rate = 0.0 # convertion rate from penalty to cash for river overflows

        self.timestep = 0

    def add_player(self, player_id, player_name):
        self.simulations[player_id] = deepcopy(self.base_simulation)
        self.names[player_id] = player_name
        self.cash[player_id] = 0.0
        self.production[player_id] = set()
        self.price_of_power[player_id] = 0.0

        self.power_marked.n_players += 1


    def set_production(self, player_id, reservoir_ids, price_of_power):
        self.production[player_id] = set(reservoir_ids)
        self.price_of_power[player_id] = price_of_power


    def get_full_state(self, player_id):
        state = self.simulations[player_id].get_full_state()
        state['cash'] = self.cash[player_id]
        # Add more

        return state
    
    def get_timestep_state(self, player_id):
        d = self.simulations[player_id].get_timestep_state()
        d["cash"] = self.cash[player_id]
        d["marked_demand"] = self.current_day_production_demand
        d["sold_power"] = self.power_marked.accepted_bids

        earning_report = self.power_marked.earnings_report_by_player.get(player_id)
        if earning_report is None:
            earning_report = (0.0, 0.0)

        d["production_results"] = {"price": earning_report[0], "amount": earning_report[1]}
        d["is_game_over"] = self.is_game_over()
        d["timestep"] = self.timestep

        d["other_players"] = []
        for other_player_id, sim in self.simulations.items():
            if other_player_id != player_id:
                total_water_in_m3 = sim.get_total_water_in_m3()
                d["other_players"].append({"name": self.names[other_player_id], "player_id": other_player_id, "cash": self.cash[other_player_id], "total_water_in_m3": total_water_in_m3})

        return d

    def is_game_over(self):
        return self.timestep >= self.n_timesteps
    
    def process_timestep(self):

        for player_id, sim in self.simulations.items():

            producing_reservoirs = self.production.get(player_id, [])
            for r_id in producing_reservoirs:
                sim.set_production(r_id, True)

            player_output_in_mwh, penalty_for_river_overflow = sim.simulate_day()

            print("player_output_in_mwh:", player_output_in_mwh)

            if penalty_for_river_overflow > 0:
                print("negative river overflow penalty: {}".format(penalty_for_river_overflow))
                self.cash[player_id] -= penalty_for_river_overflow * self.penalty_convertion_rate

            if player_output_in_mwh > 0:
                price_of_power = self.price_of_power.get(player_id, 0.0)                
                self.power_marked.add_player_bid(player_id, player_output_in_mwh, self.price_of_power[player_id])

        self.power_marked.process_bids()

        for player_id, (price, amount_water) in self.power_marked.earnings_report_by_player.items():
            self.cash[player_id] += price
        
        self.power_marked.timestep += 1

        self.current_day_production_demand = self.power_marked.get_production_demand()

        self.timestep += 1

        # clear production
        self.production = {}
        self.price_of_power = {}
    
