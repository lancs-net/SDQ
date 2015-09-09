import qtest.firsttiercaller as firsttiercaller
import qtest.resourceallocationcaller as secondtiercaller
import pyjsonrpc
import json
import threading
import random
import logging
import calendar
import time
from pygraph.classes.digraph import digraph
from optparse import OptionParser

class Integration(object):

    _testing = False #Change to true to include randomly generated test data instead of a real response
    first = []
    second = []
    limits = []
    tiers = ["first", "second"]
    _switch_port_results= {}
    _first_tier_result_mapping = ['A', 'B', 'C', 'D', 'E']

    def __init__(self, config, poll, threshold, capacity, host, port):
        self._parse_graph(self._load_graph(config))
        self._controller = self.Controller(host, port, self._testing)
        self._experience = self.Experience()
        #self._initialise_switch_ports()
        self._threshold = threshold
        self._poll(float(poll))

    def _load_graph(self, path):
        '''Load the JSON from a file.'''
        with open(path) as json_data:
            graph = json.load(json_data)
            json_data.close()
        return graph

    def _parse_graph(self, graph):
        '''Parse the JSON into a graph representation.'''
        self._graph = digraph()
        self._parse_nodes(graph)
        self._parse_edges(graph)

    def _parse_nodes(self, tree):
        '''Parse the nodes from JSON file into objects.'''
        for _type, node in tree["nodes"].iteritems():
            for _id, attrs in node.iteritems():
                attrs["type"] = _type
                self._graph.add_node(node=_id, attrs=attrs.items())
                try:
                    tier = getattr(self, attrs["tier"])
                    tier.append(_id)
                except KeyError:
                    pass

    def _parse_edges(self, tree):
        '''Parse the edge of the graph.'''
        for _id, attrs in tree["edges"].iteritems():
            self._graph.add_edge(edge=tuple(attrs["items"]), wt=1, label=_id, attrs=attrs.items())
            if "limit" in attrs.keys():
                self.limits.append(tuple(attrs["items"]))

    # def _initialise_switch_ports(self):
    #     '''For each of the edges, clear the current meters.'''
    #     for edge in self.limits:
    #         attrs = dict(self._graph.edge_attributes(edge))
    #         switch = self._get_field_from_node(attrs["items"][0], "dpid")
    #         self._controller.call(method="enforce_port_outbound", params=[switch, attrs["port"], attrs["limit"]])

    def _poll(self, poll):
        '''At a regular interval, poll each tier for their metrics.'''
        threading.Timer(poll, self._poll, [poll]).start()
        for tier in self.tiers:
            self._fetch_stats(tier)

    def _get_field_from_node(self, node, field):
        '''For a given node, retrieve a specific field value.'''
        try:
            return dict(self._graph.node_attributes(node))[str(field)]
        except KeyError:
            return {}

    def _get_field_from_edge(self, edge, field):
        '''For a given field, retrieve a specific field value.'''
        try:
            return dict(self._graph.edge_attributes(edge))[str(field)]
        except KeyError:
            return {}

    def _fetch_stats(self, tier):
        '''
        For a set of given nodes, retrieve the statistics from the OpenFlow controller.

        Check if a change has occured. If so, recalculate the QoE fairness.
        '''
        nodes = getattr(self, tier)
        for node in nodes:
            switch = self._get_field_from_node(node, "dpid")
            result = self._controller.call(method="report_switch_ports", params=[False, False, switch]) #TODO check this is returning expected value ready for _compare_switch_ports
	    if self._compare_switch_ports(tier, switch, result):
                 self._recalculate(tier, switch)

    def _compare_switch_ports(self, tier, switch, result):
        '''Check if a statistic has changed drastically in the result.'''
        if switch not in self._switch_port_results.keys():
            self._switch_port_results[switch] = {}
        for port, throughput in result.iteritems():
            if port not in self._switch_port_results[switch].keys():
                self._switch_port_results[switch][port] = throughput[2]
                continue
            else:
                current = throughput[2]
		print "Port", port," current ",current,"kpbs"
                previous = self._switch_port_results[switch][port]
		print "Port", port," previous ",previous,"kpbs" 
            self._switch_port_results[switch][port] = throughput[2]
            return self._calculate_difference(current, previous)

    def _calculate_difference(self, current, previous):
        '''Calculate the difference between the current and previous values.'''
        difference = current - previous
	print "Difference ",abs(difference)
        if abs(difference) >= self._threshold:
            return True

    def _recalculate(self, tier, switch):
        '''Call the correct recalculation function given the tier.'''
        getattr(self, '_recalculate_' + tier + '_tier')(switch)

    def _recalculate_first_tier(self, _):
        '''Recalculate the metrics for the first tier.'''
        totalbw, households = self._fetch_first_tier_stats()
        result = self._experience.first(totalbw=totalbw, households=households)
        switch = self._get_field_from_node(self.first[0], "dpid")
        result = self._fix_household_result(switch, result)
        self._effect_first_tier_change(switch, result)

    def _recalculate_second_tier(self, switch):
        '''Recalculate the metrics for the second tier.'''
        totalbw, clients, _ = self._fetch_second_tier_stats(switch)
        result = self._experience.second(totalbw=totalbw, clients=clients)
        self._effect_second_tier_change(switch, result)
        self._update_forgiveness_effect(result)

    def _update_forgiveness_effect(self, result):
        '''If a change has been made to the meters, update the forgiveness effect in the QoE function.'''
        timestamp = calendar.timegm(time.gmtime())
        for client_id, allocation in result.iteritems():
            self._experience.forgiveness_effect(client=client_id, timestamp=timestamp, bitrate=allocation[3])

    def _effect_second_tier_change(self, switch, result):
        '''Install a service meter in the second tier.'''
        for id_, allocation in result.iteritems():
            limit = allocation[3]
	    src = '192.168.1.235'
	    ip = [self._get_field_from_node(id_, 'ip')]
	    print 'Second tier change		 switch :',str(self._dp_name(switch)),' limit :',str(self._linear_meter_mapping(limit)),'kbps', src, ip
	    self._controller.call(method="enforce_service", params=[str(switch), src, ip, self._linear_meter_mapping(limit)])
    def _linear_meter_mapping(self, limit):
	return limit*1.7-38.482
#        return limit*1.592+200 
    def _effect_first_tier_change(self, switch, result):
        '''Install a service meter in the first tier.'''
        for household in result:
            neighbor = self._find_node_from_label("household", household["household_id"])
            src = '192.168.1.235'
            limit = household["limit"]
            dsts = self._fetch_ips_from_household(neighbor)
	    print 'First tier change			switch :',str(self._dp_name(switch)),' limit :', str(limit),'kbps', str(src),str(dsts)
            self._controller.call(method="enforce_service", params=[str(switch), src, dsts, limit])

    def _fetch_ips_from_household(self, node):
        '''Fetch a the IPs of the hosts within a given household.'''
        ips = []
        neighbors = self._graph.neighbors(node)
        for neighbor in neighbors:
        	ip = self._get_field_from_node(neighbor, 'ip')
        	if ip:
        		ips.append(ip)
        return ips

    def _fetch_first_tier_stats(self):
        '''Fetch the statistics from each of the switches attached to the aggregation (first tier) switch.'''
        households = []
        totalbw = 0
        background = 0
        # node = self.first[0]
        # neighbors = self._graph.neighbors(node)
        for second in self.second:
            household_available, _, household_background = self._fetch_second_tier_stats(second, dpid=False)
            background += household_background
            id_ = self._get_field_from_node(second, "household")
            households.append((id_, household_available))
        # for neighbor in list(set(neighbors)-set(self.second)): #probably only one
        #     port = self._get_field_from_edge((node, neighbor), "port")
        #     switch = self._get_field_from_node(node, "dpid")
        #     totalbw += self._controller.call(method="report_port", params=[False, True, switch, port])[3] #Rx - link max
        totalbw = 50000 #Kbps   TODO: Hard-coded according to experimental parameters as passive measurement not exercising full link capacity
        totalbw = totalbw - background
        logging.debug("Background traffic %s",background)
	return (totalbw, households)

    def _fetch_second_tier_stats(self, switch, dpid=True):
        '''Fetch the statistics from each of the hosts attached to a switch.'''
        clients = []
        totalbw = 0
        if dpid:
            node = self._find_node_from_label("dpid", switch)
        else:
            node = switch
        neighbors = self._classify_neighbors(node)
        for foreground in neighbors["foreground"]:
            clients.append(self._fetch_foreground(node, foreground))
        totalbw, background = self._fetch_switch(node, neighbors["switch"][0], neighbors["background"])
	print "Totalbw ",totalbw," clients ",clients," background",background
        return (totalbw, clients, background)

    def _classify_neighbors(self, node):
        '''Classify the neighbours into foreground and background hosts.'''
        neighbors = {}
        for neighbor in self._graph.neighbors(node):
            _type = self._get_field_from_node(neighbor, "type")
            if not neighbors.has_key(_type):
                neighbors[_type] = []
            neighbors[_type].append(neighbor)
        return neighbors

    def _fetch_foreground(self, node, neighbor):
        '''
        Fetch the foreground traffic for a node.

        Assumes no background traffic.
        '''
        port = self._get_field_from_edge((node, neighbor), "port")
    	switch = self._get_field_from_node(node, "dpid")
    	result = self._controller.call(method="report_port", params=[False, True, switch, port])
    	available_bandwidth = result[2] #Tx - link max
    	#available_bandwidth = self._convert_bits_to_kilobits(available_bandwidth)
    	resolution = self._get_field_from_node(neighbor, "resolution")
        return ((neighbor, available_bandwidth, resolution))

    def _convert_bits_to_kilobits(self, value):
        '''Convert bits to kilobits.'''
        return value/1000

    def _convert_kilobits_to_bits(self, value):
        '''Convert kilobits to bits.'''
        return value * 1000

    def _fetch_switch(self, node, neighbor, background):
        '''Fetch the background traffic and available bandwidth for a given switch.'''
        background_traffic = 0
        switch = self._get_field_from_node(node, "dpid")
        port = self._get_field_from_edge((node, neighbor), "port")
        max_bandwidth = self._controller.call(method="report_port", params=[False, True, switch, port])[3] #Rx - link max
        #max_bandwidth = 20000 #Kbps TODO: Hard-coded according to experimental parameters. Assumed bandwidth of 20mb
        print background
	for client in background:
            port = self._get_field_from_edge((node, client), "port")
            background_traffic += self._controller.call(method="report_port", params=[False, False, switch, port])[2] #Tx - current background
        available_bandwidth = max_bandwidth - background_traffic
        try:
            assert available_bandwidth >= 0
        except AssertionError:
            print available_bandwidth, max_bandwidth, background_traffic
            pass
	return available_bandwidth, background_traffic

    def _find_node_from_label(self, field, value):
        '''Find a node from a given label.'''
        for node in self._graph.nodes():
            if self._get_field_from_node(node, field) == value:
                return node

    def _fix_household_result(self, switch, result):
        '''Map index in result to household ID. Fixed mapping (see object variables).'''
        limits = []
        for index, limit in enumerate(result):
            household_id = self._first_tier_result_mapping[index]
            neighbor = self._find_node_from_label("household", household_id)
            node = self._find_node_from_label("dpid", switch)
            port = self._get_field_from_edge((node, neighbor), "port")
            limits.append({'household_id' : household_id, 'port' : port, 'limit' : limit})
        return limits


    def _dp_name(self, dpid):
	'''Converts dpids to openflow instance names. Just for debugging'''
	name=dpid
	if '239' in str(dpid):
            name = 't'
        elif '2115686243633600' in str(dpid):
            name = 'b'
        elif '708311360080320' in str(dpid):
            name = 'p1'
        elif '989786336790976' in str(dpid):
            name = 'p2'
        elif '1271261313501632' in str(dpid):
            name = 'p3'
        elif '1552736290212288' in str(dpid):
            name = 'p4'
        elif '1834211266922944' in str(dpid):
            name = 'p5'

	return name


    class Controller(object):
        '''Represents all communication with the controller.'''

        def __init__(self, host, port, testing):
            '''Connect to the controller.'''
            self._testing = testing
            self._client = pyjsonrpc.HttpClient(url = "http://" + host + ":" + port + "/jsonrpc")

        def call(self, **kwargs):
            '''Make a call to the controller.'''
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
                try:
                    result = self._client.call(kwargs['method'], *kwargs['params'])
                except pyjsonrpc.rpcerror.InternalError as e:
                    print e, kwargs
                #result = self._client.notify(kwargs['method'], *kwargs['params'])
                #result = None
                logging.debug('[controller][result]: %s', result)
            return result

        def _generate_random_bandwidth(self, length):
            '''Generate a random bandwidth for testing purposes.'''
            _max = 20000000
            _min = 300000
            bandwidth = []
            for _ in range(length):
                bandwidth.append(random.randint(_min, _max))
            return bandwidth


    class Experience(object):
        '''Represents all communication with the QoE code.'''

        def __init__(self):
            '''Initialise the two tier objects.'''
            self.first_tier = firsttiercaller.FirstTier()
            self.second_tier = secondtiercaller.SecondTier()

        def first(self, **kwargs):
            '''Make a call to the first tier code.'''
            logging.debug('[experience][first][call]: %s', kwargs)
            result = self.first_tier.call(**kwargs)
            logging.debug('[experience][first][result]: %s', result)
            return result

        def second(self, **kwargs):
            '''Make a call to the second tier code.'''
            logging.debug('[experience][second]: %s', kwargs)
            result = self.second_tier.call(**kwargs)
            logging.debug('[experience][second][result]: %s', result)
            return result

        def forgiveness_effect(self, **kwargs):
            '''Update the forgiveness effect. Only present in the second tier.'''
            logging.debug('[experience][forgiveness]: %s', kwargs)
            self.second_tier.set_session_index(**kwargs)

if __name__ == '__main__':
    parser = OptionParser()
    parser.add_option("-i", "--interval", dest="interval", help="controller polling interval, measured in seconds", default=5.0)
    parser.add_option("-t", "--threshold", dest="threshold", help="change threshold at which to trigger a recalculation, measured in kbits", default=200)
    parser.add_option("-c", "--capacity", dest="capacity", help="maximum capacity to initialise meter to, measured in bytes", default=1000000000)
    parser.add_option("-n", "--hostname", dest="host", help="controller hostname", default="localhost")
    parser.add_option("-p", "--port", dest="port", help="controller interface port", default=4000)
    (options, args) = parser.parse_args()
    logging.basicConfig(filename='debug.log',level=logging.DEBUG, format='[%(asctime)s:%(levelname)s]%(message)s')
    integration = Integration("config.json", float(options.interval), int(options.threshold), int(options.capacity), options.host, str(options.port))
