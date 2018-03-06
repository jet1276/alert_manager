import os
import sys
import urllib
import json
import re

import splunk.appserver.mrsparkle.lib.util as util
import splunk.rest as rest

dir = os.path.join(util.get_apps_dir(), 'alert_manager', 'bin', 'lib')
if not dir in sys.path:
    sys.path.append(dir)

from AlertManagerUsers import *
from AlertManagerLogger import *
from CsvLookup import *

logger = setupLogger('helpers')

if sys.platform == "win32":
    import msvcrt
    # Binary mode is required for persistent mode on Windows.
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stderr.fileno(), os.O_BINARY)

from splunk.persistconn.application import PersistentServerConnectionApplication

def flatten_query_params(params):
    # Query parameters are provided as a list of pairs and can be repeated, e.g.:
    #
    #   "query": [ ["arg1","val1"], ["arg2", "val2"], ["arg1", val2"] ]
    #
    # This function simply accepts only the first parameter and discards duplicates and is not intended to provide an
    # example of advanced argument handling.
    flattened = {}
    for i, j in params:
        flattened[i] = flattened.get(i) or j
    return flattened


class HelpersHandler(PersistentServerConnectionApplication):
    def __init__(self, command_line, command_arg):
        PersistentServerConnectionApplication.__init__(self)

    def handle(self, in_string):
        request = json.loads(in_string)
        query_params = flatten_query_params(request['query'])

        action = query_params.get('action')
        sessionKey = request.get('session').get('authtoken')

        logger.debug('SESSIONKEY: %s', str(sessionKey))
        #logger.debug('QUERY_PARAMS: %s', str(query_params))

        payload = None
        err_payload = json.dumps({ 'payload': None })

        if not in_string or not action:
            logger.warn("Missing input payload or action query parameter")
            return err_payload

        if action == 'list_users':
            users = self._get_users(sessionKey=sessionKey)
            payload = { 'payload': users, 'status': 200 }

        elif action == 'list_status':
            status = self._get_status(sessionKey=sessionKey)
            payload = { 'payload': status, 'status': 200 }

        elif action == 'get_savedsearch_description':
            savedsearch = query_params.get('savedsearch')
            app = query_params.get('app')
            if not savedsearch or not app:
                return err_payload

            description = self._get_savedsearch_description(sessionKey=sessionKey, savedsearch=savedsearch, app=app)
            payload = { 'payload': description, 'status': 200 }

        elif action == 'list_notification_schemes':
            notification_schemes = self._get_notification_schemes(sessionKey=sessionKey)
            payload = { 'payload': notification_schemes, 'status': 200 }

        elif action == 'list_email_template_files':
            email_template_files = self._get_email_template_files(sessionKey=sessionKey)
            payload = { 'payload': email_template_files, 'status': 200 }

        elif action == 'list_externalworkflowaction_settings':
            externalworkflowaction_settings = self._get_externalworkflowaction_settings(sessionKey=sessionKey)
            payload = { 'payload': externalworkflowaction_settings, 'status': 200 }

        elif action == 'get_externalworkflowaction_command':
            logger.debug("START get_externalworkflowaction_command()")
            incident_id = query_params.get('incident_id')
            externalworkflowaction = query_params.get('externalworkflowaction')
            externalworkflowaction_label = query_params.get('externalworkflowaction_label')

            if not incident_id or (not externalworkflowaction and not externalworkflowaction_label):
                logger.info("Missing either incident_id and/or externalworkflowaction or externalworkflowaction_label query param")
                return err_payload

            externalworkflowaction_command = self._get_externalworkflowaction_command(sessionKey=sessionKey, incident_id=incident_id, externalworkflowaction=externalworkflowaction, externalworkflowaction_label=externalworkflowaction_label)
            payload = { 'payload': externalworkflowaction_command, 'status': 200 }

        else:
            logger.warn("Unknown action: %s" % action)
            return err_payload

        logger.debug('PAYLOAD: %s', str(payload))

        return json.dumps(payload)

    def _get_users(self, sessionKey):

        users = AlertManagerUsers(sessionKey=sessionKey)
        user_list = users.getUserList()

        logger.debug("user_list: %s " % json.dumps(user_list))

        return user_list

    def _get_status(self, sessionKey):

        uri = '/servicesNS/nobody/alert_manager/storage/collections/data/alert_status?output_mode=json'
        serverResponse, serverContent = rest.simpleRequest(uri, sessionKey=sessionKey)

        logger.info("server_response: %s" % json.dumps(serverResponse))
        entries = json.loads(serverContent)

        status_list = []
        if len(entries) > 0:
            for entry in entries:
                if int(entry['internal_only']) == 0:
                    se = {'status_description': entry['status_description'], 'status': entry['status']}
                    status_list.append(se)

        logger.info("status_list: %s " % json.dumps(status_list))

        return status_list

    def _get_savedsearch_description(self, sessionKey, savedsearch, app):
        uri = '/servicesNS/nobody/%s/admin/savedsearch/%s?output_mode=json' % \
              (app, urllib.quote(savedsearch.encode('utf8')))
        serverResponse, serverContent = rest.simpleRequest(uri, sessionKey=sessionKey, method='GET')

        savedSearchContent = json.loads(serverContent)

        if savedSearchContent["entry"][0]["content"]["description"]:
            return savedSearchContent["entry"][0]["content"]["description"]
        else:
            return ""


    def _get_notification_schemes(self, sessionKey):
        uri = '/servicesNS/nobody/alert_manager/storage/collections/data/notification_schemes?q=output_mode=json'
        serverResponse, serverContent = rest.simpleRequest(uri, sessionKey=sessionKey, method='GET')
        logger.debug("response: %s" % serverContent)
        entries = json.loads(serverContent)

        scheme_list = [ ]
        if len(entries) > 0:
            for entry in entries:
                scheme_list.append(entry['schemeName'])


        return scheme_list


    def _get_email_template_files(self, sessionKey):
        file_list = []

        file_default_dir = os.path.join(util.get_apps_dir(), "alert_manager", "default", "templates")
        if os.path.exists(file_default_dir):
            for f in os.listdir(file_default_dir):
                if re.match(r'.*\.html', f):
                    if f not in file_list:
                        file_list.append(f)

        file_local_dir = os.path.join(util.get_apps_dir(), "alert_manager", "local", "templates")
        if os.path.exists(file_local_dir):
            for f in os.listdir(file_local_dir):
                if re.match(r'.*\.html', f):
                    if f not in file_list:
                        file_list.append(f)

        return file_list

    def _get_externalworkflowaction_settings(self, sessionKey):
        uri = '/servicesNS/nobody/alert_manager/storage/collections/data/externalworkflowaction_settings?q=output_mode=json'
        serverResponse, serverContent = rest.simpleRequest(uri, sessionKey=sessionKey, method='GET')
        logger.debug("response: %s" % serverContent)
        entries = json.loads(serverContent)

        externalworkflowaction_settings = [ ]

        if len(entries) > 0:
            for entry in entries:
                if int(entry['disabled']) == 0:
                	ewa = {'label': entry['label'], 'title': entry['title'] }
                	externalworkflowaction_settings.append(ewa)

        return externalworkflowaction_settings

    def _get_externalworkflowaction_command(self, sessionKey, incident_id, externalworkflowaction = None, externalworkflowaction_label = None):
        # Gives back sendalert string based on template
        # Takes incident_id and external workflow action as a parameter
        # e.g. https://<hostname>/en-US/custom/alert_manager/helpers/get_externalworkflowaction_command?incident_id=<incident_id>&externalworkflowaction=<externalworkflowaction>&externalworkflowaction_label=<externalworkflowaction_label>

        logger.info("Run external workflow action")

        # Put together query string for incident data
        incident_id_query = '{"incident_id": "' + incident_id + '"}'
        incident_uri = '/servicesNS/nobody/alert_manager/storage/collections/data/incidents?q=output_mode=json&query=' + urllib.quote_plus(incident_id_query)

        # Put together query string for incident results
        incident_results_uri = '/servicesNS/nobody/alert_manager/storage/collections/data/incident_results?q=output_mode=json&query=' + urllib.quote_plus(incident_id_query)

        if externalworkflowaction:
            externalworkflowaction_query = '{"title": "' + externalworkflowaction + '"}'
        elif externalworkflowaction_label:
            externalworkflowaction_query = '{"label": "' + externalworkflowaction_label + '"}'

        externalworkflowaction_uri = '/servicesNS/nobody/alert_manager/storage/collections/data/externalworkflowaction_settings?q=output_mode=json&query=' + urllib.quote_plus(externalworkflowaction_query)

        # Get incident json
        serverResponse, serverContent = rest.simpleRequest(incident_uri, sessionKey=sessionKey, method='GET')
        logger.debug("response: %s" % serverContent)
        incident = json.loads(serverContent)

        # Get incident_results
        serverResponse, serverContent = rest.simpleRequest(incident_results_uri, sessionKey=sessionKey, method='GET')
        logger.debug("response: %s" % serverContent)
        incident_results = json.loads(serverContent)

        # Get externalworkflowaction settings json
        serverResponse, serverContent = rest.simpleRequest(externalworkflowaction_uri, sessionKey=sessionKey, method='GET')
        logger.debug("response: %s" % serverContent)
        externalworkflowaction_setting = json.loads(serverContent)

        if len(externalworkflowaction_setting) == 1:
            # Extract title from ewf settings
            title = externalworkflowaction_setting[0]['title']

            # Create dict for template replacement key/values
            incident_data = {}
            for key in incident[0]:
        	       incident_data[key] = incident[0][key]

            # Create dict for results
            if incident_results:
                incident_results=incident_results[0]['fields']
                results = {}
                for key in incident_results[0]:
                    results['result.' + key] = incident_results[0][key]

                # Append results to incident data
                incident_data.update(results)

            # Get parameters
            if 'parameters' in externalworkflowaction_setting[0]:
                parameters = externalworkflowaction_setting[0]['parameters']

                # Change parameters from Splunk variables to Python variables ( remove appended $)
                parameters=re.sub('(?<=\w)\$', '', parameters)

                # Allow dot in pattern for template
                class FieldTemplate(Template):
                    idpattern = r'[a-zA-Z][_a-zA-Z0-9.]*'

                # Create template from parameters
                parameters_template = FieldTemplate(parameters)

                # Build command string
                command = '| sendalert ' + title + ' ' + parameters_template.safe_substitute(incident_data)
            else:
                command = '| sendalert ' + title

            # Return command
            return command
        else:
            logger.warn("Number of return external workflow action settings is incorrect. Expected: 1. Given: %s" % (len(externalworkflowaction_setting)))
            return ""