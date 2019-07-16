#!/usr/bin/env python
#
# Original source: https://github.com/reneboer/python-carnet-client/
#
import re
import requests
import json
import sys
import time
import argparse


#Login details Volkswagen We Connect
carnet_username ='' # VW Car-net registered e-mail address
carnet_password = '' # VW Car-net password

#Domoticz Connection Details
DOMOTICZ_SERVER = '' # IP/Hostname to Domoticz Server
DOM_BATTERY_LEVEL_VALUE = '' # IDX of Device/Custom percentage sensor
DOM_RANGE_VALUE = '' # IDX of Device/Custom Sensor
DOM_CHARGE_SWITCH = '' # IDX of Device/Virtual Switch
DOM_HEAT_SWITCH = '' # IDX of Device/Virtual Switch
DOM_WINDOW_SWITCH = '' # IDX of Device/Virtual Switch
DOM_PLUGIN_SWITCH = '' # IDX of Device/Virtual Switch
DOM_LOCK_SWITCH = '' # IDX of Device/Virtual Switch
DOM_REMAINING_CHARGE_TIME = '' # IDX Device/Text Sensor

#Username for domoticz
DOM_USERNAME = ''
DOM_PASSWORD = ''

class VWCarnet(object):
    def __init__(self, args):
        self.carnet_username = carnet_username
        self.carnet_password = carnet_password
        self.carnet_retry = args.carnet_retry
        self.carnet_wait = args.carnet_wait
        self.carnet_task = args.carnet_task
        if self.carnet_retry:
            self.carnet_wait = True

        # Fake the VW CarNet mobile app headers
        self.headers = { 'Accept': 'application/json, text/plain, */*', 'Content-Type': 'application/json;charset=UTF-8', 'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0.1; D5803 Build/23.5.A.1.291; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/63.0.3239.111 Mobile Safari/537.36' }
        self.session = requests.Session()
        self.timeout_counter = 30 # seconds

        self._carnet_logon()

    def _carnet_logon(self):
        AUTHHEADERS = { 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0.1; D5803 Build/23.5.A.1.291; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/63.0.3239.111 Mobile Safari/537.36' }
        auth_base_url = "https://identity.vwgroup.io"
        base_url = "https://www.portal.volkswagen-we.com"
        landing_page_url = base_url + '/portal/en_GB/web/guest/home'
        get_login_url = base_url + '/portal/en_GB/web/guest/home/-/csrftokenhandling/get-login-url'
        complete_login_url = base_url + "/portal/web/guest/complete-login"

        # Regular expressions to extract data
        csrf_re = re.compile('<meta name="_csrf" content="([^"]*)"/>')
        login_action_url_re = re.compile('<form id="userCredentialsForm" method="post" name="userCredentialsForm" action="([^"]*)">')
        login_relay_state_token_re = re.compile('<input type="hidden" name="relayStateToken" value="([^"]*)"/>')
        login_csrf_re = re.compile('<input type="hidden" name="_csrf" value="([^"]*)"/>')

        authcode_re = re.compile('&code=([^"]*)')

        def extract_csrf(r):
            return csrf_re.search(r.text).group(1)

        def extract_login_action_url(r):
            return login_action_url_re.search(r.text).group(1)

        def extract_login_relay_state_token(r):
            return login_relay_state_token_re.search(r.text).group(1)

        def extract_login_csrf(r):
            return login_csrf_re.search(r.text).group(1)

        def extract_code(r):
            return authcode_re.search(r).group(1)

        def build_complete_login_url(state):
            return complete_login_url + '?p_auth=' + state + '&p_p_id=33_WAR_cored5portlet&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view&p_p_col_id=column-1&p_p_col_count=1&_33_WAR_cored5portlet_javax.portlet.action=getLoginStatus'

        # Request landing page and get CSRF:
        #print("Requesting first CSRF from landing page (", landing_page_url, ")...", sep='')
        r = self.session.get(landing_page_url)
        if r.status_code != 200:
            return ""
        csrf = extract_csrf(r)
        #print("CSRF found to be '", csrf, "'", sep='')

        # Request login page and get CSRF
        AUTHHEADERS["Referer"] = base_url + '/portal'
        AUTHHEADERS["X-CSRF-Token"] = csrf
        r = self.session.post(get_login_url, headers=AUTHHEADERS)
        if r.status_code != 200:
            return ""
        login_url = json.loads(r.text).get("loginURL").get("path")
        #print("SSO Login url found to be '", login_url, "'", sep='')

        # no redirect so we can get values we look for
        r = self.session.get(login_url, allow_redirects=False, headers=AUTHHEADERS)
        if r.status_code != 302:
            return ""
        login_form_url = r.headers.get("location")
        #print("Login form url is found to be '", login_form_url, "'", sep='')

        # now get actual login page and get various details for the post to login.
        # Login post url must be found in the content of the login form page:
        # <form id="userCredentialsForm" method="post" name="userCredentialsForm" action="/signin-service/v1/b7a5bb47-f875-47cf-ab83-2ba3bf6bb738@apps_vw-dilab_com/signin/emailPassword">

        # We need to post the following
        # email=
        # password=
        # relayStateToken=
        # _csrf=
        # login=true

        r = self.session.get(login_form_url, headers=AUTHHEADERS)
        if r.status_code != 200:
            return ""
        login_action_url = auth_base_url + extract_login_action_url(r)
        login_relay_state_token = extract_login_relay_state_token(r)
        login_csrf = extract_login_csrf(r)
        #print("Page to post login details to '", login_action_url, "', relayStateToken '", login_relay_state_token,
        #	"', _csrf '", login_csrf, "'", sep='')


        # Login with user details
        del AUTHHEADERS["X-CSRF-Token"]
        AUTHHEADERS["Referer"] = login_form_url
        AUTHHEADERS["Content-Type"] = "application/x-www-form-urlencoded"

        post_data = {
            'email': self.carnet_username,
            'password': self.carnet_password,
            'relayStateToken': login_relay_state_token,
            '_csrf': login_csrf,
            'login': 'true'
        }
        r = self.session.post(login_action_url, data=post_data, headers=AUTHHEADERS, allow_redirects=False)

        if r.status_code != 302:
            return ""

        # Now we are going through 4 redirect pages, before finally landing on complete-login page.
        # Allow redirects to happen
        ref2_url = r.headers.get("location")
        #print("Successfully login through the vw auth system. Now proceeding through to the we connect portal.", ref2_url)

        # load ref page
        r = self.session.get(ref2_url, headers=AUTHHEADERS, allow_redirects=True)
        if r.status_code != 200:
            return ""

        #print("Now we are at ", r.url)
        portlet_code = extract_code(r.url)
        #print("portlet_code is ", portlet_code)
        state = extract_csrf(r)
        #print("state is ", state)

        # Extract csrf and use in new url as post
        # We need to include post data
        # _33_WAR_cored5portlet_code=

        # We need to POST to
        # https://www.portal.volkswagen-we.com/portal/web/guest/complete-login?p_auth=cF3xgdcf&p_p_id=33_WAR_cored5portlet&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view&p_p_col_id=column-1&p_p_col_count=1&_33_WAR_cored5portlet_javax.portlet.action=getLoginStatus
        # To get the csrf for the final json requests
        # We also need the base url for json requests as returned by the 302 location. This is the location from the redirect

        AUTHHEADERS["Referer"] = ref2_url
        post_data = {
            '_33_WAR_cored5portlet_code': portlet_code
        }
        #print("Complete_url_login: ", build_complete_login_url(state))
        r = self.session.post(build_complete_login_url(state), data=post_data, allow_redirects=False, headers=AUTHHEADERS)
        if r.status_code != 302:
            return ""
        base_json_url = r.headers.get("location")
        r = self.session.get(base_json_url, headers=AUTHHEADERS)
        #We have a new CSRF
        csrf = extract_csrf(r)
        # done!!!! we are in at last
        # Update headers for requests
        self.headers["Referer"] = base_json_url
        self.headers["X-CSRF-Token"] = csrf
        #print("Login successful. Base_json_url is found as", base_json_url)
        self.url = base_json_url

    def _carnet_post(self, command):
        #print(command)
        r = self.session.post(self.url + command, headers = self.headers)
        return r.text

    def _carnet_post_action(self, command, data):
        #print(command)
        r = self.session.post(self.url + command, json=data, headers = self.headers)
        return r.text


    def _carnet_retrieve_carnet_info(self):
        vehicle_data = {}
        vehicle_data_messages = json.loads(self._carnet_post( '/-/msgc/get-new-messages'))
        vehicle_data_location = json.loads(self._carnet_post('/-/cf/get-location'))

        if self.carnet_wait:
            # request vehicle details, takes some time to get
            self._carnet_post('/-/vsr/request-vsr')
            vehicle_data_status = json.loads(self._carnet_post('/-/vsr/get-vsr'))
            counter = 0
            while vehicle_data_status['vehicleStatusData']['requestStatus'] == 'REQUEST_IN_PROGRESS':
                vehicle_data_status = json.loads(self._carnet_post('/-/vsr/get-vsr'))
                counter +=1
                time.sleep(1)
                if counter > self.timeout_counter:
                    break
        else:
            vehicle_data_status = json.loads(self._carnet_post('/-/vsr/get-vsr'))
        vehicle_data_details = json.loads(self._carnet_post('/-/vehicle-info/get-vehicle-details'))
        vehicle_data_emanager = json.loads(self._carnet_post('/-/emanager/get-emanager'))

        vehicle_data['messages'] = vehicle_data_messages
        vehicle_data['location'] = vehicle_data_location
        vehicle_data['status'] = vehicle_data_status
        vehicle_data['details'] = vehicle_data_details
        vehicle_data['emanager'] = vehicle_data_emanager

        return vehicle_data

    def _carnet_start_charge(self):
        post_data = {
            'triggerAction': True,
            'batteryPercent': '100'
        }
        return json.loads(self._carnet_post_action('/-/emanager/charge-battery', post_data))

    def _carnet_stop_charge(self):
        post_data = {
            'triggerAction': False,
            'batteryPercent': '99'
        }
        return json.loads(self._carnet_post_action('/-/emanager/charge-battery', post_data))


    def _carnet_start_climat(self):
        post_data = {
            'triggerAction': True,
            'electricClima': True
        }
        return json.loads(self._carnet_post_action('/-/emanager/trigger-climatisation', post_data))

    def _carnet_stop_climat(self):
        post_data = {
            'triggerAction': False,
            'electricClima': True
        }
        return json.loads(self._carnet_post_action('/-/emanager/trigger-climatisation', post_data))

    def _carnet_start_window_melt(self):
        post_data = {
            'triggerAction': True
        }
        return json.loads(self._carnet_post_action('/-/emanager/trigger-windowheating', post_data))

    def _carnet_stop_window_melt(self):
        post_data = {
            'triggerAction': False
        }
        return json.loads(self._carnet_post_action('/-/emanager/trigger-windowheating', post_data))

    def _carnet_print_carnet_info(self):
        vehicle_data = self._carnet_retrieve_carnet_info()
        # vehicle_located, vehicle_located_link  = self._google_get_location(str(vehicle_data['location']['position']['lng']), str(vehicle_data['location']['position']['lat']))

        # Availible Values Status
        # Next service inspection: vehicle_data['details']['vehicleDetails']['serviceInspectionData']
        # ODO Meter: vehicle_data['details']['vehicleDetails']['distanceCovered']
        # Last vehicle update: vehicle_data['details']['vehicleDetails']['lastConnectionTimeStamp'][0], vehicle_data['details']['vehicleDetails']['lastConnectionTimeStamp'][1]

        # Availible Location Status
        # Latitude: %s' % vehicle_data['location']['position']['lat'])
        # Longitude: %s' % vehicle_data['location']['position']['lng'])
        # if vehicle_located:
        # 	print(' Located: %s' % (vehicle_located))
        # 	if vehicle_located_link:
        # 		print(' Link: %s' % (vehicle_located_link))

        # Availible Values eManager
        # Charger max ampere: vehicle_data['emanager']['EManager']['rbc']['settings']['chargerMaxCurrent']
        # External power connected: vehicle_data['emanager']['EManager']['rbc']['status']['extPowerSupplyState']
        # Electric range left: vehicle_data['emanager']['EManager']['rbc']['status']['electricRange']
        # Charging state: vehicle_data['emanager']['EManager']['rbc']['status']['chargingState']
        # Charging time left: vehicle_data['emanager']['EManager']['rbc']['status']['chargingRemaningHour'], vehicle_data['emanager']['EManager']['rbc']['status']['chargingRemaningMinute']
        # Climatisation target temperature: vehicle_data['emanager']['EManager']['rpc']['settings']['targetTemperature']
        # Climatisation state: vehicle_data['emanager']['EManager']['rpc']['status']['climatisationState']
        # Windowheating state front: vehicle_data['emanager']['EManager']['rpc']['status']['windowHeatingStateFront']
        # Windowheating state rear: vehicle_data['emanager']['EManager']['rpc']['status']['windowHeatingStateRear']

        # Update Domoticz device with Battery level
        BATTERY_LEVEL = vehicle_data['emanager']['EManager']['rbc']['status']['batteryPercentage']
        requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_BATTERY_LEVEL_VALUE + '&nvalue=0&svalue=' + str(BATTERY_LEVEL), auth=(DOM_USERNAME, DOM_PASSWORD))

        # Update Domoticz device with Battery range
        BATTERY_RANGE = vehicle_data['emanager']['EManager']['rbc']['status']['electricRange']
        requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_RANGE_VALUE + '&nvalue=0&svalue=' + str(BATTERY_RANGE), auth=(DOM_USERNAME, DOM_PASSWORD))

        # Update Domoticz Charge switch with current status
        CHARGE_STATE = vehicle_data['emanager']['EManager']['rbc']['status']['chargingState']
        if CHARGE_STATE == 'CHARGING':
            requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_CHARGE_SWITCH + '&nvalue=1', auth=(DOM_USERNAME, DOM_PASSWORD))
        else:
            requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_CHARGE_SWITCH + '&nvalue=0', auth=(DOM_USERNAME, DOM_PASSWORD))

        # UPDATE PLUGIN STATE
        PLUGIN_STATE = vehicle_data['emanager']['EManager']['rbc']['status']['pluginState']
        if PLUGIN_STATE == 'CONNECTED':
            requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_PLUGIN_SWITCH + '&nvalue=1', auth=(DOM_USERNAME, DOM_PASSWORD))
        else:
            requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_PLUGIN_SWITCH + '&nvalue=0', auth=(DOM_USERNAME, DOM_PASSWORD))

        # Update Domoticz Heating switch with current value
        CLIMA_STATE = vehicle_data['emanager']['EManager']['rpc']['status']['climatisationState']
        if CLIMA_STATE == 'OFF':
            requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_HEAT_SWITCH + '&nvalue=0', auth=(DOM_USERNAME, DOM_PASSWORD))
        else:
            requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_HEAT_SWITCH + '&nvalue=1', auth=(DOM_USERNAME, DOM_PASSWORD))

        # Update Domoticz Windows Heating switch with current value
        WINDOWHEAT_STATE_FRONT = vehicle_data['emanager']['EManager']['rpc']['status']['windowHeatingStateFront']
        WINDOWHEAT_STATE_REAR = vehicle_data['emanager']['EManager']['rpc']['status']['windowHeatingStateRear']
        if WINDOWHEAT_STATE_REAR == 'ON': # Windows heating is ON
            requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_WINDOW_SWITCH + '&nvalue=1', auth=(DOM_USERNAME, DOM_PASSWORD))
        else: # If windows heating is off
            requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_WINDOW_SWITCH + '&nvalue=0', auth=(DOM_USERNAME, DOM_PASSWORD))

        #UPDATE LOCK STATE
        LOCK_STATE = vehicle_data['status']['vehicleStatusData']['lockData']['left_front']
        if LOCK_STATE == 2:
            requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_LOCK_SWITCH + '&nvalue=1', auth=(DOM_USERNAME, DOM_PASSWORD))
        else:
            requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_LOCK_SWITCH + '&nvalue=0', auth=(DOM_USERNAME, DOM_PASSWORD))

        #Update remaining charge time
        REMAINING_HOUR = vehicle_data['emanager']['EManager']['rbc']['status']['chargingRemaningHour']
        REMAINING_MINUTE = vehicle_data['emanager']['EManager']['rbc']['status']['chargingRemaningMinute']
        requests.get('http://' + DOMOTICZ_SERVER + '/json.htm?type=command&param=udevice&idx=' + DOM_REMAINING_CHARGE_TIME + '&nvalue=0&svalue=' + REMAINING_HOUR + "." + REMAINING_MINUTE, auth=(DOM_USERNAME, DOM_PASSWORD))

    def _carnet_print_action(self, resp):
        print('-- Information --')
        print(' Task: %s' % (self.carnet_task))
        if not 'actionNotification' in resp:
            print(' Status: FAILED, %s' % resp)
        else:
            print(' Status: %s' % resp['actionNotification']['actionState'])

    def _carnet_print_action_notification_status(self):
        if self.carnet_wait:
            counter = 0
            while counter < self.timeout_counter:
                resp = json.loads(self._carnet_post('/-/emanager/get-notifications'))
                if 'actionNotificationList' in resp:
                    print('-- Information --')
                    for notification in resp['actionNotificationList']:
                        print(' Task: %s' % (self.carnet_task))
                        print(' Status: %s' % notification['actionState'])
                        if notification['actionState'] == 'FAILED':
                            print(' Message: %s, %s' % (notification['errorTitle'], notification['errorMessage']))
                            return False
                        if notification['actionState'] == 'SUCCEEDED':
                            return True
                time.sleep(1)
                counter += 1

            print('-- Information --')
            print(' Task: %s' % (self.carnet_task))
            print(' Status: ERROR, request timed out')
            return False
        return True

    def _carnet_do_action(self):
        if self.carnet_task == 'info':
            self._carnet_print_carnet_info()
            return True
        elif self.carnet_task == 'start-charge':
            resp = self._carnet_start_charge()
            self._carnet_print_action(resp)
            return self._carnet_print_action_notification_status()

        elif self.carnet_task == 'stop-charge':
            resp = self._carnet_stop_charge()
            self._carnet_print_action(resp)
            return self._carnet_print_action_notification_status()

        elif self.carnet_task == 'start-climat':
            resp = self._carnet_start_climat()
            self._carnet_print_action(resp)
            return self._carnet_print_action_notification_status()

        elif self.carnet_task == 'stop-climat':
            resp = self._carnet_stop_climat()
            self._carnet_print_action(resp)
            return self._carnet_print_action_notification_status()

        elif self.carnet_task == 'start-window-heating':
            resp = self._carnet_start_window_melt()
            self._carnet_print_action(resp)
            return self._carnet_print_action_notification_status()

        elif self.carnet_task == 'stop-window-heating':
            resp = self._carnet_stop_window_melt()
            self._carnet_print_action(resp)
            return self._carnet_print_action_notification_status()

    def _carnet_run_action(self):
        if self.carnet_retry:
            retry_counter = 0
            while True:
                retry_counter += 1
                print('-- Information --')
                print(' Task: %s' % (self.carnet_task))
                print(' Retry: %s/%s' % (retry_counter, self.carnet_retry))
                if self._carnet_do_action() or retry_counter >= int(self.carnet_retry):
                    break
        else:
            self._carnet_do_action()

    def _google_get_location(self, lng, lat):
        counter = 0
        location = False
        location_link = False
        while counter < 3:
            lat_reversed = str(lat)[::-1]
            lon_reversed = str(lng)[::-1]
            lat = lat_reversed[:6] + lat_reversed[6:]
            lon = lon_reversed[:6] + lon_reversed[6:]
            try:
                req = requests.get('https://maps.googleapis.com/maps/api/geocode/json?address=' + str(lat[::-1]) + ',' + str(lon[::-1]))
            except:
                time.sleep(2)
                continue
            data = json.loads(req.content)
            if 'status' in data and data['status'] == 'OK':
                location = data["results"][0]["formatted_address"]
                location_link = "https://maps.google.com/maps?z=12&t=m&q=loc:%s+%s" % (str(lat[::-1]), str(lon[::-1]))
                break

            time.sleep(2)
            continue

        return location, location_link


def main():
    parser = argparse.ArgumentParser()
    required_argument = parser.add_argument_group('required arguments')
    required_argument.add_argument('-t', action = 'store', dest='carnet_task', choices = ['info', 'start-charge', 'stop-charge', 'start-climat', 'stop-climat', 'start-window-heating', 'stop-window-heating'], required=True)
    parser.add_argument('-w', dest='carnet_wait', action = 'store_true', default = False, help='Specify -w if you want to wait for response on your actions from your vehicle', required=False)
    parser.add_argument('-r', dest='carnet_retry', action='store', type = int, default=False, help='Specify -r <number of retries> if you want to retry action if it fails', required=False)
    args = parser.parse_args()

    vw = VWCarnet(args)
    vw._carnet_run_action()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Aborting..')
        sys.exit(1)
