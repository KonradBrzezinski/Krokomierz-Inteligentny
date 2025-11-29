from machine import Pin, I2C
import ssd1306
import mpu6050
import time
import usocket as socket
import network
import json
from step_detector import StepDetector

SSID = ''
PASSWORD = ''

I2C_SCL_PIN = 9
I2C_SDA_PIN = 8

steps = 0
last_gyro_update_ms = time.ticks_ms()
GYRO_UPDATE_INTERVAL_MS = 50 # Częstotliwość aktualizacji MPU/OLED
# Parametry krokomierza
GYRO_FORWARD_THRESHOLD = 40.0
GYRO_BACKWARD_THRESHOLD = -40.0
GYRO_RESET_THRESHOLD = 15.0

try:
    i2c = I2C(scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN))
    accel_sensor = mpu6050.MPU6050(bus=i2c)
    display = ssd1306.SSD1306_I2C(128, 32, i2c)
    display.fill(0)
    display.text('Inicjalizacja...', 0, 0, 1)
    display.show()
except Exception as e:
    print(f"Błąd inicjalizacji I2C/czujników: {e}")

def connect_wifi():
    """Łączy się z siecią WiFi i wyświetla status na OLED."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print(f'Łączenie z siecią {SSID}...')
        display.fill(0)
        display.text(f"Laczenie z {SSID}", 0, 0, 1)
        display.show()
        wlan.connect(SSID, PASSWORD)
        max_wait = 20
        while max_wait > 0:
            if wlan.isconnected():
                break
            time.sleep(1)
            max_wait -= 1

    if wlan.isconnected():
        ip_addr = wlan.ifconfig()[0]
        print(f'Połączono! Adres IP: {ip_addr}')
        display.fill(0)
        display.text(f"IP: {ip_addr}", 0, 0, 1)
        display.text('Serwer MPU ON', 0, 16, 1)
        display.show()
        return ip_addr
    else:
        display.fill(0)
        display.text('Blad WiFi!', 0, 0, 1)
        display.show()
        raise RuntimeError('Nie udalo sie polaczyc z siecia WiFi.')

def get_steps_json():
    """Zwraca dane krokomierza w formacie JSON."""
    return json.dumps({"steps": steps})

ip_addr = connect_wifi()
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(addr)
s.listen(1)

s.setblocking(False) 
print('Serwer nasłuchuje na porcie 80...')

krokomierz = StepDetector()

while True:
    current_time = time.ticks_ms()
    
    if time.ticks_diff(current_time, last_gyro_update_ms) > GYRO_UPDATE_INTERVAL_MS:
        try:
            # Odczyt MPU
            accel_data = accel_sensor.read_accel_data()
            ax = accel_data['x']
            ay = accel_data['y']
            az = accel_data['z']

            krokomierz.process_sample(ax, ay, az)
            steps = krokomierz.get_step_count()

            # Wyświetlanie danych
            display.fill(0)
            display.text("KROKI: " + str(steps), 0, 0, 1)
            display.text(f"IP: {ip_addr}", 0, 24, 1)
            display.show()
            
            last_gyro_update_ms = current_time

        except Exception as e:
            print(f"Błąd odczytu MPU/OLED: {e}")
            pass # Ignoruj błędy czujnika, aby pętla działała dalej

    try:
        conn, addr = s.accept()
    except OSError as e:
        if e.args[0] in (11, 35, 110): 
            time.sleep_ms(1) 
            continue 
        else:
            print(f"Krytyczny błąd s.accept(): {e}")
            time.sleep(1)
            continue
        
    print(f'Got a connection from {str(addr)}')
    
    try:
        conn.settimeout(0.1) 
        request = conn.recv(512).decode('utf-8')
        request_line = request.split('\r\n')[0]
        print(f"Odebrano zadanie: {request_line}")
        http_status = "200 OK"
        json_data = None
        if request_line.startswith('GET /steps'):
            json_data = get_steps_json()
        elif request_line.startswith('GET /zeruj'):
            krokomierz.reset_step_count()
            json_data = get_steps_json()
        elif request_line.startswith('GET /dodaj'):
            steps = krokomierz.add_step()
            json_data = get_steps_json()
        elif request_line.startswith('OPTIONS'):
            pass
        else:
            http_status = "404 Not Found"
            json_data = "<h1>404 Not Found</h1>"

        response = f"HTTP/1.1 {http_status}\r\n"
        response += "Access-Control-Allow-Origin: *\r\n"
        response += "Access-Control-Allow-Methods: GET, OPTIONS\r\n"
        response += "Access-Control-Allow-Headers: Content-Type\r\n"
        response += "Connection: close\r\n"
        
        if json_data is not None:
            response += "Content-Type: application/json\r\n"
            response += f"Content-Length: {len(json_data)}\r\n\r\n"
            response += json_data
        elif http_status == "404 Not Found":
            # Dla prostego 404
            response += "Content-Type: text/html\r\n"
            response += f"Content-Length: {len(json_data)}\r\n\r\n"
            response += json_data
        else:
            response += "\r\n"
            
        conn.sendall(response.encode())

    except OSError as e:
        if e.args[0] not in (11, 35, 110):
            print(f"Blad socket podczas recv/send: {e}")
        pass
    except Exception as e:
        print(f"Nieznany błąd w obsłudze HTTP: {e}")
        pass
    finally:
        if 'conn' in locals():
            conn.close()
            print("Połączenie zamknięte.")
