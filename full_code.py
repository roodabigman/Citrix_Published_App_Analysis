import requests
from requests.models import Response
import csv
from datetime import datetime, timedelta
from tqdm.auto import tqdm
import numpy
import time

# program opening text, details, version, etc
print("#############################################################################################################")
print("Welcome to the Monitor API data retriever tool.  This program takes a customer ID and API client as inputs ")
print("A Bearer Token is generated from the API client, and used to query the Monitor DB associated with your Cloud")
print("site.  The data collected is all Sessions over a given time period, with the user, device platform, agent")
print("version, application details / desktop details, and start and end time.  The data is formatted into a CSV")
print("for easy analysis using Excel or other data manipulation tools. These API queries are READ-ONLY, so you cannot")
print("make any changes / interrupt a production environment using this program. ")
print("Version 0.7, 9/29/22")
print("Written by BVB")
print("#############################################################################################################")

# collect customer name from users
customer_name = input("please provide Customer ID: ")
print("\n")


# collect Client ID from Client token generated on Citrix Cloud
client_id = input("please enter API Client Id: ")
print("\n")


# collect Client Secret of Client token generated on Citrix CLoud
client_secret = input("please enter API Client Secret: ")
print("\n")
print("Using these credentials to retrieve a Bearer Token from the Citrix Trust Center...")


# function to retrieve bearer token
def get_bearer_token(clientid, clientsecret):
    content_type = 'application/json'

    data = {"clientId": clientid, "clientSecret": clientsecret}

    headers = {'content-type': content_type}

    trusturl: str = "https://trust.citrixworkspacesapi.net/root/tokens/clients"

    response: Response = requests.post(trusturl, json=data, headers=headers)
    if 200 <= response.status_code <= 299:
        print('API token Accepted, downloading bearer token')
        print("\n")
    else:
        print("*********FAILED TO RETRIEVE BEARER TOKEN************")
        print("Response code: {}".format(response.status_code))
        print("please check your customer id, client id, and client secret, and try again")
        input("Press Enter to Exit")
        exit()

    return response


# add line brek
print("\n")

# send parameters to function to retrieve token
token: Response = get_bearer_token(client_id, client_secret)

# Read token from auth response and prepend necessary syntax
bearer_token = 'CwsAuth Bearer=%s' % token.json()["token"]

# store bearer token expiration - needed to check validity for large queries that take more than 60 minutes
bearer_expiration = datetime.now() + (timedelta(seconds=token.json()['expiresIn'] - 120))


# define function to query API and return payload, includes 4 retries per call in event of a status code
# outside 200-299, with a 2-second pause between each request.  purpose here is the Citrix API can return
# a 429 status frequently (too many requests) if the API is being used elsewhere, resulting in simultaneous
# requests to the same API.  A few spaced retries usually relieves this issue
def query_api(queryurl, bearertoken, customername):
    query_headers = {'Authorization': bearertoken, 'Citrix-CustomerId': customername}
    payload = {}
    retries = 4
    while retries > 0:
        response: Response = requests.get(queryurl, headers=query_headers, data=payload)
        if not 200 <= response.status_code <= 299:
            print("API Query failed with error:")
            print("Response code: {}".format(response.status_code))
            time.sleep(2)
            retries -= 1
            continue
        return response
    print("ERROR: Monitor API did not return data with 4 retries, check status codes returned")
    return


# get instance ID from Orchestration API
instance_query_url: str = f"https://api-us.cloud.com/cvad/manage/me"
print("Attempting to retrieve Site Instance ID from API")
instance_json: Response = query_api(instance_query_url, bearer_token, customer_name).json()
instance_id = instance_json['Customers'][0]['Sites'][0]['Id']
print("Instance ID retrieved successfully, Instance ID is {}".format(instance_id))


# function to query orchestation API for application details - command line parameters
# includes same retry function as described in the query_api function above
def query_orch_api(queryurl, bearertoken, customername, instanceid):
    query_headers = {'Authorization': bearertoken, 'Citrix-CustomerId': customername, 'Citrix-InstanceId': instanceid}
    payload = {}
    retries = 4
    while retries > 0:
        response: Response = requests.get(queryurl, headers=query_headers, data=payload)
        if not 200 <= response.status_code <= 299:
            print("API Query failed with error:")
            print("Response code: {}".format(response.status_code))
            time.sleep(2)
            retries -= 1
            continue
        return response
    print("ERROR: Orchestration API did not return data with 4 retries, check status codes returned")
    return


# set up variables for looping the application detail collection
# in environments with more than 1000 applications, need to process the ContinuationToken to iterate
# through the paginated results until there is no continuation token provided in the API response
continuemarker_app = 1
continuation_token = ""
app_output = []
app_missing_cmd = 0
app_missing_id = 0

print("Collecting Published Application Details from Site...")
print("\n")

while continuemarker_app > 0:
    appdetails_url: str = f"https://api-us.cloud.com/cvad/manage/Applications?" \
                          f"fields=Id,InstalledAppProperties&limit=1000{continuation_token}"

    app_details: Response = query_orch_api(appdetails_url, bearer_token, customer_name, instance_id).json()

    for x in app_details['Items']:
        try:
            app_output.append([x['Id'],
                               x['InstalledAppProperties']['CommandLineArguments']])
        except TypeError:
            try:
                app_output.append([x['Id'], "None"])
                app_missing_cmd += 1
            except Exception:
                app_missing_id += 1
        except Exception:
            app_missing_id += 1

    if len(continuation_token) == 0:
        print("Number of Applications found = {}".format(app_details['TotalItems']))

    if app_details.__len__() > 2:
        continuation_token = "&ContinuationToken={}".format(app_details['ContinuationToken'])
    else:
        continuemarker_app = 0

    continue

print("number of applications for which app properties was blank = {}".format(app_missing_cmd))
print("number of applications for which the application ID was blank = {}".format(app_missing_id))
print("\n")

# convert the app details array to a numpy array to simplify the lookup of app id / command line parameters
# and append to the output of session details
app_details_np = numpy.array(app_output)


# define function to accept yes / no answers in all iterations
def questionyn():
    i = 0
    while i < 2:
        answer = input("Please respond:")
        if any(answer.lower() == f for f in ["yes", 'y', '1', 'ye']):
            # print("Yes")
            answer_hold = 1
            return answer_hold
        elif any(answer.lower() == f for f in ['no', 'n', '0']):
            # print("No")
            answer_hold = 0
            return answer_hold
        else:
            i += 1
            if i < 2:
                print('Please enter yes or no')
            else:
                print("Nothing done")
                answer_hold = 0
                return answer_hold


# some rows of data in the monitor DB have no entry for delivery group, which raises an exception in the data
# formatter as we need to index by delivery group to get to name - this function will return the name if the
# delivery group name is there, if not it will return none rather than raise an exception
def dg_exists(dg):
    if dg is None:
        return None
    else:
        return dg['Name']


# function to apply true / false to each row depending on if the EXE run matches any items in the list of browsers
# browaer list is defined with other variables in the block before the session odata queries
def appcheck(path):
    if path in browsers:
        return True
    else:
        return False


# function to account for numpy not finding a match between application table and app id given in the Odata output
def appdetails(appid):
    if numpy.argwhere(app_details_np == appid).shape[0] > 0:
        return app_details_np[numpy.argwhere(app_details_np == appid)[0][0]][1]
    else:
        return None


# calculate duration of app instances and overall sessions
# convert end date and start date from json data to time values, difference these time values, return result
def duration(end, start):
    end = datetime.strptime(end[:19], '%Y-%m-%dT%H:%M:%S')
    start = datetime.strptime(start[:19], '%Y-%m-%dT%H:%M:%S')
    s = (end - start).total_seconds()
    hours, remainder = divmod(s, 3600)
    minutes, seconds = divmod(remainder, 60)
    appduration = '{:02}:{:02}:{:02}'.format(int(hours), int(minutes), int(seconds))
    return appduration


# function to calculate run time based on decreasing speed due to throttling
def runtime(sessions):
    qtime = 0
    if 0 < sessions <= 100000:
        qtime = "{:.1f}".format((sessions/35)/60)
    if 100000 < sessions <= 200000:
        qtime = "{:.1f}".format((3000 + (sessions - 100000)/20)/60)
    if 200000 < sessions <= 300000:
        qtime = "{:.1f}".format((8000 + (sessions - 200000)/15)/60)
    if 300000 < sessions:
        qtime = "{:.1f}".format((15000 + (sessions - 300000)/13)/60)
    return qtime


# declare some variables
browsers = ['chrome.exe', 'firefox.exe', 'iexplore.exe', 'msedge.exe']
skipcount = 0
continuemarker = 1
output = []
bad_row_count = 0

# declare loop variables to control while loop behavior
startconfirmed = 0
endconfirmed = 0
startdate = ""
enddate = ""
odatacount = Response()

while startconfirmed == 0 or endconfirmed == 0:
    # loop start from here to allow start date to be re-entered if too long of range...
    while startconfirmed == 0:
        startdate = input("please enter start date of time period for data collection in format yyyy-mm-dd: ")
        print("\n")

        # warn if start date is more than 90 days ago due to data gooming
        if (datetime.today() - datetime.strptime(startdate, '%Y-%m-%d')).days > 90:
            print("warning: start date specified is more than 90 days ago.  The Monitor DB in Citrix Cloud only")
            print("retains session data for 90 days.  The query will succeed, but you will only see results from")
            print("the past 90 days")
            print("would you like to enter a different start date?")
            answer2 = questionyn()
            if answer2 == 1:
                continue
            else:
                print("ok, carrying on...")

        startconfirmed = 1
        continue

    # give user the option to specify an end date for data collection (ex - if you wanted to restrict data collection
    # to a specific month, you could enter 2022-08-01 for start date and 2022-09-01 for end date and get details for
    # all sessions in the month of August 2022 only
    print("would you line to specify an end date for data collection - please answer yes to enter end date,")
    print("or enter no to collect data from start date to current time (yes/no): ")
    enddate_answer = questionyn()
    enddate = ""

    while endconfirmed == 0:
        if enddate_answer == 1:
            endraw = input("please enter end date of time period for data collection in format yyyy-mm-dd: ")
            enddate = endraw
            if (datetime.strptime(endraw, '%Y-%m-%d') - datetime.strptime(startdate, '%Y-%m-%d')).days < 0:
                print("End date must be a later calendar date than start date, please pick again")
                continue
            else:
                endconfirmed = 1
        else:
            enddate = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            endconfirmed = 1

        continue

    # generate a query_url to perform the count
    query_count_url: str = f"https://api-us.cloud.com/monitorodata/Sessions?$filter=StartDate ge {startdate} "\
                           f"and EndDate le {enddate}&$select=ExitCode&$count=true"

    # send URL to API query function and capture json output
    odatacount: Response = query_api(query_count_url, bearer_token, customer_name).json()

    # quantify data to be retrieved and validate that user would like to proceed
    print("The date range requested will analyze data for {} sessions".format(odatacount['@odata.count']))
    print("estimated time to run based on quantity of data is {} minutes".format(runtime(odatacount['@odata.count'])))
    print("do you wish to prceed with data collection for this date range? (yes / no)")
    answer1 = questionyn()

    if answer1 == 1:
        print("Great, proceeding to data collection")
        print("\n")
    else:
        print("ok, lets go back and pick a new date range")
        startconfirmed = 0
        endconfirmed = 0

    continue

print("beginning Monitor API queries...")
# progress bar for session iteration
pbar = tqdm(desc='row progress', total=odatacount['@odata.count'])

# iterate through paginated Odata responses.  For each query returned, format data into output array
while continuemarker > 0:

    query_url: str = f"https://api-us.cloud.com/monitorodata/Sessions?$filter=StartDate " \
                     f"ge {startdate} and EndDate le {enddate}&$expand=ApplicationInstances" \
                     f"($select=StartDate,EndDate,ApplicationId;$expand=application($select=Name,Path))," \
                     f"User($select=Upn),connections" \
                     f"($top=1;$select=ClientVersion,ClientPlatform), " \
                     f"machine($select = DnsName;$expand = desktopgroup($select = Name))" \
                     f"&$select=StartDate,EndDate,SessionType,SessionKey" \
                     f"&$skip={skipcount}"

    # check validity of bearer token
    if datetime.now() > bearer_expiration:
        # bearer token has expired, need to retrieve a new one in order to continue with the queries
        print("\n")
        print("Bearer token expired, retrieving new token in order to continue with data collection")

        # send parameters to function to retrieve token
        token: Response = get_bearer_token(client_id, client_secret)

        # Read token from auth response and prepend necessary syntax
        bearer_token = 'CwsAuth Bearer=%s' % token.json()["token"]

        # store bearer token expiration - needed to check validity for large queries that take more than 60 minutes
        bearer_expiration = datetime.now() + (timedelta(seconds=token.json()['expiresIn'] - 120))

    # send URL to API query function and capture json output
    odata: Response = query_api(query_url, bearer_token, customer_name).json()

    for x in odata['value']:
        if x['StartDate'] == x['EndDate']:
            continue
        try:
            if x['ApplicationInstances'].__len__() > 0:

                for y in x['ApplicationInstances']:
                    # print(y)
                    output.append([x['User']['Upn'],
                                   x['Connections'][0]['ClientPlatform'],
                                   x['Connections'][0]['ClientVersion'],
                                   x['SessionKey'],
                                   y['ApplicationId'],
                                   y['Application']['Name'],
                                   y['Application']['Path'],
                                   y['Application']['Path'].split('\\')[-1],
                                   appcheck(y['Application']['Path'].split('\\')[-1]),
                                   appdetails(y['ApplicationId']),
                                   datetime.strptime(y['StartDate'][:19], '%Y-%m-%dT%H:%M:%S'),
                                   datetime.strptime(y['EndDate'][:19], '%Y-%m-%dT%H:%M:%S'),
                                   duration(y['EndDate'], y['StartDate']),
                                   datetime.strptime(x['StartDate'][:19], '%Y-%m-%dT%H:%M:%S'),
                                   datetime.strptime(x['EndDate'][:19], '%Y-%m-%dT%H:%M:%S'),
                                   duration(x['EndDate'], x['StartDate']),
                                   x['Machine']['DnsName'],
                                   dg_exists(x['Machine']['DesktopGroup'])])
            else:
                output.append([x['User']['Upn'],
                               x['Connections'][0]['ClientPlatform'],
                               x['Connections'][0]['ClientVersion'],
                               x['SessionKey'],
                               None, None, None, None, None, None, None, None, None,
                               datetime.strptime(x['StartDate'][:19], '%Y-%m-%dT%H:%M:%S'),
                               datetime.strptime(x['EndDate'][:19], '%Y-%m-%dT%H:%M:%S'),
                               duration(x['EndDate'], x['StartDate']),
                               x['Machine']['DnsName'],
                               dg_exists(x['Machine']['DesktopGroup'])])

        except Exception:
            bad_row_count += 1
            pass

    if odata.__len__() > 2:
        skipcount += 100
        # continuemarker = 0
    else:
        continuemarker = 0

    pbar.update(100)
    continue

print("\n")
print("iteractions complete, invalid data found in {} rows of database".format(bad_row_count))
print("NOTE: it is expected to have some invalid rows, typically 1 in 1000 will have some corruption")
print("\n")
print("\n Data Collection Finished, formatting and writing out CSV")
print("\n")
# field names
fields = ['UPN', 'Client Platform', 'ClientVersion', 'SessionKey',
          'ApplicationId', 'App Name', 'App Path', 'App EXE',
          'Is Browser', 'CMD Line Arguments', 'App StartDate (UTC)', 'App EndDate (UTC)',
          'App Run Duration',
          'Session StartDate (UTC)', 'Session EndDate (UTC)', 'Session Duration',
          'Machine Dns Name', 'Delivery Group Name']

with open('monitoring_output.csv', 'w', newline='') as g:
    writer = csv.writer(g)
    writer.writerow(fields)
    writer.writerows(output)

print("All Done, have written a CSV to the same local directory that the EXE was run from called Monitoring Output")
print("\n")
input("Press Enter to Exit")

# home for lunch
