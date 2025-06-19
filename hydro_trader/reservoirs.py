
norwegian_reservoirs = [
    "Østarne",
    "Vestarne", 
    "Nyfjord",
    "Tesselvannet"
]
import csv
import os
import random

class River:
    def __init__(self, id, initial_water, length_in_timesteps, max_flow, output_reservoir:"Reservoir"):
        """
        The River class is used to model the water flow between reservoirs.

        initial_water: float [m3] * length_in_timesteps
        length_in_timesteps: int
        max_flow: float [m3/s]
        output_reservoir: Reservoir # the reservoir that receives the water
        """
        self.id = id
        self.water_queue = [initial_water / length_in_timesteps] * length_in_timesteps
        self.length_in_timesteps = length_in_timesteps
        self.max_flow = max_flow
        self.output_reservoir = output_reservoir
        self.current_flow = 0.0  # m3/s
        self.consecutive_days_over_max = 0  # count of consecutive days over max flow
        self.cumulative_penalty = 0.0  # track the total cumulative penalty

    def add_inflow(self, water_volume):
        """Add water to the river at the beginning of the queue"""
        self.water_queue[0] += water_volume
        
    def process_timestep(self):
        """
        Process the river for the next timestep
        """

        self.current_flow = sum(self.water_queue)

        # Get water at the end of the queue
        outflow_water = self.water_queue.pop()        
        
        # Check if we exceed the maximum flow
        if self.current_flow > self.max_flow:
            self.consecutive_days_over_max += 1
            # We'll update the cumulative_penalty in get_max_flow_penalty()
        else:
            self.consecutive_days_over_max = 0
            self.cumulative_penalty = 0.0  # Reset the cumulative penalty when flow returns to normal
        
        # Add water to the output reservoir (capped at max_flow)
        if self.output_reservoir:
            self.output_reservoir.add_inflow_river(outflow_water)
            
        # Add new empty slot at the beginning of queue
        self.water_queue.insert(0, 0.0)
        
        return self.current_flow
        
    def get_max_flow_penalty(self):
        """
        Calculate the penalty for exceeding the maximum flow rate.
        The penalty scales with the amount over max flow and adds to the cumulative
        penalty from previous consecutive days of violations.
        
        Returns:
            float: The penalty in cash units for the current day
        """
        if self.current_flow <= self.max_flow:
            self.cumulative_penalty = 0.0
            return 0.0
        
        # Calculate the excess flow
        excess_flow = self.current_flow - self.max_flow
        
        # Base penalty for today: 100 cash units per m³/s of excess flow
        today_penalty = 100.0 * excess_flow
        
        # Add today's penalty to the cumulative total
        total_penalty = today_penalty + self.cumulative_penalty
        
        # Update the cumulative penalty for future calculations
        self.cumulative_penalty = total_penalty
        
        return total_penalty



class MontainWithSnow:
    def __init__(self, id, output_reservoir:"Reservoir", in_file_csv:str):
        """
        Reads the Temperature and Snow height from the in_file
        current_snow_height: float [m] - height of the snow
        temperature: float [°C] - temperature of the snow
        snow_area: float [m2] - area of the mountain snow, used to calculate the snow melt

        Read the csv file to get the temperature and snow height for each timestep, use the delta to calculate any potential snow melt
        """
        self.id = id
        self.output_reservoir = output_reservoir
        self.current_snow_height = 0.0  # m
        self.temperature = 0.0  # °C
        self.snow_area = 1000000.0  # m2 (default 1 km²)
        self.timestep = 0
        self.data = []
        
        # Read the CSV file
        if os.path.exists(in_file_csv):
            with open(in_file_csv, 'r') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    self.data.append({
                        'temperature': float(row.get('Temperature', 0)),
                        'snow_height': float(row.get('SnowHeight', 0))
                    })
        else:
            raise ValueError(f"Warning: Snow data file {in_file_csv} not found!")
            
        # Initialize with first data point if available
        if self.data:
            self.current_snow_height = self.data[0]['snow_height']
            self.temperature = self.data[0]['temperature']

    def process_timestep(self):
        """
        Process the mountain snow melt for the next timestep.
        Calculate snow melt based on temperature and send water to output reservoir.
        """
        self.timestep += 1
        
        # Get data for current timestep if available
        if self.timestep < len(self.data):
            # Calculate snow melt from previous to current timestep
            prev_snow_height = self.current_snow_height
            self.current_snow_height = self.data[self.timestep]['snow_height']
            self.temperature = self.data[self.timestep]['temperature']
            
            # Only melt snow if temperature is above 0°C and snow height has decreased
            snow_melt = 0.0
            if self.temperature > 0 and prev_snow_height > self.current_snow_height:
                # Calculate snow melt in m³
                snow_melt = (prev_snow_height - self.current_snow_height) * self.snow_area
                # Add melt water to the reservoir - add direcly to the reservoir to make the task a bit easier (no delay)
                self.output_reservoir.add_inflow_snow_melt(snow_melt)
            
            return snow_melt
        
        return 0.0

    


class Reservoir:
    def __init__(self, id, rain_data_csv:str):
        """
        Initialize a reservoir with its properties.
        
        rain_data_csv: str - a file to read the forcast and and rain data from

        water amount: float [m3]
        water_area: float [m2]
        basin_area: float [m2] # for rainfall
        capacity: float [m3]
        (water height can be derived from water amount, water_area and capacity) m

        river_inflow: float [m3/s]   # river inflow (sum if more than 1 in_rivers )
        natural inflow: float [m3/s] # from rain and snow melt
        river_outflow: float [m3/s]  # river outflow (divided equally if more than 1 out_rivers )
        
        generator_efficiency: float [0, 1]
        generator_capacity: float MWh
        generator_head_height: float [m] # height of the generator drop (m)
        generator_flow: float [m3/s] # flow of the generator (m3/s) : given by height of water 

        is_raining: bool # add rain to the natural inflow, depends on the basin_area and is_raining
        
        is_producing = bool # depends on water hight, generator efficiency
        current_production: float [MWh] # production for this timestep

        out_river: River
        rain_forecast_probability: float [0,1] probability of rain tomorrow
        """
        self.id = id
        
        # Water properties
        self.water_amount = 0.0  # m³
        self.water_area = 1000000.0  # m² (default 1 km²)
        self.basin_area = 5000000.0  # m² (default 5 km²)
        self.capacity = 10000000.0  # m³ (default 10 million m³)
        
        # Flow properties
        self.river_inflow = 0.0  # m³/s
        self.natural_inflow = 0.0  # m³/s
        self.river_outflow = 0.0  # m³/s
        
        # Power generation properties
        self.generator_head_height = 50.0 # m - height of the generator
        self.generator_efficiency = 0.85  # 85% efficient
        self.is_producing = False
        self.current_production = 0.0  # MWhi
        self.generator_flow = 0.0  # m3/s
        self.max_generator_flow = 0.0 # m3/s
        
        # Rain properties
        self.is_raining = False
        self.rain_forecast_probability = 0.0
        self.rain_data = []
        self.timestep = 0
        # Rain height in meters - constant value when it rains (in meters)
        self.rain_height = 0.01  # Default: 1 cm of rain
        
        # River connections
        self.in_rivers = []
        self.out_rivers = []
        
        # Load rain data if available
        if os.path.exists(rain_data_csv):
            with open(rain_data_csv, 'r') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    # Parse Actual_Rain as boolean and Forecast as probability
                    is_raining = row.get('Actual_Rain', '0').lower() in ['1', 'true', 'True', 'yes', 'y']
                    forecast_prob = float(row.get('Forecast', 0))  # [0,1]
                    
                    self.rain_data.append({
                        'is_raining': is_raining,
                        'forecast_probability': forecast_prob
                    })
        else:
            print(f"Warning: Rain data file {rain_data_csv} not found!")
        
        # Initial rain status
        if self.rain_data:
            self.is_raining = self.rain_data[0]['is_raining']    
            self.rain_forecast_probability = self.rain_data[0]['forecast_probability']

    def fill(self):
        self.water_amount = self.capacity
    
    def get_water_height(self):
        """Calculate water height in meters"""
        if self.water_area > 0:
            return self.water_amount / self.water_area
        return 0.0
    
    def get_water_percentage(self):
        """Calculate percentage of capacity filled"""
        if self.capacity > 0:
            return (self.water_amount / self.capacity) * 100
        return 0.0
    
    def add_inflow_river(self, inflow_river_m3:float):
        """Add inflow from a river (m³)"""
        self.river_inflow += inflow_river_m3
        self.water_amount += inflow_river_m3
        # Ensure water amount doesn't exceed capacity
        self.water_amount = min(self.water_amount, self.capacity)
    
    def add_inflow_snow_melt(self, snow_melt_m3:float):
        """Add inflow from snow melt (m³)"""
        self.natural_inflow += snow_melt_m3
        self.water_amount += snow_melt_m3
        # Ensure water amount doesn't exceed capacity
        self.water_amount = min(self.water_amount, self.capacity)
    
    def add_inflow_rain(self, rain_m:float):
        """
        Add rain to reservoir, the total amount is equal basin_area * rain
        """
        rain_volume = rain_m * self.basin_area  # m³
        self.natural_inflow += rain_volume
        self.water_amount += rain_volume
        # Ensure water amount doesn't exceed capacity
        self.water_amount = min(self.water_amount, self.capacity)
    
    def add_outflow_river(self, outflow_river):
        """Add an outflow river to the reservoir"""
        if outflow_river not in self.out_rivers:
            self.out_rivers.append(outflow_river)
    
    def add_inflow_river_connection(self, inflow_river):
        """Add an inflow river connection to the reservoir"""
        if inflow_river not in self.in_rivers:
            self.in_rivers.append(inflow_river)
    
    def calculate_production(self):
        """Calculate electricity production based on hydropower equation: P = η × ρ × g × Q × h
        where:
        η (eta) = efficiency
        ρ (rho) = density of water (1000 kg/m³)
        g = gravitational acceleration (9.81 m/s²)
        Q = flow rate (m³/s)
        h = height/head (m)
        """

        if self.is_producing is False:
            self.current_production = 0.0
            self.generator_flow = 0.0
            return 0.0
                
        # Get current water height
        water_height = self.get_water_height()
        
        # Constants
        rho = 1000  # kg/m³ (water density)
        g = 9.81    # m/s² (gravitational acceleration)
        
        # Set generator head height if not already set        
        self.generator_head_height = 50.0  # Default 50m head
        
        # Calculate flow based on water height (more water = more flow)
        # This is a simplified model - in reality the relationship would be based on dam design
        
        
        
        # Check if we have water to run the generator
        seconds_in_day = 86400

        max_water_height = self.capacity / self.water_area        
        flow_factor = self.get_water_height() / max_water_height
        flow_factor = min(flow_factor, 1.0)
        flow_factor = max(flow_factor, 0.4)

        actual_flow_rate = flow_factor * self.max_generator_flow        
        water_needed_for_day = actual_flow_rate * seconds_in_day

        # Use all available water for production
        if water_height > 0:
            
            # Calculate how much water we can actually use (limited by what's available)            
            total_available_water_volume = self.water_amount  # All water is available
            
            # If we don't have enough water for a full day, adjust the flow rate
            if total_available_water_volume < water_needed_for_day:
                # We'll produce with whatever water we have
                actual_flow_rate = total_available_water_volume / seconds_in_day
                                    
            # Calculate power using the hydropower equation (P = η * ρ * g * Q * h)
            # Power in Watts = efficiency * water density * gravity * flow rate * head height
            power_watts = self.generator_efficiency * rho * g * actual_flow_rate * self.generator_head_height
            
            # Convert to MWh (divide by 1,000,000 for MW, then multiply by hours in a day (24) for MWh)
            power_mwh = (power_watts / 1000000) * 24
            
            # Limit to generator capacity
            self.current_production = power_mwh
            
            # Calculate water used - either all available water or what's needed for the day
            water_used = min(total_available_water_volume, actual_flow_rate * seconds_in_day)
            
            # Reduce water amount based on usage
            self.water_amount -= water_used

        else:
            self.is_producing = False
            self.current_production = 0.0
            self.generator_flow = 0.0
        
        return self.current_production
    
    def process_timestep(self):
        """
        Process the reservoir for the next timestep
        """
        # Reset flow counters for this timestep
        self.river_inflow = 0.0
        self.natural_inflow = 0.0
        self.river_outflow = 0.0
        
        # Process rain data for current timestep
        self.timestep += 1
        if self.timestep < len(self.rain_data):
            rain_data = self.rain_data[self.timestep]
            self.is_raining = rain_data['is_raining']
            self.rain_forecast_probability = rain_data['forecast_probability']
            
            # Process rainfall - use the constant rain_height when it's raining
            if self.is_raining:
                self.add_inflow_rain(self.rain_height)
        
        # Handle overflow case - check if we're at capacity
        overflow_amount = 0.0
        if self.water_amount >= self.capacity:
            overflow_amount = self.water_amount - self.capacity
            self.water_amount = self.capacity  # Cap water at capacity
        
        # Calculate regular outflow to rivers
        if self.out_rivers:
            # If there's overflow, distribute it to the rivers
            if overflow_amount > 0:
                # Just distribute overflow among rivers
                overflow_per_river = overflow_amount / len(self.out_rivers)
                self.river_outflow += overflow_amount
                
                # Send to each river
                for river in self.out_rivers:
                    river.add_inflow(overflow_per_river)
                    
        # Calculate electricity production
        self.calculate_production()







 