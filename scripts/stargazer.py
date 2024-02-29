import datetime
import os
import requests
import http.client
import urllib

import julian
from PyAstronomy import pyasl

from dotenv import load_dotenv
load_dotenv()

home_lat= os.environ.get('home_lat')
home_lon= os.environ.get('home_lon')

pushover_token = os.environ.get('pushover_token')
pushover_user = os.environ.get('pushover_user')

def json_extract(obj, key):
    """Nested json extract function

    Args:
        obj (dict): Dictionary you're searching through
        key (str): Key you're looking for

    Returns:
        list: Returns a list of every dictionary value at key
    """    
    arr = []


    def extract(obj, arr, key):
        # If object is a dictionary, for kv pair check if v is a dictionary as well
        if isinstance(obj, dict):
            for k, v in obj.items():
                # If so, recursively run the function. 
                if isinstance(v, (dict, list)):
                    extract(v, arr, key)
                # If not, check if k is a match and append to array if so
                elif k == key:
                    arr.append(v)
        # If object is a list, run a similar process but with list items
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, key)
        return arr

    values = extract(obj, arr, key)
    return values

def send_notification(message):

    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request("POST", "/1/messages.json",
    urllib.parse.urlencode({
        "token": f"{pushover_token}",
        "user": f"{pushover_user}",
        "message": message,
    }), { "Content-type": "application/x-www-form-urlencoded" })
    conn.getresponse()

def get_5_day_moon_forecast():

    # Julian Date - Creates an array of dates for the next 5 days. Extra day added for padding
    jd = pyasl.jdcnv(datetime.datetime.now())
    jd_list = []
    for i in range(0,6):
        jd_list.append(jd+i)

    # Moon Position
    pos = pyasl.moonpos(jd_list)
    
    # Moon Phase
    phase = pyasl.moonphase(jd_list)

    moon_dict = {
        'date':[datetime.datetime.strftime(julian.from_jd(jd), '%Y-%m-%d') for jd in jd_list],
        'illum':phase*100,
        'dist':pos[2],
        'geo_lon':pos[3],
        'geo_lat':pos[4]
    }

    return moon_dict

def get_5_day_sky_forecast(lat, lon, tz='America/Los_Angeles', start_hour=22, end_hour=4):
    
    api_key = os.environ.get('weather_api_key')

    response = requests.get(f'https://api.tomorrow.io/v4/weather/forecast?location={home_lat},{home_lon}&apikey={api_key}')

    time = json_extract(response.json()['timelines']['hourly'], 'time')
    vis = json_extract(response.json()['timelines']['hourly'], 'visibility')
    cover = json_extract(response.json()['timelines']['hourly'], 'cloudCover')

    from collections import defaultdict

    # Create a defaultdict to store data for each day
    sky_dict = defaultdict(lambda: {'date': None, 'vis_avg': 0, 'cover_avg': 0})

    # Iterate through the timestamps and aggregate data

    first_day = time[0].split('T')[0]
    prev_day = None
    target_day = None
    vis_list = []
    cover_list = []

    sky_list = list(zip(time,vis,cover))
    accepted_times = [f'{i:02d}:00:00Z' for i in range(6,13)]

    for timestamp in sky_list:
        
        day, vis, cover = timestamp
        if day.split('T')[1] in accepted_times:
            day_key = day.split('T')[0]

            sky_dict[day_key]['date'] = day_key
            if (day_key == target_day) or (day_key == first_day):
                vis_list.append(vis)
                cover_list.append(cover)
                prev_day = day_key
            else:
                sky_dict[prev_day]['vis_avg'] = sum(vis_list)/len(vis_list)
                sky_dict[prev_day]['cover_avg'] += sum(cover_list)/len(cover_list)
                vis_list = []
                cover_list = []
                target_day = day_key
        
    # Convert the defaultdict to a list of dictionaries
    sky_dict = list(sky_dict.values())

    return sky_dict
    
def find_stargazing_dates(illum_threshold, vis_threshold, cover_threshold, home_lat, home_lon):
    moon = get_5_day_moon_forecast()
    new_moons = [index for index, value in enumerate(moon['illum']) if value >= illum_threshold]
    new_moon_dates = [value for index, value in enumerate(moon['date']) if index in new_moons]

    stargazing_dates = []

    if len(new_moons) > 0:
        sky = get_5_day_sky_forecast(home_lat, home_lon)
        for day in sky:
            if day['date'] in new_moon_dates:
                if day['vis_avg'] > vis_threshold and day['cover_avg'] < cover_threshold:
                    stargazing_dates.append(day['date'])
    
    return stargazing_dates

def handler(events, lambda_context):

    vis_threshold = 20
    cover_threshold = 5
    illum_threshold = 2
    dist_threshold = 360000

    forecast = find_stargazing_dates(illum_threshold, vis_threshold, cover_threshold, home_lat, home_lon)
    
    if len(forecast) > 0:
        message = f"""Upcoming Stargazing Dates!"""
        for i in range(len(forecast)):
            date = datetime.datetime.strptime(forecast[i], '%Y-%m-%d')
            message += f"""\n\t- {date.strftime("%B")} {date.day}, {date.year}"""
        send_notification(message)
    else:
        print('No upcoming stargazing dates!')

if __name__ == "__main__":
    handler("","")