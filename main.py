# Description: A simple script to monitor the status of heaters and log the data to a CSV file.
# Using the mill generation 3 api
# https://github.com/Mill-International-AS/Generation_3_REST_API/

import requests, time, json, datetime, calendar
import os

# Update the following variables with the IP addresses of your heaters
heatersips        = [""]
previousTemps     = [0,0]
cumulative_energy = [0.0, 0.0]

LOW_TEMP_THRESHOLD  = 15
HIGH_TEMP_THRESHOLD = 25
MAX_RETRIES         = 3
RETRY_DELAY         = 5
LOG_INTERVAL        = 60

if os.path.exists("previous_state.json"):
    with open("previous_state.json", "r") as f:
        state = json.load(f)
        previousTemps = state.get("previousTemps", previousTemps)
        cumulative_energy = state.get("cumulative_energy", cumulative_energy)
else:
    print("No previous state file found. Starting fresh.\033[K")

with open("heaters_log.csv", "a") as log_file:
    if log_file.tell() == 0:
        log_file.write("timestamp,heater_ip,heater_name,ambient_temp,temp_diff,alert,cumulative_kWh\n")

import requests
import datetime

LAST_HOUR  = 0
LAST_PRICE = 0

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

print("\033[H\033[J", end="")
while True:
    EL_PRICE = get_current_price()
    print("\033[H\033[K", end="")
    print(f"Heater status. Time : {time.ctime()}\033[K")
    print(f"Current electricity price: {EL_PRICE:.2f} NOK/kWh\033[K")
    print("------------------------------------\033[K")

    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    log_lines = []
    total_pr_heater = 0
    for index, heater in enumerate(heatersips):
        attempts = 0
        response_data = None
        status_data = None

        while attempts < MAX_RETRIES:
            try:
                response = requests.get(f"http://{heater}/control-status", timeout=5)
                status_response = requests.get(f"http://{heater}/status", timeout=5)
                
                if response.status_code == 200 and status_response.status_code == 200:
                    response_data = response.json()
                    status_data = status_response.json()
                    break
                else:
                    print(f"Error: {response.status_code} from {heater}. Retrying...\033[K")
            except requests.exceptions.RequestException as e:
                print(f"Request error from {heater}: {e}\033[K")
            
            attempts += 1
            time.sleep(RETRY_DELAY)

        if response_data is None or status_data is None:
            print(f"Could not retrieve data from {heater} after {MAX_RETRIES} attempts. Skipping...\033[K")
            continue

        ambient_temperature = response_data['ambient_temperature']
        set_temperature     = response_data['set_temperature']
        control_signal      = response_data['control_signal']
        current_power       = response_data['current_power']
        old_temp = previousTemps[index]
        temp_diff = ambient_temperature - old_temp

        if ambient_temperature < old_temp:
            print(f"Temperature is decreasing in {heater}\033[K")
            print(f"From \033[94m{old_temp}\033[0m to \033[94m{ambient_temperature}\033[0m\033[K")
        elif ambient_temperature > old_temp:
            print(f"Temperature is increasing in {heater}\033[K")
            print(f"From \033[91m{old_temp}\033[0m to \033[91m{ambient_temperature}\033[0m\033[K")
        else:
            print(f"Temperature is stable in {heater}: \033[92m{ambient_temperature}\033[0m\033[K")

        previousTemps[index] = ambient_temperature

        alert_message = ""
        if ambient_temperature < LOW_TEMP_THRESHOLD:
            alert_message = f"ALERT: Temperature below {LOW_TEMP_THRESHOLD}°C!"
        elif ambient_temperature > HIGH_TEMP_THRESHOLD:
            alert_message = f"ALERT: Temperature above {HIGH_TEMP_THRESHOLD}°C!"

        interval_energy_kWh = current_power / (60.0 * 1000.0)
        cumulative_energy[index] += interval_energy_kWh

        print(f"Heater name         : {status_data['name']}\033[K")
        print(f"ambient_temperature : {ambient_temperature} °C\033[K")
        print(f"set_temperature     : {set_temperature} °C\033[K")
        print(f"control_signal      : {control_signal}\033[K")
        print(f"current_power       : {current_power} W\033[K")
        print(f"Cumulative energy   : {cumulative_energy[index]:.6f} kWh\033[K")
        print(f"Current cost pr hour: {current_power/1000*EL_PRICE:.2f} NOK\033[K")
        if alert_message:
            print(f"\033[93m{alert_message}\033[0m\033[K")
        print("------------------------------------\033[K")
        total_pr_heater += current_power/1000*EL_PRICE
        log_lines.append(
            f"{current_time},{heater},{status_data['name']},{ambient_temperature},{temp_diff},{alert_message},{cumulative_energy[index]:.6f}\n"
        )

    with open("previous_state.json", "w") as f:
        json.dump({"previousTemps": previousTemps, "cumulative_energy": cumulative_energy}, f)

    with open("heaters_log.csv", "a") as log_file:
        for line in log_lines:
            log_file.write(line)

    now = datetime.datetime.now()
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    
    print(f"Total cost pr day: {(total_pr_heater * 24):.2f} NOK\033[K")
    print(f"Total cost pr month: {((total_pr_heater * 24) * days_in_month):.2f} NOK\033[K")
    time.sleep(LOG_INTERVAL)
