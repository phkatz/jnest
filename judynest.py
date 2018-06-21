"""
This program is for managing a Nest thermostat. The primary function is
to switch between heat mode and cool mode. While the Nest has a native
heat-cool mode, the interface for adjusting the temperature is too
complicated for my Alzheimer's inflicted mother, as it requires
extra steps to select either the heat set point or the cool set point,
and adjusting one can affect the other.

Instead, this program uses only heat and cool modes so that Mom can
adjust the temperature to make herself comfortable. If the program
detects that the house temperature is getting warmer than the heat
set point warrants, it will switch to cool. Similarly, if the the
house temperature is getting colder than the cool set point warrants,
it will switch to heat.

This program uses the requests library for interacting with the Nest
RESTful API. Note that Nest API accesses cause an HTTP redirect. The 
requests library will not replicate the authentication information on 
the redirect, causing API accesses to fail. A workaround is described 
here: https://github.com/requests/requests/issues/2949
and this is what I've implemented.
"""

import sys
import time
import pprint
import pickle
import requests
import json

POLL_TIME = 5
COOL_TARGET = 77
HEAT_TARGET = 75

# Simulator
CLIENT_ID = r'3c28905c-e2db-4656-872d-c301d5719860'
CLIENT_SECRET = r'VeiCBX7lnXqP6JoB52TajPWvA'

AUTH_URL = 'https://api.home.nest.com/oauth2/access_token'
API_URL = "https://developer-api.nest.com"

CFG_FILE = "judynest.cfg"
TKN_FILE = "judynest.tkn"

read_redirect_url = None
write_redirect_url = None

# TODO: Make sure all HTTP requests have a timeout


def get_access_token():

    if (len(sys.argv) < 2):
        # No pin specified on command line, so see if we already
        # have a token file.
        try:
            tknf = open(TKN_FILE, 'rb')
        except OSError:
            print("*** ERROR: cannot open ", TKN_FILE,
                  " to read access token!")
            exit()
        else:
            try:
                token = pickle.load(tknf)
            except pickle.PickleError:
                print("*** ERROR: cannot read token from ", TKN_FILE)
                exit()
            else:
                tknf.close()
    else:
        # Pin was specified, so get a new token
        pin = sys.argv[1]

        payload = "client_id=" + CLIENT_ID \
                  + "&client_secret=" + CLIENT_SECRET \
                  + "&grant_type=authorization_code" \
                  + "&code=" + pin

        headers = {
            'Content-Type': "application/x-www-form-urlencoded"
        }

        response = requests.request("POST", AUTH_URL, 
                                    data=payload, headers=headers)
        resp_data = json.loads(response.text)

        if response.status_code != 200:
            print("*** ERROR!!! ***")
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(resp_data)
            exit()

        token = resp_data['access_token']
        # Save the token to file so we can use it next time
        try:
            tknf = open(TKN_FILE, 'wb')
        except OSError:
            print("*** ERROR: cannot open ", TKN_FILE,
                  " to save access token!")
            exit()
        else:
            pickle.dump(token, tknf)
            tknf.close()

    return token



def read_device(token):
    global read_redirect_url

    headers = {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    }

    if (read_redirect_url is None):
        url = API_URL
    else:
        url = read_redirect_url

    response = requests.get(url, headers=headers, allow_redirects=False)
    if response.status_code == 307:
        read_redirect_url = response.headers['Location']
        print("In read_device redirecting to ", read_redirect_url)
        response = requests.get(read_redirect_url,
                                headers=headers, allow_redirects=False)

    if response.status_code != 200:
        print("*** ERROR!!! ***")
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(resp_data)
        exit()

    resp_data = json.loads(response.text)
    devices = resp_data['devices']
    thermos = devices['thermostats']
    # We don't know the name of the thermostat, but there should be
    # only 1, so just get the first
    key = list(thermos.keys())[0]
    nest = thermos[key]

    #pp = pprint.PrettyPrinter(indent=4)
    #pp.pprint(nest)
    return nest


def set_device(token, device_id, parm, value):
    global write_redirect_url

    headers = {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    }

    if (type(value) is str):
        payload = "{\"" + parm + "\": \"" + value + "\"}"
    else:
        payload = "{\"" + parm + "\": " + str(value) + "}"


    if (write_redirect_url is None):
        url = API_URL + "/devices/thermostats/" + device_id
    else:
        url = write_redirect_url

    response = requests.put(url, 
                            headers=headers, data=payload, 
                            allow_redirects=False)
    if response.status_code == 307:
        write_redirect_url = response.headers['Location']
        print("In set_device redirecting to ", write_redirect_url)
        response = requests.put(write_redirect_url, 
                                headers=headers, data=payload, 
                                allow_redirects=False)
    if response.status_code != 200:
        print("*** ERROR!!! ***")
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(resp_data)
        exit()

################################
# main
################################

token = get_access_token()

# Loop forever, monitoring the thermostat and making adjustments
# as needed.
while (True):
    stat = read_device(token)
    ambient = stat['ambient_temperature_f']
    mode = stat['hvac_mode']
    target = stat['target_temperature_f']
    device_id = stat['device_id']

    if (mode == 'heat'):
        # If H and Tm > Ts + 2 and Tm > 77, turn on C and set Ts = 77
        if (ambient > target+2 and ambient > COOL_TARGET):
            set_device(token, device_id, 'hvac_mode', 'cool')
            set_device(token, device_id, 'target_temperature_f', 77)
    elif (mode == 'cool'):
        # If C and Tm < Ts - 2 and Tm < 75, turn on H and set Ts = 75
        if (ambient < target-2 and ambient < HEAT_TARGET):
            set_device(token, device_id, 'hvac_mode', 'heat')
            set_device(token, device_id, 'target_temperature_f', HEAT_TARGET)
    elif (mode == 'heat-cool' or mode == 'eco'):
        if (ambient <= COOL_TARGET):
            set_device(token, device_id, 'hvac_mode', 'heat')
            set_device(token, device_id, 'target_temperature_f', HEAT_TARGET)
        else:
            set_device(token, device_id, 'hvac_mode', 'cool')
            set_device(token, device_id, 'target_temperature_f', COOL_TARGET)

    print("Target={}, ambient={}, mode={}".format(target, ambient, mode))
    time.sleep(POLL_TIME)

