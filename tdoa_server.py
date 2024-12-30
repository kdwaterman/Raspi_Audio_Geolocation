import numpy as np
import folium
from folium.features import DivIcon
import socket
import json


def compute_hyperbola_local(R1_latlon, R2_latlon, delta_t, v, num_points=1000):
    """
    Compute the hyperbola of points satisfying the TDOA constraint between two receivers.
    Approximates the Earth's surface as flat over small distances.

    """
    # Unpack receiver coordinates
    lat1, lon1 = R1_latlon
    lat2, lon2 = R2_latlon

    # Approximate conversions: degrees to meters
    # At the equator: 1 degree latitude ~ 111.32 km, longitude varies with latitude
    mean_lat = np.radians((lat1 + lat2) / 2)
    m_per_deg_lat = 111132.92 - 559.82 * np.cos(2 * mean_lat) + 1.175 * np.cos(4 * mean_lat) - 0.0023 * np.cos(6 * mean_lat)
    m_per_deg_lon = 111412.84 * np.cos(mean_lat) - 93.5 * np.cos(3 * mean_lat) + 0.118 * np.cos(5 * mean_lat)

    # Convert lat/lon to local Cartesian coordinates (meters)
    x1 = (lon1 - lon1) * m_per_deg_lon  # Reference point at Receiver 1
    y1 = (lat1 - lat1) * m_per_deg_lat
    x2 = (lon2 - lon1) * m_per_deg_lon
    y2 = (lat2 - lat1) * m_per_deg_lat

    # Compute the difference in distances based on the TDOA
    delta_d = delta_t * v
    # Distance between the two receivers
    d = np.hypot(x2 - x1, y2 - y1)
    # Half the distance between receivers (focal length)
    c = d / 2

    # Check if a real hyperbola exists
    if abs(delta_d) > d:
        print(f"time distance = {delta_d}, physical distance = {d}" )
        raise ValueError("No real hyperbola exists: the absolute value of delta_d is greater than the distance between receivers.")

    # Semi-major axis
    a = abs(delta_d) / 2

    # Handle the degenerate case when delta_d is zero
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
        b = np.sqrt(c**2 - a**2)

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
    
def generate_map(reciever_data):
    """
    Generate the hyperbolic curve for the two recievers. 
    """
    
    v = 343  # m/s
    delta_t = (reciever_data['reciever1']['time'] - reciever_data['reciever2']['time']) / 1_000_000_000
    R1_latlon = (reciever_data['reciever1']['lat'],reciever_data['reciever1']['lon'])
    R2_latlon = (reciever_data['reciever2']['lat'],reciever_data['reciever2']['lon'])
	
    lats, lons = compute_hyperbola_local(R1_latlon, R2_latlon, delta_t, v)

    # Create a Folium map centered between the receivers
    map_center = ((R1_latlon[0] + R2_latlon[0]) / 2, (R1_latlon[1] + R2_latlon[1]) / 2)
    m = folium.Map(location=map_center, zoom_start=15)

    # Add the hyperbola to the map
    hyperbola_coords = list(zip(lats, lons))
    folium.PolyLine(hyperbola_coords, color="red", weight=2.5, opacity=1).add_to(m)

    # Add markers for the receivers
    folium.Marker(R1_latlon, popup="Receiver 1", icon=folium.Icon(color='blue')).add_to(m)
    folium.Marker(R2_latlon, popup="Receiver 2", icon=folium.Icon(color='green')).add_to(m)

    # Optionally, label the receivers
    folium.map.Marker(
        R1_latlon,
        icon=DivIcon(
            icon_size=(150,36),
            icon_anchor=(0,0),
            html='<div style="font-size: 12pt; color : blue">Receiver 1</div>',
        )
    ).add_to(m)

    folium.map.Marker(
        R2_latlon,
        icon=DivIcon(
            icon_size=(150,36),
            icon_anchor=(0,0),
            html='<div style="font-size: 12pt; color : green">Receiver 2</div>',
        )
    ).add_to(m)

    # Save the map to an HTML file
    m.save(f"hyperbola_map_{time.time()}.html")


def run_server():
    # create a socket object
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    server_ip = "0.0.0.0"
    port = 65432

    # bind the socket to a specific address and port
    server.bind((server_ip, port))
 
    print(f"Listening on {server_ip}:{port}")

    rec_names = ["reciever1","reciever2"]
    rec_list = {}
    # receive data from the client
    while True:
        data, addr = server.recvfrom(1024)
        msg = data.decode("utf-8") # convert bytes to string
        json_msg = json.loads(msg)
        host = json_msg['hostname']
        rec_list[host] = json_msg
        try:
            rec_names.remove(host)
        except:
            pass
        print(f"Received: {json_msg['lat']}, {json_msg['lon']}, at time {json_msg['time']} from {host}")
        if len(rec_names) == 0:
                generate_map(rec_list)
                break


    # close server socket
    server.close()


run_server()

