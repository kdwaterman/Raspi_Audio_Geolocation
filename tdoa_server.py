import numpy as np
import folium
from folium.features import DivIcon
import socket
import json
import time
from itertools import combinations, permutations

def compute_hyperbola_local(R1_latlon, R2_latlon, delta_t, v, num_points=1000):
    """
    Compute the hyperbola of points satisfying the TDOA constraint between two receivers.
    Approximates the Earth's surface as flat over small distances.
    
    """
    # Unpack receiver coordinates
    lat1, lon1 = R1_latlon
    lat2, lon2 = R2_latlon

    # Approximate conversions: degrees to meters
    mean_lat = np.radians((lat1 + lat2) / 2)
    m_per_deg_lat = (
        111132.92
        - 559.82 * np.cos(2 * mean_lat)
        + 1.175 * np.cos(4 * mean_lat)
        - 0.0023 * np.cos(6 * mean_lat)
    )
    m_per_deg_lon = (
        111412.84 * np.cos(mean_lat)
        - 93.5 * np.cos(3 * mean_lat)
        + 0.118 * np.cos(5 * mean_lat)
    )

    # Convert lat/lon to local Cartesian coordinates (meters) relative to Receiver 1
    x1 = 0
    y1 = 0
    x2 = (lon2 - lon1) * m_per_deg_lon
    y2 = (lat2 - lat1) * m_per_deg_lat

    # Compute the difference in distances based on the TDOA
    delta_d = delta_t * v

    # Distance between the two receivers
    d = np.hypot(x2 - x1, y2 - y1)
    c = d / 2  # Half the distance between receivers (focal length)

    # Check if a real hyperbola exists
    if abs(delta_d) > d:
        print(f"Time difference * speed = {delta_d} m, which is greater than the distance between receivers = {d} m.")
        raise ValueError("No real hyperbola exists: |delta_d| > distance between receivers.")

    # Semi-major axis
    a = abs(delta_d) / 2

    # Handle the case when delta_d is zero 
    if a == 0:
        # Midpoint between the receivers
        x0 = (x1 + x2) / 2
        y0 = (y1 + y2) / 2
        dx = x2 - x1
        dy = y2 - y1

        # Determine the perpendicular bisector
        if dy == 0:
            x = np.full(num_points, x0)
            y = np.linspace(y0 - 10000, y0 + 10000, num_points)
        elif dx == 0:
            x = np.linspace(x0 - 10000, x0 + 10000, num_points)
            y = np.full(num_points, y0)
        else:
            slope = -dx / dy
            x = np.linspace(x0 - 10000, x0 + 10000, num_points)
            y = slope * (x - x0) + y0
    else:
        # Semi-minor axis
        try:
            b = np.sqrt(c**2 - a**2)
        except ValueError:
            print(f"Invalid hyperbola parameters: c={c}, a={a}.")
            raise

        # Midpoint between the receivers (hyperbola center)
        x0 = (x1 + x2) / 2
        y0 = (y1 + y2) / 2

        # Angle to rotate the coordinate system
        theta = np.arctan2(y2 - y1, x2 - x1)

        # Parameter u for the hyperbola equation
        u_max = np.arccosh(10)  # Adjust for desired extent
        u = np.linspace(-u_max, u_max, num_points)

        # Hyperbola in rotated coordinate system
        x_prime = a * np.cosh(u)
        y_prime = b * np.sinh(u)

        # Reflect hyperbola if delta_d is negative
        if delta_d < 0:
            x_prime = -x_prime

        # Rotate back to the original coordinate system
        cos_theta = np.cos(theta)
        sin_theta = np.sin(theta)
        x_rotated = x_prime * cos_theta - y_prime * sin_theta
        y_rotated = x_prime * sin_theta + y_prime * cos_theta

        # Translate back to the original position
        x = x_rotated + x0
        y = y_rotated + y0

    # Convert local Cartesian coordinates back to latitude and longitude
    lons = x / m_per_deg_lon + lon1
    lats = y / m_per_deg_lat + lat1

    return lats, lons

def generate_map(receiver_data):
    """
    Generate the hyperbolic curves for all unique receiver pairs and plot them on a Folium map.

    """
    v = 343  # Speed of sound in m/s (adjust as needed)

    # List of receiver names
    receiver_names = list(receiver_data.keys())
    num_receivers = len(receiver_names)

    if num_receivers < 2:
        raise ValueError("At least two receivers are required to compute hyperbolas.")

    # Generate all unique unordered pairs of receivers
    receiver_pairs = list(combinations(receiver_names, 2))

    hyperbola_list = []
    colors = ['red', 'blue', 'green']  # Predefined colors for consistency

    for idx, (ref, non_ref) in enumerate(receiver_pairs):
        pair_key = f"{ref}_vs_{non_ref}"
        print(pair_key)
        
        # Calculate delta_t
        delta_t = (receiver_data[ref]['time'] - receiver_data[non_ref]['time']) / 1_000_000_000  # Convert ns to seconds

        R_ref_latlon = (receiver_data[ref]['lat'], receiver_data[ref]['lon'])
        R_non_latlon = (receiver_data[non_ref]['lat'], receiver_data[non_ref]['lon'])

        try:
            lats, lons = compute_hyperbola_local(R_ref_latlon, R_non_latlon, delta_t, v)
            hyperbola_list.append({
                'pair': pair_key,
                'lats': lats,
                'lons': lons,
                'color': colors[idx % len(colors)]  # Assign colors cyclically
            })
        except ValueError as e:
            print(f"Skipping pair {pair_key}: {e}")

    if not hyperbola_list:
        print("No valid hyperbolas to plot. Exiting map generation.")
        return

    # Create a Folium map centered at the average location of all receivers
    avg_lat = np.mean([receiver_data[rec]['lat'] for rec in receiver_names])
    avg_lon = np.mean([receiver_data[rec]['lon'] for rec in receiver_names])
    m = folium.Map(location=(avg_lat, avg_lon), zoom_start=15)

    # Add all hyperbolas to the map
    for hyper in hyperbola_list:
        hyperbola_coords = list(zip(hyper['lats'], hyper['lons']))
        folium.PolyLine(
            hyperbola_coords,
            color=hyper['color'],
            weight=2.5,
            opacity=0.7,
            popup=hyper['pair']
        ).add_to(m)

    # Add markers for all receivers
    marker_colors = ['blue', 'green', 'purple']  # Distinct colors for receivers
    for idx, rec in enumerate(receiver_names):
        folium.Marker(
            (receiver_data[rec]['lat'], receiver_data[rec]['lon']),
            popup=f"{rec.capitalize()}",
            icon=folium.Icon(color=marker_colors[idx % len(marker_colors)])
        ).add_to(m)
        
        # Optionally, label the receivers
        folium.map.Marker(
            (receiver_data[rec]['lat'], receiver_data[rec]['lon']),
            icon=DivIcon(
                icon_size=(150,36),
                icon_anchor=(0,0),
                html=f'<div style="font-size: 12pt; color : {marker_colors[idx % len(marker_colors)]}">{rec.capitalize()}</div>',
            )
        ).add_to(m)

    # Save the map to an HTML file with timestamp
    timestamp = int(time.time())
    map_filename = f"hyperbola_map_{timestamp}.html"
    m.save(map_filename)
    print(f"Map saved to {map_filename}")

def run_server():
    """
    Run a UDP server to receive data from three receivers and generate a map once all data is received.
    """
    # Create a UDP socket
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    server_ip = "0.0.0.0"
    port = 65432

    # Bind the socket to the address and port
    server.bind((server_ip, port))
 
    print(f"Listening on {server_ip}:{port}")

    # Define the expected receiver names
    expected_receivers = ["reciever1", "reciever2", "reciever3"]
    received_data = {}
    
    while True:
        try:
            data, addr = server.recvfrom(4096)  # Increased buffer size for more data
            msg = data.decode("utf-8")  # Convert bytes to string
            json_msg = json.loads(msg)
            host = json_msg['hostname'].lower()  # Ensure consistency in receiver names

            if host not in expected_receivers:
                print(f"Unknown receiver '{host}' from {addr}. Ignoring.")
                continue

            received_data[host] = json_msg
            print(f"Received from {host}: lat={json_msg['lat']}, lon={json_msg['lon']}, time={json_msg['time']}")

            # Check if all expected receivers have sent data
            if all(rec in received_data for rec in expected_receivers):
                print("All receiver data received. Generating map...")
                generate_map(received_data)
                break
        except json.JSONDecodeError:
            print(f"Received invalid JSON from {addr}. Ignoring.")
        except KeyError as e:
            print(f"Missing key {e} in the received data from {addr}. Ignoring.")
        except Exception as e:
            print(f"Error processing data from {addr}: {e}. Ignoring.")

    # Close the server socket
    server.close()
    print("Server closed.")

if __name__ == "__main__":
    run_server()

