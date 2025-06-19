

import os
from re import I
from hydro_trader.reservoirs import Reservoir, River, MontainWithSnow

class Simulation:
    def __init__(self, data_dir="data"):
        self.reservoirs = []
        self.rivers = []
        self.mountains = []

        self.data_dir = data_dir


    def fill_all_reservoirs(self):
        for reservoir in self.reservoirs:
            reservoir.fill()

    def get_total_water_in_m3(self):
        return sum([r.water_amount for r in self.reservoirs])

    def set_production(self, reservoir_id, production_status):
        for reservoir in self.reservoirs:
            if reservoir.id == reservoir_id:
                reservoir.is_producing = production_status
                break

    def get_timestep_state(self) -> dict:
        return {
            "reservoirs": {
                r.id: {
                    "water_amount": r.water_amount,
                    "capacity": r.capacity,
                    "forecast_probability": r.rain_forecast_probability,
                    "did_rain": r.is_raining,
                }
                for r in self.reservoirs
            },
            "rivers": {
                r.id: {
                    "flow": list(r.water_queue),
                }
                for r in self.rivers
            },
            "mountains": {
                m.id: {
                    "snow_height": m.current_snow_height,
                    "temperature": m.temperature,
                }
                for m in self.mountains
            },
            }

    def get_full_state(self) -> dict:
        """
        This is sendt to each player so that they can correctly setup their state, should include all states.
        Unlike get_timestep_state, this should include all states.
        """

        # Build a comprehensive snapshot of the full simulation state so that
        # every client (e.g. game player or UI) can faithfully recreate the
        # simulation on their side before the first timestep is processed.
        state: dict = {
            "reservoirs": {},
            "rivers": {},
            "mountains": {},
        }

        # Reservoirs – include both static meta-data and dynamic values that may
        # matter for decision making.
        for res in self.reservoirs:
            state["reservoirs"][res.id] = {
                "water_amount": res.water_amount,
                "water_area": res.water_area,
                "basin_area": res.basin_area,
                "capacity": res.capacity,
                "river_inflow": res.river_inflow,
                "natural_inflow": res.natural_inflow,
                "river_outflow": res.river_outflow,
                "generator_efficiency": res.generator_efficiency,
                "max_generator_flow": res.max_generator_flow,
                "generator_head_height": res.generator_head_height,
                "generator_flow": res.generator_flow,
                "is_raining": res.is_raining,
                "rain_forecast_probability": res.rain_forecast_probability,
                
                # Connection info – reference rivers by id only to avoid
                # circular references in the JSON-able state structure.
                "in_rivers": [river.id for river in res.in_rivers],
                "out_rivers": [river.id for river in res.out_rivers],
            }

        # Rivers – key operational limits and linkage to the downstream
        # reservoir.
        for river in self.rivers:
            state["rivers"][river.id] = {
                "length_in_timesteps": river.length_in_timesteps,
                "max_flow": river.max_flow,
                "current_flow": river.current_flow,
                "output_reservoir": river.output_reservoir.id if river.output_reservoir else None,
            }

        # Mountains with snow – include snowpack status and linkage to the
        # receiving reservoir.
        for mountain in self.mountains:
            state["mountains"][mountain.id] = {
                "current_snow_height": mountain.current_snow_height,
                "temperature": mountain.temperature,
                "snow_area": mountain.snow_area,
                "output_reservoir": mountain.output_reservoir.id if mountain.output_reservoir else None,
            }

        return state
        

    def create_norwegian_environment(self):
        """
        Creates the Norwegian reservoir system with the structure:
        Nyfjord -> Vestarne -> Tesselvannet
        Østarne -> Tesselvannet
        Tesselvannet -> Ocean (outlet)
        
        Sizes:
        - Nyfjord: Small reservoir, large basin
        - Vestarne: Largest reservoir
        - Østarne: Small reservoir
        - Tesselvannet: Medium reservoir
        """
        # Ensure data directory exists
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Use actual rain data files from data/rain_csv
        rain_data_path = {
            "nyfjord": os.path.join(self.data_dir, "nyfjord_rain_data.csv"),
            "vestarne": os.path.join(self.data_dir, "vestarne_rain_data.csv"),
            "ostarne": os.path.join(self.data_dir, "østarne_rain_data.csv"),
            "tesselvannet": os.path.join(self.data_dir,  "tesselvannet_rain_data.csv")
        }
        
        # Verify that all rain data files exist
        for name, path in rain_data_path.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"Rain data file not found: {path}")
        
        # Use existing snow data files from the data/snow_csv directory
        snow_data_paths = {
            "kolasnuten": os.path.join(self.data_dir, "Kølasnuten_snow_data.csv"),
            "bastihoyden_ost": os.path.join(self.data_dir, "Bastihøyden-Øst_snow_data.csv"),
            "bastihoyden_vest": os.path.join(self.data_dir, "Bastihøyden-Vest_snow_data.csv"),
            "tobikammen_nord": os.path.join(self.data_dir, "Tobikammen-Nord_snow_data.csv"),
            "tobikammen_sor": os.path.join(self.data_dir,  "Tobikammen-Sør_snow_data.csv")
        }
        
        # Verify that all snow data files exist
        for name, path in snow_data_paths.items():
            if not os.path.exists(path):
                raise FileNotFoundError(f"Snow data file not found: {path}")
        
        # Create the reservoirs
        # Tesselvannet (Medium)
        tesselvannet = Reservoir(
            id="Tesselvannet",
            rain_data_csv=rain_data_path["tesselvannet"]
        )
        tesselvannet.water_area = 5000000.0  # 5 km²
        tesselvannet.basin_area = 15000000.0  # 15 km²
        tesselvannet.capacity = 50000000.0  # 50 million m³
        tesselvannet.water_amount = 30000000.0  # Initial water: 60% full
        tesselvannet.generator_head_height = 40.0  # 40m head height
        tesselvannet.max_generator_flow = 100.0  # m³/s

        # Østarne (Small)
        ostarne = Reservoir(
            id="Østarne",
            rain_data_csv=rain_data_path["ostarne"]
        )
        ostarne.water_area = 2000000.0  # 2 km²
        ostarne.basin_area = 8000000.0  # 8 km²
        ostarne.capacity = 15000000.0  # 15 million m³
        ostarne.water_amount = 9000000.0  # Initial water: 60% full
        ostarne.generator_head_height = 30.0  # 30m head height
        ostarne.max_generator_flow = 50.0  # m³/s    
        
        # Vestarne (Largest)
        vestarne = Reservoir(
            id="Vestarne",
            rain_data_csv=rain_data_path["vestarne"]
        )
        vestarne.water_area = 8000000.0  # 8 km²
        vestarne.basin_area = 25000000.0  # 25 km²
        vestarne.capacity = 100000000.0  # 100 million m³
        vestarne.water_amount = 70000000.0  # Initial water: 70% full
        vestarne.generator_head_height = 60.0  # 60m head height
        vestarne.max_generator_flow = 150.0  # m³/s
        
        # Nyfjord (Small reservoir, large basin)
        nyfjord = Reservoir(
            id="Nyfjord",
            rain_data_csv=rain_data_path["nyfjord"]
        )
        nyfjord.water_area = 3000000.0  # 3 km²
        nyfjord.basin_area = 40000000.0  # 40 km² (large catchment area)
        nyfjord.capacity = 20000000.0  # 20 million m³
        nyfjord.water_amount = 16000000.0  # Initial water: 80% full
        nyfjord.generator_head_height = 25.0  # 25m head height
        nyfjord.max_generator_flow = 75.0  # m³/s
        
        # Create rivers
        # Nyfjord -> Vestarne (medium river, 2 days travel time)
        nyfjord_vestarne_river = River(
            id="Nyfjord-Vestarne",
            initial_water=5000.0,
            length_in_timesteps=2,
            max_flow=50.0 * 2,
            output_reservoir=vestarne
        )
        
        # Both Arne -> Tesselvannet (long river, 3 day travel time)
        arne_tesselvannet_river = River(
            id="Arne-Tesselvannet",
            initial_water=8000.0,
            length_in_timesteps=3,
            max_flow=80.0 * 3,
            output_reservoir=tesselvannet
        )
        
        # Tesselvannet -> Ocean (outlet river, no output reservoir)
        tesselvannet_ocean_river = River(
            id="Tesselvannet-Ocean",
            initial_water=10000.0,
            length_in_timesteps=2,
            max_flow=100.0 * 2,
            output_reservoir=None  # No reservoir at the end (ocean)
        )
        
        # Connect the reservoirs with their outflow rivers
        nyfjord.add_outflow_river(nyfjord_vestarne_river)
        vestarne.add_outflow_river(arne_tesselvannet_river)
        ostarne.add_outflow_river(arne_tesselvannet_river)
        tesselvannet.add_outflow_river(tesselvannet_ocean_river)
        
        # Add mountains with snow melting according to the specified connections
        # 1. Kølasnuten -> Nyfjord
        kolasnuten = MontainWithSnow(
            id="Kølasnuten",
            output_reservoir=nyfjord,
            in_file_csv=snow_data_paths["kolasnuten"]
        )
        kolasnuten.snow_area = 2500000.0  # 2.5 km²
        
        # 2. Bastihøyden mountains -> Both Østarne and Vestarne
        bastihoyden_ost = MontainWithSnow(
            id="Bastihøyden-Øst",
            output_reservoir=ostarne,
            in_file_csv=snow_data_paths["bastihoyden_ost"]
        )
        bastihoyden_ost.snow_area = 1800000.0  # 1.8 km²
        
        bastihoyden_vest = MontainWithSnow(
            id="Bastihøyden-Vest",
            output_reservoir=vestarne,
            in_file_csv=snow_data_paths["bastihoyden_vest"]
        )
        bastihoyden_vest.snow_area = 2200000.0  # 2.2 km²
        
        # 3. Tobikammen mountains -> Vestarne
        tobikammen_nord = MontainWithSnow(
            id="Tobikammen-Nord",
            output_reservoir=vestarne,
            in_file_csv=snow_data_paths["tobikammen_nord"]
        )
        tobikammen_nord.snow_area = 3000000.0  # 3 km²
        
        tobikammen_sor = MontainWithSnow(
            id="Tobikammen-Sør",
            output_reservoir=vestarne,
            in_file_csv=snow_data_paths["tobikammen_sor"]
        )
        tobikammen_sor.snow_area = 2800000.0  # 2.8 km²
        
        # Add all components to the simulation
        self.reservoirs.extend([nyfjord, ostarne, vestarne, tesselvannet])
        self.rivers.extend([nyfjord_vestarne_river,arne_tesselvannet_river, tesselvannet_ocean_river])
        self.mountains.extend([kolasnuten, bastihoyden_ost, bastihoyden_vest, tobikammen_nord, tobikammen_sor])


    def simulate_day(self, verbose=False):
        if verbose:
            print("Processing mountains...")
        for mountain in self.mountains:
            snow_melt = mountain.process_timestep()
            if verbose and snow_melt > 0:
                print(f"  {mountain.id}: {snow_melt:.2f} m³ snow melt at {mountain.temperature:.1f}°C")
        
        # Process reservoirs
        if verbose:
            print("Processing reservoirs...")
        total_production = 0
        
        for reservoir in self.reservoirs:
            reservoir.process_timestep()
            total_production += reservoir.current_production
            

        river_overflow_penalty = 0
        for river in self.rivers:
            flow = river.process_timestep()
            river_overflow_penalty += river.get_max_flow_penalty()            

            if verbose:
                print(f"  {river.id}: {flow:.2f} m³/s flow")

        # turn off all reservoirs
        for reservoir in self.reservoirs:
            reservoir.is_producing = False

        return total_production, river_overflow_penalty
            


if __name__ == "__main__":
    simulation = Simulation()
    simulation.create_norwegian_environment()
    
    # Simulate 10 days
    for day in range(10):
        print(f"\nDay {day+1}:")
        total_power = simulation.simulate_day(verbose=True)
        print(f"Total power production: {total_power:.2f} MWh") 

    