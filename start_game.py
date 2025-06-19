import argparse
import requests

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Start the game by calling the /start endpoint')
    parser.add_argument('--password', '-p', required=True, help='Password for authentication')
    parser.add_argument('--host', default='http://localhost:8000', help='Server host (default: http://localhost:8000)')    
    parser.add_argument('--n_timesteps', '-n', type=int, default=20, help='Number of timesteps (default: 20)')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Prepare the request
    url = f"{args.host}/start"
    params = {"pwd": args.password, "num_timesteps": args.n_timesteps}  # Changed from JSON body to query parameter
    
    try:
        # Call the /start endpoint
        response = requests.post(url, params=params)  # Using params instead of json
        
        # Check the response
        if response.status_code == 200:
            print("Game started successfully!")
            print(response.json())
        else:
            print(f"Error starting game. Status code: {response.status_code}")
            print(response.text)
    
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    main()