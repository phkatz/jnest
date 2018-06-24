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

TODO:
    1. timeouts on all HTTP requests.

    2. Handle cached redirect URL going bad.

    X. Generate log file of decision activity

    -. SMS or email notification
       (Use IOS app to SSH into VM and view log files or kill
       app)

    5. Move CLIENT_ID and CLIENT_SECRET to cfg file

    6. Change token from pickle to json, maybe in same
       config file as CLIENT_ID and CLIENT_SECRET?

    7. Notifications via SMS (twilio.com)

    8. State machine architecture for handling things like
       thermostat being set to Off mode

    9. Handle case where temp is above AC range, but mom has set
       to heat so it won't be cold in the morning.

    xx. Use existence of a file to trigger enable/disable of
        program operation so can ssh from phone and control
        whether program runs or not.

"""

import os
import sys
import time
import logging
import pprint
import pickle
import requests
import json
import argparse

from logging.handlers import RotatingFileHandler

LOGFILE = 'jnest.log'
LOGFILESIZE = 500000

MIN_POLL_TIME = 65
COOL_TARGET = 77
HEAT_TARGET = 75

# Simulator
CLIENT_ID = r'3c28905c-e2db-4656-872d-c301d5719860'
CLIENT_SECRET = r'VeiCBX7lnXqP6JoB52TajPWvA'

AUTH_URL = 'https://api.home.nest.com/oauth2/access_token'
API_URL = "https://developer-api.nest.com"

CFG_FILE = "judynest.cfg"
TKN_FILE = "judynest.tkn"
ENABLE_FILE = "gojnest"

FAKE_KEY = "c.fakekey123"
fake_stats = {
        'ambient_temperature_f': 70,
        'hvac_mode': 'heat',
        'target_temperature_f': 70,
        'device_id': 'fake_device_123',
}

read_redirect_url = None
write_redirect_url = None


def get_access_token():

    if (args.pin is None):
        # No pin specified on command line, so see if we already
        # have a token file.
        try:
            tknf = open(TKN_FILE, 'rb')
        except OSError:
            log.error("Cannot open %s to read access token" % TKN_FILE)
            log.critical("Terminating program.")
            exit()
        else:
            try:
                token = pickle.load(tknf)
            except pickle.PickleError:
                log.error("Cannot read token from %s" % TKN_FILE)
                log.critical("Terminating program.")
                exit()
            else:
                tknf.close()
    else:
        # Pin was specified, so get a new token
        payload = "client_id=" + CLIENT_ID \
                  + "&client_secret=" + CLIENT_SECRET \
                  + "&grant_type=authorization_code" \
                  + "&code=" + args.pin

        headers = {
            'Content-Type': "application/x-www-form-urlencoded"
        }

        response = requests.request("POST", AUTH_URL, 
                                    data=payload, headers=headers)
        resp_data = json.loads(response.text)

        if response.status_code != 200:
            pp = pprint.PrettyPrinter(indent=4)
            rsp = pp.pformat(resp_data)
            log.error("Post request response code: %d" % response.status_code)
            log.error("Post response message: %s" % rsp)
            log.critical("Terminating program.")
            exit()

        token = resp_data['access_token']
        # Save the token to file so we can use it next time
        try:
            tknf = open(TKN_FILE, 'wb')
        except OSError:
            log.error("Cannot open %s to save access token" % TKN_FILE)
            log.critical("Terminating program.")
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

    if (args.sim):
        log.debug("Returning fake stats for sim mode.")
        return fake_stats
        
    response = requests.get(url, headers=headers, allow_redirects=False)
    if response.status_code == 307:
        read_redirect_url = response.headers['Location']
        log.debug("In read_device redirecting to %s" % read_redirect_url)
        response = requests.get(read_redirect_url,
                                headers=headers, allow_redirects=False)

    resp_data = json.loads(response.text)
    if response.status_code != 200:
        pp = pprint.PrettyPrinter(indent=4)
        rsp = pp.pformat(resp_data)
        log.error("Get request response code: %d" % response.status_code)
        log.error("Get response message: %s" % rsp)
        log.critical("Terminating program.")
        exit()

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

    if (args.sim):
        log.debug("Faking Put to set parameter.")
        fake_stats[parm] = value
        return

    response = requests.put(url, 
                            headers=headers, data=payload, 
                            allow_redirects=False)
    if response.status_code == 307:
        write_redirect_url = response.headers['Location']
        log.debug("In set_device redirecting to %s" % write_redirect_url)
        response = requests.put(write_redirect_url, 
                                headers=headers, data=payload, 
                                allow_redirects=False)
    resp_data = json.loads(response.text)
    if response.status_code != 200:
        pp = pprint.PrettyPrinter(indent=4)
        rsp = pp.pformat(resp_data)
        log.error("Put request response code: %d" % response.status_code)
        log.error("Put response message: %s" % rsp)
        log.critical("Terminating program.")
        exit()

################################
# main
################################

# Parse command line options
parser = argparse.ArgumentParser(description='Nest thermostat monitoring and control.')
parser.add_argument('-p', '--pin',
                    help='Speicfy authentication PIN'
)
parser.add_argument('-d', '--debug',
                    help="Log debug messages",
                    action="store_const", dest="loglevel", const=logging.DEBUG,
                    default=logging.INFO,
)
parser.add_argument('-s', '--sim',
                    help="Fake calls to Nest API (to prevent blocking)",
                    action="store_true"
)
parser.add_argument('-r', '--rate',
                    help="Poll rate in seconds (forces --sim if <%d)" % MIN_POLL_TIME,
                    default=MIN_POLL_TIME,
                    type=int,
)
parser.add_argument('-q', '--quiet',
                    help="Suppress info log messages",
                    action="store_const", dest="loglevel", const=logging.WARNING,
)
args = parser.parse_args()

# Set up logger
log = logging.getLogger('')
log.setLevel(logging.DEBUG)
format = logging.Formatter("%(asctime)s (%(name)s) [%(levelname)s]: %(message)s")

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(format)
ch.setLevel(args.loglevel)
log.addHandler(ch)

fh = RotatingFileHandler(LOGFILE, maxBytes=LOGFILESIZE, backupCount=5)
fh.setFormatter(format)
fh.setLevel(logging.DEBUG)
log.addHandler(fh)

# If using a short poll rate, force --sim to prevent blocking
if (args.rate < MIN_POLL_TIME):
    args.sim = True

token = get_access_token()

lastmode = 'off'
lasttarg = 0
lastamb = 0

# Create the enable file when we first start up
lastenab = True
open(ENABLE_FILE, 'w').close()

# Loop forever, monitoring the thermostat and making adjustments
# as needed.
while (True):
    time.sleep(args.rate)
    
    # Idle if the enable file is not present
    if not os.path.isfile(ENABLE_FILE):
        if (lastenab):
            lastenab = False
            log.info("Idling - file '%s' is missing." % ENABLE_FILE)
        continue;
    else:
        if (not lastenab):
            lastenab = True
            log.info("Un-idling - file '%s' is present." % ENABLE_FILE)

    stat = read_device(token)
    ambient = stat['ambient_temperature_f']
    mode = stat['hvac_mode']
    target = stat['target_temperature_f']
    device_id = stat['device_id']

    if (mode == 'heat' and mode == lastmode):
        # If H and Tm > Ts + 2 and Tm > 77, turn on C and set Ts = 77
        if (ambient > target+2 and ambient > COOL_TARGET):
            set_device(token, device_id, 'hvac_mode', 'cool')
            set_device(token, device_id, 'target_temperature_f', 77)
    elif (mode == 'cool' and mode == lastmode):
        # If C and Tm < Ts - 2 and Tm < 75, turn on H and set Ts = 75
        if (ambient < target-2 and ambient < HEAT_TARGET):
            set_device(token, device_id, 'hvac_mode', 'heat')
            set_device(token, device_id, 'target_temperature_f', HEAT_TARGET)
    elif ((mode == 'heat-cool' or mode == 'eco') and mode == lastmode):
        if (ambient <= COOL_TARGET):
            set_device(token, device_id, 'hvac_mode', 'heat')
            set_device(token, device_id, 'target_temperature_f', HEAT_TARGET)
        else:
            set_device(token, device_id, 'hvac_mode', 'cool')
            set_device(token, device_id, 'target_temperature_f', COOL_TARGET)

    if (mode != lastmode or target != lasttarg or ambient != lastamb):
        log.info("Target={}, ambient={}, mode={}".format(target, ambient, mode))

    lastmode = mode
    lasttarg = target
    lastamb = ambient

