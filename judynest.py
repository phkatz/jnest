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
import requests
import json


# TODO: These should be read from a file
# The following are for the JudyTest OAUTH client:
redirect_uri = None
API_URL = "https://developer-api.nest.com"

# TODO: Make sure all HTTP requests have a timeout

def req_access_token(pin):
    auth_url = 'https://api.home.nest.com/oauth2/access_token'
    client_id = r'3c28905c-e2db-4656-872d-c301d5719860'
    client_secret = r'VeiCBX7lnXqP6JoB52TajPWvA'

    payload = "client_id=" + client_id \
              + "&client_secret=" + client_secret \
              + "&grant_type=authorization_code" \
              + "&code=" + pin

    headers = {
        'Content-Type': "application/x-www-form-urlencoded"
    }

    response = requests.request("POST", auth_url, 
                                data=payload, headers=headers)
    resp_data = json.loads(response.text)

    if response.status_code != 200:
        print("*** ERROR!!! ***")
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(resp_data)
        exit()

    return resp_data['access_token']



def read_device(token):
    headers = {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    }

    response = requests.get(API_URL, headers=headers, allow_redirects=False)
    if response.status_code == 307:
        response = requests.get(response.headers['Location'], 
                                headers=headers, allow_redirects=False)

    print(response.text)


################################
# main
################################
if (len(sys.argv) < 2):
    print("Specify the pin")
    exit()

token = req_access_token(sys.argv[1])
read_device(token)

