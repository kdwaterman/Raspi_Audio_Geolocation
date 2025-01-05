import pyaudio
import numpy as np
import time
import datetime
import matplotlib.pyplot as plt
import socket
import gpsd  # For GPS data via gpsd
import json

# Configuration parameters
SAMPLE_RATE = 44100  # 44.1 kHz sample rate
CHUNK_SIZE = 128    # Size of each audio chunk
TARGET_FREQUENCY = 4000  # Frequency to detect (in Hz)
AMPLITUDE_THRESHOLD = 5000  # Amplitude threshold for detection

# Socket configuration
SERVER_IP = '10.42.0.120'   # Replace with the IP address of the target device
SERVER_PORT = 65432  # Replace with the port number of the target device
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("here")
# Initialize gpsd connection
try:
    gpsd.connect()  # Connect to gpsd running on localhost
except Exception as e:
    print(f"Error connecting to GPSD: {e}")
    exit(1)

# Function to get GPS fix from gpsd
def get_gps_fix():
    gps_stamp = "No valid GPS fix"
    try:
        packet = gpsd.get_current()
        if packet.mode >= 2:  # Check if we have a 2D fix (mode 2) or better
            latitude = packet.lat
            longitude = packet.lon
            gps_stamp = {"Lat":latitude,"Lon":longitude}
    except Exception as e:
        print(f"Error fetching GPS data: {e}")
    return gps_stamp
print("here2")
gps_fix = get_gps_fix()

# Set up PyAudio for audio streaming
audio = pyaudio.PyAudio()
stream = audio.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=CHUNK_SIZE)

print("Listening for target frequency...")

try:
    while True:

        # Read audio data from the stream
        data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        audio_data = np.frombuffer(data, dtype=np.int16)

        # Perform Fourier Transform
        fft_result = np.fft.fft(audio_data)
        freqs = np.fft.fftfreq(len(fft_result), 1 / SAMPLE_RATE)

        # Get the magnitude of the FFT result
        magnitude = np.abs(fft_result)

        # Find the index of the target frequency
        target_index = np.argmin(np.abs(freqs - TARGET_FREQUENCY))


        # Check if the amplitude at the target frequency exceeds the threshold
        if magnitude[target_index] > AMPLITUDE_THRESHOLD:
        # Get the current timestamp with nanosecond accuracy
           timestamp_ns = time.time_ns()

        # Get the current GPS fix
           gps_stamp = get_gps_fix()

            # Print and send timestamp and GPS data via socket
           message = f"Frequency detected at: {timestamp_ns}, {gps_stamp}"
           print(message)
           data_to_send = {'lat':gps_stamp['Lat'], 'lon':gps_stamp['Lon'],'time':timestamp_ns,'hostname':socket.gethostname() }
           data_to_send = json.dumps(data_to_send)
           sock.sendto(f"{data_to_send}".encode('utf-8'),(SERVER_IP,SERVER_PORT))

           # Plot the frequency spectrum
           plt.figure(figsize=(10, 6))
           plt.plot(freqs[:len(freqs)//2], magnitude[:len(magnitude)//2])
           plt.xlabel('Frequency (Hz)')
           plt.ylabel('Magnitude')
           plt.title('Frequency Spectrum')
           plt.grid()
           plt.show()
           break

except KeyboardInterrupt:
    
    print("Interrupted by user.")

finally:
    # Clean up the stream and audio interface
    stream.stop_stream()
    stream.close()
    audio.terminate()
    sock.close()

