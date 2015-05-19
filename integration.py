import qtest.firsttiercaller as firsttiercaller
import qtest.resourceallocationcaller as secondtiercaller
import pyjsonrpc
import json
import threading
import random
import calendar
import time
import logging

from optparse import OptionParser

class Integration(object):

    _switch_ports = {}
    _combined_switches = {}
    _max_throughput = {}
    _first_tier_result_mapping = ['A', 'B', 'C', 'D', 'E']
    _meters = {}
    _testing = False

    def __init__(self, config, poll, threshold, capacity, host, port):
        self._threshold = threshold
        self._capacity = capacity
        self._load_config(config)
        self._merge_switch_tiers()
        self._controller = self.Controller(host, port, self._testing)
        self._experience = self.Experience()
        self._initialise_switch_ports()
        self._initialise_meters()
        self._reset_counters()
        self._poll(float(poll), self.config["network"].keys())

    def _merge_switch_tiers(self):
        self._combined_switches = self.config["network"]["first"].copy()
        self._combined_switches.update(self.config["network"]["second"])

    def _initialise_switch_ports(self):
        for switch, value in self._combined_switches.iteritems() :
            port_mapping = {}
            for port in value["port_mapping"].keys():
                port_mapping[port] = {"upload" : 0, "download" : 0}
            self._switch_ports[switch] = (port_mapping)
            self._max_throughput[switch] = (port_mapping)

    def _initialise_meters(self):
        self._initialise_service_meters()
        self._initialise_port_meters()

    def _initialise_port_meters(self):
        for tier in self.config["network"].keys():
            for switch, value in self.config["network"][tier].iteritems():
                port = value["uplink"]
                limit = self.config["limits"][tier]
                limit = limit  * 125 #Convert from kilobits to bytes
                self._controller.call(method="enforce_port_outbound", params=[switch, port, limit])

    def _initialise_service_meters(self):
        switch = None
        for tier in self.config["network"].keys():
            self._meters[tier] = {}
            if tier == 'first':
                switch = self.config["network"][tier].keys()[0]
            for view, ip in self.config["servers"].iteritems():
               self._meters[tier][view] =  self._create_service_meters(ip, self._capacity, view, switch)

    def _create_service_meters(self, source, limit, view, switch=None):
        meter_ids = {}
        for client_id, details in self.config["clients"][view].iteritems():
            if switch:
                port = self._match_first_tier_port(details["switch"])
                meter_ids = self._service_meter_helper(switch, source, details["ip"], limit, meter_ids, port)
            else:
                meter_ids = self._service_meter_helper(details["switch"], source, details["ip"], limit, meter_ids, details["port"])
        return meter_ids

    def _service_meter_helper(self, switch, source, destination, limit, meter_ids, port):
        meter_ids = self._check_meter_keys(switch, meter_ids)
        _id = self._controller.call(method="enforce_service", params=[switch, source, destination, limit])
        meter_ids[switch][destination] = {"meter_id" : _id, "limit" : limit, "port" : port}
        return meter_ids

    def _match_first_tier_port(self, switch):
        for details in self.config["network"]["first"].values():
            for port, connection in details["port_mapping"].iteritems():
                if switch == connection:
                    return port

    def _check_meter_keys(self, switch, meter_ids):
        if switch not in meter_ids.keys():
            meter_ids[switch] = {}
        return meter_ids

    def _available_bandwidth(self, tier, switch, port):
        _max = self._fetch_max(switch, port)
        background = self._fetch_background(tier, switch, port)
        bandwidth =  _max - background
        bandwidth = bandwidth * 0.008 #Convert from bytes to kilobits
        return bandwidth

    def _fetch_max(self, switch, port):
        return self._controller.call(method="report_port", params=[False, True, switch, port])[1]

    def _fetch_background(self, tier, switch, port):
        background = 0
        for details in self._meters[tier]["background"][switch].values():
            if port == details["port"]:
                background += self._controller.call(method="report_port", params=[True, False, switch, details["meter_id"]])[1]
        return background

    def _load_config(self, path):
        with open(path) as json_data:
            self.config = json.load(json_data)
            json_data.close()

    def _reset_counters(self):
        pass #TODO: Not yet implemented in modified Ryu controller


    def _fetch_stats(self, tier):
        for switch in self.config["network"][tier].keys():
            switch_ports = self._controller.call(method="report_switch_ports", params=[False, False, switch])
            if self._compare_switch_ports(tier, switch, switch_ports):
                self._recalculate(tier, switch)

    def _find_uplink_port(self, switch):
        return self._combined_switches[switch]["uplink"]

    def _recalculate(self, tier, switch):
        if tier == 'first':
            totalbw, households = self._fetch_parameters(switch, tier)
            result = self._experience.first(totalbw=totalbw, households=households)
            result = self._fix_household_result(switch, result)
            self._effect_first_tier_change(switch, result)
        elif tier == 'second':
            totalbw, clients = self._fetch_parameters(switch, tier)
            try:
                result = self._experience.second(totalbw=totalbw, clients=clients)
                self._effect_second_tier_change(switch, result)
                self._update_forgiveness_effect(result)
            except secondtiercaller.ImpossibleSolution as impossible:
                logging.debug('[integration][calculation] %s', impossible)

    def _update_forgiveness_effect(self, result):
        timestamp = calendar.timegm(time.gmtime())
        for client_id, allocation in result.iteritems():
            self._experience.forgiveness_effect(client=client_id, timestamp=timestamp, bitrate=allocation[3])

    def _effect_first_tier_change(self, switch, result):
        for household in result:
            switch, port = self._find_household_from_port(household["port"])
            limit = household["limit"]
            limit = limit * 125 #Convert from kilobits to bytes
            self._controller.call(method="enforce_port_outbound", params=[switch, port, limit])

    def _find_household_from_port(self, port_to_find):
        for details in self.config["network"]["first"].values():
            for port, switch in details["port_mapping"].iteritems():
                if port == port_to_find :
                    (switch, self._find_uplink_port(switch))

    def _effect_second_tier_change(self, switch, result):
        for client_id, allocation in result.iteritems():
            source = self.config["clients"]["foreground"][client_id]["ip"]
            destination = self.config["servers"]["foreground"]
            limit = allocation[3]
            limit = limit * 125 #Convert from kilobits to bytes
            self._controller.call(method="enforce_service", params=[switch, source, destination, limit])

    def _lookup_server(self):
        return self.config["servers"][0]

    def _fetch_parameters(self, switch, tier):
        uplink =  self._find_uplink_port(switch)
        totalbw = self._available_bandwidth(tier, switch, uplink)
        if tier == "second":
            clients = self._calculate_clients(switch, uplink, tier)
            return totalbw, clients
        elif tier == "first":
            households = self._calculate_households(switch, uplink, tier)
            return totalbw, households

    def _fix_household_result(self, switch, result):
        """Map index in result to household ID. Fixed mapping (see object variables)."""
        limits = []
        for index, limit in enumerate(result):
            household_id = self._first_tier_result_mapping[index]
            port = self._find_port_from_household_id(switch, household_id)
            limits.append({'household_id' : household_id, 'port' : port, 'limit' : limit})
        return limits

    def _find_port_from_household_id(self, switch, household_id_to_find):
        for port, household_id in self._combined_switches[switch]["household_id"].iteritems():
            if household_id == household_id_to_find:
                return port

    def _calculate_clients(self, switch, uplink, tier):
        clients = []
        for client_id, details in self.config["clients"]["foreground"].iteritems():
            if details["switch"] == switch:
                available_bw = self._available_bandwidth(tier, switch, details["port"])
                clients.append((client_id, available_bw, details["resolution"]))
        return clients


    def _calculate_households(self, switch, uplink, tier):
        households = []
        for port in self._switch_ports[switch]:
            if port != uplink:
                household_id = self._combined_switches[switch]["household_id"][port]
                available_bw = self._available_bandwidth(tier, switch, port)
                households.append((household_id, available_bw))
        return households

    def _compare_switch_ports(self, tier, switch, switch_ports_result):
        for port, throughput in self._switch_ports[switch].iteritems():
            try:
                #self._update_max_throughput(switch, port, 'upload', switch_ports_result[port][0])
                self._update_max_throughput(switch, port, 'download', switch_ports_result[port][1])
                #self._calculate_difference(switch_ports_result[port][0], throughput["upload"])
                self._calculate_difference(switch_ports_result[port][1], throughput["download"])
            except KeyError as key:
                logging.warning('[integration][comparison] Port not found in result: %s', key)
            except self.ChangeNotification as change:
                logging.debug('[integration][comparison] %s', change)
                return True

    def _calculate_difference(self, result, throughput):
        difference = result - throughput #download B/s
        if abs(difference) >= self._threshold:
            raise self.ChangeNotification("Threshold exceeded by " + str(abs(difference)) + "!")

    def _update_max_throughput(self, switch, port, field, value):
        if self._max_throughput[switch][port][field] < value:
            self._max_throughput[switch][port][field] = value

    def _poll(self, poll, tiers):
        threading.Timer(poll, self._poll, [poll, tiers]).start()
        for tier in tiers:
            self._fetch_stats(tier)

    class ChangeNotification(Exception):
        pass

    class Controller(object):

        def __init__(self, host, port, testing):
            self._testing = testing
            self._client = pyjsonrpc.HttpClient(url = "http://" + host + ":" + port + "/jsonrpc")

        def call(self, **kwargs):
            result = None
            logging.debug('[controller][call]: %s', kwargs)
            if self._testing:
                if kwargs['method'] == 'report_switch_ports':
                    result = { "1":self._generate_random_bandwidth(4),
                    "2":self._generate_random_bandwidth(4),
                    "3":self._generate_random_bandwidth(4),
                    "4":self._generate_random_bandwidth(4),
                    "5":self._generate_random_bandwidth(4),
                    "6":self._generate_random_bandwidth(4),
                    "7":self._generate_random_bandwidth(4)}
                elif kwargs['method'] == "enforce_service":
                    result = random.randint(53, 200)
                elif kwargs['method'] == "report_port":
                    result = self._generate_random_bandwidth(4)
            else:
                result = self._client.call(kwargs['method'], *kwargs['params'])
            logging.debug('[controller][result]: %s', result)
            return result

        def _generate_random_bandwidth(self, length):
            _max = 20000000
            _min = 300000
            bandwidth = []
            for _ in range(length):
                bandwidth.append(random.randint(_min, _max))
            return bandwidth

    class Experience(object):

        def __init__(self):
            self.first_tier = firsttiercaller.FirstTier()
            self.second_tier = secondtiercaller.SecondTier()

        def first(self, **kwargs):
            logging.debug('[experience][first][call]: %s', kwargs)
            result = self.first_tier.call(**kwargs)
            logging.debug('[experience][first][result]: %s', result)
            return result

        def second(self, **kwargs):
            logging.debug('[experience][second]: %s', kwargs)
            result = self.second_tier.call(**kwargs)
            logging.debug('[experience][first][result]: %s', result)
            return result

        def forgiveness_effect(self, **kwargs):
            logging.debug('[experience][forgiveness]: %s', kwargs)
            self.second_tier.set_session_index(**kwargs)

if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option("-i", "--interval", dest="interval", help="controller polling interval, measured in seconds", default=5.0)
    parser.add_option("-t", "--threshold", dest="threshold", help="change threshold at which to trigger a recalculation, measured in bytes", default=1000)
    parser.add_option("-c", "--capacity", dest="capacity", help="maximum capacity to initialise meter to, measured in bytes", default=1000000000)
    parser.add_option("-n", "--hostname", dest="host", help="controller hostname", default="localhost")
    parser.add_option("-p", "--port", dest="port", help="controller interface port", default=4000)
    (options, args) = parser.parse_args()
    logging.basicConfig(filename='debug.log',level=logging.DEBUG, format='[%(asctime)s:%(levelname)s] %(message)s')
    integration = Integration("config.json", float(options.interval), int(options.threshold), int(options.capacity), options.host, str(options.port))
