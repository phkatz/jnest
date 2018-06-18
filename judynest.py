import sys
import requests
import json
import time
import pprint

# TODO: These should be read from a file
# The following are for the JudyTest OAUTH client:
redirect_uri = None
apiUrl = "https://developer-api.nest.com"

# TODO: Make sure all HTTP requests have a timeout

def reqAccessToken(pin):
    authUrl = 'https://api.home.nest.com/oauth2/access_token'
    client_id = r'3c28905c-e2db-4656-872d-c301d5719860'
    client_secret = r'VeiCBX7lnXqP6JoB52TajPWvA'

    payload = "client_id=" + client_id + "&client_secret=" + client_secret + "&grant_type=authorization_code&code=" + pin

    headers = {
        'Content-Type': "application/x-www-form-urlencoded"
        }

    response = requests.request("POST", authUrl, data=payload, headers=headers)
    respData = json.loads(response.text)

    if response.status_code != 200:
        print("*** ERROR!!! ***")
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(respData)
        exit()

    return respData['access_token']



def readDevice(token):
    headers = {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
              }

    response = requests.get(apiUrl, headers=headers, allow_redirects=False)
    if response.status_code == 307:
        response = requests.get(response.headers['Location'], headers=headers, allow_redirects=False)

    print(response.text)


################################
# main
################################
if (len(sys.argv) < 2):
    print("Specify the pin")
    exit()

token = reqAccessToken(sys.argv[1])
readDevice(token)

