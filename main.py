# Description: A simple script to monitor the status of heaters and log the data to a CSV file.
# Using the mill generation 3 api and hva koster strømmen api.
# https://github.com/Mill-International-AS/Generation_3_REST_API/
# https://www.hvakosterstrommen.no/strompris-api/
# https://api.met.no/weatherapi/locationforecast/2.0/mini.json?lat=?&lon=?
import requests, time, json, datetime, calendar
import os

# Update the following variables with the IP addresses of your heaters
heatersips        = [""]
previousTemps     = [0,0]
cumulative_energy = [0.0, 0.0]

SLEEP_TIME = 60

LAST_HOUR  = 0
LAST_PRICE = 0

LAST_TEMP = 0

# Update the following variables with the latitude and longitude of your location
WEATHER_LAT = 0
WEATHER_LON = 0

heater_data = {}

# Function to get the current electricity price from the hvakosterstrommen API
def get_current_price(region="NO1"):
    now = datetime.datetime.now()
    global LAST_HOUR
    global LAST_PRICE
    if now.hour == LAST_HOUR:
        return LAST_PRICE
    date_str = now.strftime("%Y/%m-%d")
    url = f"https://www.hvakosterstrommen.no/api/v1/prices/{date_str}_{region}.json"
    response = requests.get(url)
    data = response.json()

    for entry in data:
        start_time = datetime.datetime.fromisoformat(entry["time_start"]).replace(tzinfo=None)
        end_time   = datetime.datetime.fromisoformat(entry["time_end"]).replace(tzinfo=None)

        if start_time <= now < end_time:
            LAST_HOUR = start_time.hour
            LAST_PRICE = entry["NOK_per_kWh"]
            return entry["NOK_per_kWh"]

    return None

def get_operation_mode(heater):
    print(f"Getting operation mode from heater '{heater}'")
    r = requests.get(f"http://{heater}/operation-mode", timeout=5)
    if r.status_code != 200:
        return None
    return r.json()

def check_heater_mode():
    controlIndividually = True
    for heater in heatersips:
        s_operation_mode = get_operation_mode(heater)
        if s_operation_mode is None:
            print(f"Failed to get operation mode from heater {heater}")
            continue
        operation_mode = s_operation_mode["mode"]
        if operation_mode != "Control individually":
            print(f"Heater {heater} is not in 'Control individually' mode")
            print("This script requires all heaters to be in 'Control individually' mode to function properly")
            print("Do you want to change the operation mode of all heaters to 'Control individually'? (y/n)")
            answer = input()
            if answer == "y":
                r = requests.post(f"http://{heater}/operation-mode", json={"mode": "Control individually"}, timeout=5)
                if r.status_code != 200:
                    print(f"Failed to set operation mode of heater {heater}")
                    controlIndividually = False
            break

    if not controlIndividually:
        print("This script requires all heaters to be in 'Control individually' mode")
        print("This is to ensure that the script can control the heaters individually")
        time.sleep(5)
        exit()

def get_temperature_lat_long(lat, lon):
    if datetime.datetime.now().hour == LAST_HOUR and LAST_TEMP != 0:
        return LAST_TEMP
    headers = {
        'User-Agent': 'weatherCheck/1.0 (+https://darahz.com)'
    }
    url = f"https://api.met.no/weatherapi/locationforecast/2.0/mini.json?lat={lat}&lon={lon}"
    response = requests.get(url, headers=headers)
    data = response.json()
    return data["properties"]["timeseries"][0]["data"]["instant"]["details"]["air_temperature"]

def analyze_temperature_trend_detail(heater_data, heater, recent_count=5):
    """
    Analyze the temperature trend for a specific heater, showing the sequence of changes.
    
    Args:
        heater_data (dict): The dictionary containing temperature data for heaters.
        heater (str): The heater identifier to analyze.
        recent_count (int): The number of recent data points to consider.

    Returns:
        str: A detailed description of the trend sequence (e.g., "down, up, down"),
             or "no data" if the heater has no recorded data.
    """

    if heater not in heater_data or not heater_data[heater]:
        return "no data"

    temperatures = [entry["room_temp"] for entry in heater_data[heater][-recent_count:]]

    if len(temperatures) < 2:
        return "no data"

    deltas = [temperatures[i] - temperatures[i - 1] for i in range(1, len(temperatures))]

    trend_sequence = []
    for delta in deltas:
        if delta > 0:
            trend_sequence.append("up")
        elif delta < 0:
            trend_sequence.append("down")
        else:
            trend_sequence.append("no change")

    return ", ".join(trend_sequence)

#TODO: Will fix this later
#check_heater_mode()

if os.path.exists("heater_data.csv"):
    print("Removing previous data file for data logging")
    os.remove("heater_data.csv")

print("\033[H\033[J", end="")
while True:
    EL_PRICE = get_current_price()
    weather  = get_temperature_lat_long(WEATHER_LAT, WEATHER_LON)

    print("\033[H\033[J", end="")
    print(f"Time : {time.ctime()} Outdoor temperature {weather} \033[K")
    print(f"Current electricity price: {EL_PRICE:.2f} NOK/kWh\033[K")
    print("------------------------------------\033[K")
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    for index, heater in enumerate(heatersips):
        if heater not in heater_data:
            heater_data[heater] = []

        r_controlStatus = requests.get(f"http://{heater}/control-status", timeout=5)
        r_status        = requests.get(f"http://{heater}/status", timeout=5)
        r_caliboffset   = requests.get(f"http://{heater}/temperature-calibration-offset", timeout=5)

        if r_controlStatus.status_code != 200 or r_status.status_code != 200 or r_caliboffset.status_code != 200:
            print(f"Failed to get status from heater {heater}\033[K")
            continue
        r_controlStatus = r_controlStatus.json()
        r_status        = r_status.json()
        r_caliboffset   = r_caliboffset.json()

        f_amb_temp  = r_controlStatus["ambient_temperature"]
        f_set_temp  = r_controlStatus['set_temperature']
        f_cur_watt  = r_controlStatus['current_power']
        print(f"Room temperature: {f_amb_temp:.2f}°C\033[K")
        print(f"Set temperature : {f_set_temp:.2f}°C\033[K")
        if f_cur_watt > 0:
            cumulative_energy[index] += f_cur_watt * SLEEP_TIME / 3600
            print(f"Cumulative energy usage: {cumulative_energy[index]:.2f} kWh\033[K")
            print(f"Energy cost pr hour: {(cumulative_energy[index]/1000) * EL_PRICE:.2f} NOK")
            print(f"Energy cost pr day: {(cumulative_energy[index]/1000) * EL_PRICE * 24:.2f} NOK")
        print(f"Power usage {f_cur_watt} W\033[K")
        if r_caliboffset['value'] > 0:
            print(f"Calibration offset : +{r_caliboffset['value']:.2f}°C\033[K")
        
        trend = analyze_temperature_trend_detail(heater_data, heater)
        amt_trend = trend.split(",")
        if trend != "no data" and len(amt_trend) > 3:
            with open("heater_data.csv", "a") as f:
                f.write(f"{current_time},{f_amb_temp},{f_set_temp},{r_caliboffset['value']},{EL_PRICE},{f_cur_watt},{trend}\n")
        print(f"Temperature trend: {trend}\033[K")
        print("------------------------------------\033[K")

        heater_data[heater].append({
            "time": current_time,
            "room_temp": f_amb_temp,
            "set_temp": f_set_temp,
            "calib_offset": r_caliboffset['value'],
            "price": EL_PRICE
        })
    time.sleep(SLEEP_TIME)
