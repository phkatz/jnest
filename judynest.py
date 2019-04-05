"""
This program is for managing a Nest thermostat. The primary function is
to switch between heat mode and cool mode. While the Nest has a native
heat-cool mode, the interface for adjusting the temperature is too
complicated for my Alzheimer's afflicted mother, as it requires
extra steps to select either the heat set point or the cool set point,
and adjusting one can affect the other.

Instead, this program uses only heat and cool modes so that Mom can
adjust the temperature to make herself comfortable. If the program
detects that the house temperature is getting warmer than the heat
set point warrants, it will switch to cool. Similarly, if the the
house temperature is getting colder than the cool set point warrants,
it will switch to heat. However, the program also looks at the outdoor
temperature (which is retrieved per city code from openweathermap.org)
and will only switch to heat of the outdoor temperature is below a
configured threhold, or to cool if the outdoor temperature is above a
configured threshold. (It is necessary to consider the outdoor temp
to prevent switching to the wrong mode in response to Mom setting the
target temperature to unreasonable extremes, which she does from time
to time.) If for some reason we can't get the outdoor temperature,
all mode changing decisions will be based only on the indoor ambient
temperature and current target temp as set by Mom.

Configuration must appear in JSON file, judynest.cfg and be of the
following format (all temperatures in Fahrenheit):

{
    "CLIENT_ID" : <Nest thermostat device ID>,
    "CLIENT_SECRET" : <Access code>,
    "COOL_TARGET" : <Target temp to set for cool mode>,
    "HEAT_TARGET" : <Target temp to set for heat mode>,
    "MAX_ALLOWED_TEMP" : <Ambient temp at which to trigger cooling>,
    "MIN_ALLOWED_TEMP" : <Ambient temp at which to trigger heating>,
    "OUTDOOR_COOL_THRESH" : <Min outdoor temp allowable for cooling>,
    "OUTDOOR_HEAT_THRESH" : <Max outdoor temp allowable for heating>,
    "OWM" : {
        "KEY" : <openweathermap.org user access key>,
        "CITY_ID" : <openweathermap.org city code> 
    }
}


This program uses the requests library for interacting with the Nest
RESTful API. Note that Nest API accesses cause an HTTP redirect. The 
requests library will not replicate the authentication information on 
the redirect, causing API accesses to fail. A workaround is described 
here: https://github.com/requests/requests/issues/2949
and this is what I've implemented.

HISTORY:
    1.0 06/28/2018  Original release

    1.1 02/24/2019  During cold weather, Mom was turning the heat up 
                    to 80, which exceeded the allowed max, causing the 
                    program to switch from heat to cool to the cool 
                    target. This cooled the house, which is not what 
                    she wanted and she would go to battle, setting the 
                    thermostat higher and higher. To address this, we now
                    incorporate looking at the outside temperature
                    to determine if the heat or cool should be on.
                    The Nest API does not provide outside temperatures
                    (even though it is displayed on the interface),
                    so we use OpenWeatherMap.org to get the data.

    1.2 02/25/2019  Add support for --outdoor option to test using a
                    fake outdoor temperature.

    1.3 04/04/2019  Don't terminate on error from OWM.

TODO:
    7. Notifications via SMS (twilio.com)

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

Version = "1.3 (4/4/2019)"

LOGFILE = 'jnest.log'
LOGFILESIZE = 500000

POLL_TIME = 65
MIN_POLL_TIME = 5

AUTH_URL = 'https://api.home.nest.com/oauth2/access_token'
API_URL = "https://developer-api.nest.com"
HTTP_TIMEOUT = 30

# OpenWeatherMap
OWM_URL = 'http://api.openweathermap.org/data/2.5/weather'
OWM_POLL_TIME = 30 # seconds

# File names
CFG_FILE = "judynest.cfg"
TKN_FILE = "judynest.tkn"
ENABLE_FILE = "gojnest"
OD_FILE = "outdoor.json"

# Fake out stuff for fake mode
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
        payload = "client_id=" + cfg['CLIENT_ID'] \
                  + "&client_secret=" + cfg['CLIENT_SECRET'] \
                  + "&grant_type=authorization_code" \
                  + "&code=" + args.pin

        headers = {
            'Content-Type': "application/x-www-form-urlencoded"
        }


        try:
            response = requests.request("POST", 
                                        AUTH_URL, 
                                        data=payload, 
                                        headers=headers,
                                        timeout=HTTP_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as err:
            log.error("Post request timed out on url '%s'" % AUTH_URL)
            log.error("Post timeout error: %s" % err)
            log.critical("Terminating program.")
            exit()

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

    if (args.fake):
        log.debug("Returning fake stats for fake mode.")
        return fake_stats
        
    # While loop is in case we need to retry due to 
    # cached redirect URL being stale.
    while (True):
        try:
            response = requests.get(url, 
                                    headers=headers, 
                                    allow_redirects=False,
                                    timeout=HTTP_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as err:
            log.error("Get request timed out on url '%s'" % url)
            log.error("Get time out error: %s" % err)
            return None
        else:
            if response.status_code == 307:
                read_redirect_url = response.headers['Location']
                log.debug("In read_device redirecting to %s" % read_redirect_url)

                try:
                    response = requests.get(read_redirect_url,
                                            headers=headers, 
                                            allow_redirects=False,
                                            timeout=HTTP_TIMEOUT)
                except (requests.Timeout, requests.ConnectionError) as err:
                    log.error("Get request timed out on redirect url '%s'" % read_redirect_url)
                    log.error("Get timeout error: %s" % err)
                    return None

            resp_data = json.loads(response.text)
            if response.status_code != 200:
                if (read_redirect_url is None or url != read_redirect_url):
                    # We didn't get a redirect, or we did and it didn't work
                    pp = pprint.PrettyPrinter(indent=4)
                    rsp = pp.pformat(resp_data)
                    log.error("Get request response code: %d" % response.status_code)
                    log.error("Get response message: %s" % rsp)
                    log.critical("Terminating program.")
                    exit()
                else:
                    # We used the cached redirect and it didn't work, so
                    # try again with the official URL
                    log.info("Cached redirect URL didn't work - trying '%s'" % API_URL)
                    url = API_URL
            else:
                # Success - no need to loop
                break;

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

    parm_url = API_URL + "/devices/thermostats/" + device_id

    if (write_redirect_url is None):
        url = parm_url
    else:
        url = write_redirect_url

    if (args.fake):
        log.debug("Faking Put to set parameter.")
        fake_stats[parm] = value
        return True

    # While loop is in case we need to retry due to 
    # cached redirect URL being stale.
    while (True):
        try:
            response = requests.put(url, 
                                    headers=headers, 
                                    data=payload, 
                                    allow_redirects=False,
                                    timeout=HTTP_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as err:
            log.error("Put request timed out on url '%s'" % url)
            log.error("Put timeout error: %s" % err)
            return False
        else:
            if response.status_code == 307:
                write_redirect_url = response.headers['Location']
                log.debug("In set_device redirecting to %s" % write_redirect_url)

                try:
                    response = requests.put(write_redirect_url, 
                                            headers=headers, 
                                            data=payload, 
                                            allow_redirects=False,
                                            timeout=HTTP_TIMEOUT)
                except (requests.Timeout, requests.ConnectionError) as err:
                    log.error("Put request timed out on redirect url '%s'" % read_redirect_url)
                    log.error("Put timeout error: %s" % err)
                    return False
                
            resp_data = json.loads(response.text)
            if response.status_code != 200:
                if (write_redirect_url is None or url != write_redirect_url):
                    # We didn't get a redirect, or we did and it didn't work
                    pp = pprint.PrettyPrinter(indent=4)
                    rsp = pp.pformat(resp_data)
                    log.error("Put request response code: %d" % response.status_code)
                    log.error("Put response message: %s" % rsp)
                    log.critical("Terminating program.")
                    exit()
                else:
                    # We used the cached redirect and it didn't work, so
                    # try again with the official URL
                    log.info("Cached redirect URL didn't work - trying '%s'" % parm_url)
                    url = parm_url
            else:
                # Success - no need to loop
                break;

    return True


#############################################################
# If the --outdoor option is specified, instead of getting
# the outdoor temperature from OWM, just read it from a 
# JSON file as a way of testing the logic that depends on
# the outdoor temperature. The JSON file is of the format:
#
#   {
#       "temp" : 68
#   }
#
# where here we show 68 degrees F as an example, but any temp
# can be specified.
#############################################################
def get_outdoor_temp():

    if (args.outdoor):
        # Do fake temperature reading from file
        try:
            odfile = open(OD_FILE, 'r')
        except OSError:
            log.error("Cannot open %s to read fake outdoor temp." % OD_FILE)
            log.critical("Terminating program.")
            exit()
        else:
            try:
                od = json.load(odfile)
            except json.decoder.JSONDecodeError as err:
                log.error("Cannot parse fake outdoor temp from file '%s'" % OD_FILE)
                log.error("Parsing error: %s" % err)
                log.critical("Terminating program.")
                exit()
        return od['temp']

    # Do real temperature reading
    parms = {}
    parms['units'] = 'Imperial'
    parms['id'] = cfg['OWM']['CITY_ID']
    parms['appid'] = cfg['OWM']['KEY']

    try:
        response = requests.get(OWM_URL, 
                                params = parms,
                                allow_redirects=False,
                                timeout=HTTP_TIMEOUT)
    except (requests.Timeout, requests.ConnectionError) as err:
        log.error("Get request timed out on url '%s'" % OWM_URL)
        log.error("Get time out error: %s" % err)
        return None
    else:
        resp_data = json.loads(response.text)
        if response.status_code != 200:
            pp = pprint.PrettyPrinter(indent=4)
            rsp = pp.pformat(resp_data)
            log.error("Get request response code: %d" % response.status_code)
            log.error("Get response message: %s" % rsp)
            return None
        else:
            # Success
            return resp_data['main']['temp']


def set_heat(token, device_id, mode, cfg):
    if (set_device(token, device_id, 'hvac_mode', 'heat')):
        set_device(token, device_id, 'target_temperature_f', cfg['HEAT_TARGET'])
        log.info("Switch from {} to heat to {}".format(mode, cfg['HEAT_TARGET']))


def set_cool(token, device_id, mode, cfg):
    if (set_device(token, device_id, 'hvac_mode', 'cool')):
        set_device(token, device_id, 'target_temperature_f', cfg['COOL_TARGET'])
        log.info("Switch from {} to cool to {}".format(mode, cfg['COOL_TARGET']))



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
parser.add_argument('-f', '--fake',
                    help="Fake calls to Nest API (to prevent blocking)",
                    action="store_true"
)
parser.add_argument('-o', '--outdoor',
                    help="Get outdoor temp from file outdoor.json",
                    action="store_true"
)
parser.add_argument('-r', '--rate',
                    help="Poll rate in seconds (forces --fake if <%d)" % MIN_POLL_TIME,
                    default=POLL_TIME,
                    type=int,
)
parser.add_argument('-q', '--quiet',
                    help="Suppress info log messages",
                    action="store_const", dest="loglevel", const=logging.WARNING,
)
args = parser.parse_args()

# If using a short poll rate, force --fake to prevent blocking
if (args.rate < MIN_POLL_TIME):
    args.fake = True

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

log.info("{} Version {}".format(sys.argv[0], Version))

# Get configuration  parameters
try:
    cfgf = open(CFG_FILE, 'r')
except OSError:
    log.error("Cannot open %s to read configuration." % CFG_FILE)
    log.critical("Terminating program.")
    exit()
else:
    try:
        cfg = json.load(cfgf)
    except json.decoder.JSONDecodeError as err:
        log.error("Cannot parse configuration from file '%s'" % CFG_FILE)
        log.error("Parsing error: %s" % err)
        log.critical("Terminating program.")
        exit()

token = get_access_token()

lastmode = 'off'
lasttarg = 0
lastamb = 0

# Create the enable file when we first start up
lastenab = True
open(ENABLE_FILE, 'w').close()

init = True
outdoorCheckTime = 0
outdoor = 0

# Loop forever, monitoring the thermostat and making adjustments
# as needed.
while (True):
    if (init):
        init = False
    else:
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
    if (stat is None):
        continue

    ambient = stat['ambient_temperature_f']
    mode = stat['hvac_mode']
    target = stat['target_temperature_f']
    device_id = stat['device_id']

    nowTime = time.time()
    if (nowTime - outdoorCheckTime > OWM_POLL_TIME):
        outdoor = get_outdoor_temp()
        outdoorCheckTime = nowTime

    if (mode != lastmode or target != lasttarg or ambient != lastamb):
        log.info("Target={}, ambient={}, outdoor={}, mode={}"
                .format(target, ambient, outdoor, mode))

    if (mode == 'heat' and mode == lastmode):
        if (ambient > cfg['MAX_ALLOWED_TEMP'] or 
                (ambient > target+2 and ambient > cfg['COOL_TARGET'])):
            if (outdoor == None or outdoor >= cfg['OUTDOOR_COOL_THRESH']):
                set_cool(token, device_id, mode, cfg)
    elif (mode == 'cool' and mode == lastmode):
        if (ambient < cfg['MIN_ALLOWED_TEMP'] or 
                (ambient < target-2 and ambient < cfg['HEAT_TARGET'])):
            if (outdoor == None or outdoor <= cfg['OUTDOOR_HEAT_THRESH']):
                set_heat(token, device_id, mode, cfg)
    elif ((mode == 'heat-cool' or mode == 'eco') and mode == lastmode):
        if (outdoor != None):
            if (outdoor <= cfg['OUTDOOR_HEAT_THRESH'] and 
                    ambient <= cfg['COOL_TARGET']):
                set_heat(token, device_id, mode, cfg)
            else:
                set_cool(token, device_id, mode, cfg)
        else:
            if (ambient <= cfg['COOL_TARGET']):
                set_heat(token, device_id, mode, cfg)
            else:
                set_cool(token, device_id, mode, cfg)

    lastmode = mode
    lasttarg = target
    lastamb = ambient

