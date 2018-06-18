import sys
import requests
import json
import time

# TODO: These should be read from a file
# The following are for the JudyTest OAUTH client:
redirect_uri = None
apiUrl = "https://developer-api.nest.com"

# TODO: Make sure all HTTP requests have a timeout

def reqAccessToken1(pin):
    '''Get an access token and return the token value.'''

    auth_endpoint = 'https://api.home.nest.com/oauth2/access_token'
    client_id = r'3c28905c-e2db-4656-872d-c301d5719860'
    client_secret = r'VeiCBX7lnXqP6JoB52TajPWvA'

    bodyContent =   {
                        "client_id" : client_id,
                        "client_secret" : client_secret,
                        "grant_type" : "authorization_code",
                        "code" : pin
                    }

    resp = requests.post(auth_endpoint, data=bodyContent)

    if (resp.status_code != 200):
        print("*** ERROR: response = {}".format(resp.status_code))
        exit()

    data = json.loads(resp.text)
    token = data["access_token"]
    print("*** token='{}'".format(token))
    return token


def readDevice1(token):
    '''Read the device parameters.'''

    payload = "client_id=3c28905c-e2db-4656-872d-c301d5719860&client_secret=VeiCBX7lnXqP6JoB52TajPWvA&grant_type=authorization_code&code=EXTSYS9S"
    headers = {
        'Content-Type': "application/json",
        'Authorization': "Bearer " + token,
        'Cache-Control': "no-cache",
        }

    print("*** Authorization='{}'".format(headers['Authorization']))
    response = requests.request("GET", apiUrl, data=payload, headers=headers)

    print(response.text)


def reqAccessToken(pin):
    url = "https://api.home.nest.com/oauth2/access_token"

    payload = "client_id=3c28905c-e2db-4656-872d-c301d5719860&client_secret=VeiCBX7lnXqP6JoB52TajPWvA&grant_type=authorization_code&code=" + pin
    headers = {
        'Content-Type': "application/x-www-form-urlencoded"
        }
        #'Cache-Control': "no-cache"
        #'Postman-Token': "d4ed99be-f9a0-43a7-8bbe-c3505613e6eb"

    response = requests.request("POST", url, data=payload, headers=headers)

    # hack print(response.text)
    respData = json.loads(response.text)
    return respData['access_token']

def readDevice2(pin, token):
    url = "https://developer-api.nest.com"

    payload = "client_id=3c28905c-e2db-4656-872d-c301d5719860&client_secret=VeiCBX7lnXqP6JoB52TajPWvA&grant_type=authorization_code&code=" + pin
    headers = {
        'Content-Type': "application/json",
        'Authorization': "Bearer " + token
        }
        #'Cache-Control': "no-cache"
        #'Postman-Token': "70df03eb-183d-48dd-8d56-d4bd3ff1257d"

    # hack print("*** Authorization='{}'".format(headers['Authorization']))
    # hack print("*** payload='{}'".format(payload))
    #response = requests.request("GET", url, data=payload, headers=headers)
    response = requests.request("GET", url, headers=headers)

    print(response.text)


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

