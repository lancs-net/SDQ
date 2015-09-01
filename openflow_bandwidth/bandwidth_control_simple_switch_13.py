from webob.static import DirectoryApp
from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from ryu.base import app_manager
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4

from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from ryu.base import app_manager

from rpc_server import *
from SwitchPoll import *
from multiprocessing import Process

import os
from threading import *
from pprint import pprint
from zlib import crc32 # used to create unique cookies for flows
import pyjsonrpc
from collections import namedtuple

PATH = os.path.dirname(__file__)

TimedMeterRecord = namedtuple('TimedMeterRecord', ['packet_in_count','byte_in_count','packet_band_count','byte_band_count', 'duration_sec','duration_nsec'])
MeterRecord = namedtuple('MeterRecord', ['packet_in_count','byte_in_count','packet_band_count','byte_band_count'])
PortStatRecord = namedtuple('PortStatRecord', ['tx_packets','rx_packets','tx_bytes','rx_bytes'])
TimedPortStatRecord = namedtuple('TimedPortStatRecord', ['tx_packets','rx_packets','tx_bytes','rx_bytes', 'duration_sec','duration_nsec'])
FlowStatRecord = namedtuple('FlowStatRecord', ['packet_count', 'byte_count', 'match', 'table_id', 'priority'])
TimedFlowStatRecord = namedtuple('TimedFlowStatRecord', ['packet_count', 'byte_count', 'match', 'table_id', 'priority', 'duration_sec', 'duration_nsec'])

class SimpleSwitch13(app_manager.RyuApp):
    '''An extention of the simple example switch. This module includes remote installaiton and monitoring of meters'''
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)

        self.mac_to_port = {}
        self.datapathdict = {}
	self.ip_to_port = {}

        #init polling thread
        switchPoll = SwitchPoll()
        pollThread = Thread(target=switchPoll.run, args=(10,self.datapathdict))
        pollThread.start()
        # print "Created polling threads"

        self.PORT_CURRENT = {}
        self.PORT_MAX = {}
        self.PORT_RATE = {}
        self.METER_CURRENT = {}
        self.METER_MAX = {}
        self.METER_RATE = {}

        Thread(target=rpc_server().run, args=(1,(self.PORT_RATE,self.PORT_MAX,self.METER_RATE,self.METER_MAX), self.add_meter_port,self.add_meter_service)).start()

        #Map for sw to meters to ports
        self.datapathID_to_meters = {}

        #Meter id for per flow based meters (Dont want port and flow meter ids conflicting)
        #starts at 53, hp
        # meter_id= 53
        self.datapathID_to_meter_ID= {}
	self.datapath_to_flows = {}



    @staticmethod
    def diff_time (t1_sec, t1_nsec, t2_sec, t2_nsec):
        def to_float (sec,nsec):
            return float(sec) + float(nsec)/10E9
        return to_float(t2_sec, t2_nsec) - to_float(t1_sec, t1_nsec)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
	'''Sends messages to switch to get information about them'''
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

	#delete existing flows - stops conflicts
	self.del_all_flows(datapath)
	self.send_barrier_request(datapath)

        # install table-miss flow entry
        #
        # We specify NO BUFFER to max_len of the output action due to
        # OVS bug. At this moment, if we specify a lesser number, e.g.,
        # 128, OVS will send Packet-In with invalid buffer_id and
        # truncated packet data. In that case, we cannot output packets
        # correctly.  The bug has been fixed in OVS v2.1.0.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]

	
	#flow mod for table miss :packetin to contoller if unrecognised by switch
	self.add_flow(datapath, 1, match, actions)
	
	#no lldp
	self.add_flow(datapath, 1, parser.OFPMatch(eth_type=0x88cc), [])

        #self.add_flow(datapath, 1, parser.OFPMatch(eth_dst="ff:ff:ff:ff:ff:ff"),[parser.OFPActionOutput(ofproto.OFPP_FLOOD,0)])        

        #Add new switches for polling
        self.datapathdict[datapath.id]=datapath



    def add_flow(self, datapath, priority, match, actions, buffer_id=None, meters=[], timeout=0, cookie=0, table_num=100):
        '''Add a flow to a datapath - modified to allow meters'''
	ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        #print ("Add flow, %s" % hex(cookie))
	
	#If destination is FF do not install flow. (Caused by switches flooding each other)
	
	inst = []
	self.logger.info("Installing flow on %s",self._dp_name(datapath.id))
        # print "The meter is :",meter

	if actions != []:
            inst.append(parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,actions))



	for meter in meters:
            # print "Sending flow mod with meter instruction, meter :", meter
	    if meter == -1:
	        inst.append(parser.OFPInstructionGotoTable(200))
	    #elif meter<50:
	    inst.append(parser.OFPInstructionMeter(meter))
	#	table_num=200
         #   else:
	#	if actions != []:
	#	     inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,actions),parser.OFPInstructionMeter(meter),parser.OFPInstructionGotoTable(200)]
	#	else:
	#	     inst = [parser.OFPInstructionMeter(meter),parser.OFPInstructionGotoTable(200)]


        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst, hard_timeout=timeout,
                                    idle_timeout=timeout, table_id=table_num, cookie=cookie)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst,
                                    hard_timeout=timeout, idle_timeout=timeout, table_id=table_num, cookie=cookie)
        datapath.send_msg(mod)

    def send_barrier_request(self, datapath):
        datapath.send_msg(datapath.ofproto_parser.OFPBarrierRequest(datapath))

    def add_meter_port(self, datapath_id, port_no, speed):
    	'''Adds a meter to a port on a switch. speed argument is in kbps'''
        print "ADDING METER TO PORT " + str(port_no) + " at " + str(speed) + " on dpid "+ str(datapath_id)
	datapath_id = int(datapath_id)
	
        if datapath_id not in self.datapathdict:
		"dont have dictionary"
		return -1
        datapath= self.datapathdict[datapath_id]
        
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

	#METER ID's WILL DIRECTLY RELATE TO PORT NUMBERS
        #change meter with meter_id <port_no>, on switch <datapath>, to have a rate of <speed>
	
	if datapath_id not in self.datapathID_to_meters:
	    self.datapathID_to_meters[datapath_id]={}
            # print "not in"
        port_to_meter = self.datapathID_to_meters[datapath_id]

        bands=[]
        
	#set starting bit rate of meter
        dropband = parser.OFPMeterBandDrop(rate=int(speed), burst_size=0)
	bands.append(dropband)
        #Delete meter incase it already exists (other instructions pre installed will still work)
        request = parser.OFPMeterMod(datapath=datapath,command=ofproto.OFPMC_DELETE,flags=ofproto.OFPMF_KBPS,meter_id=int(port_no),bands=bands)
        datapath.send_msg(request)
        #Create meter
        request = parser.OFPMeterMod(datapath=datapath,command=ofproto.OFPMC_ADD, flags=ofproto.OFPMF_KBPS,meter_id=int(port_no),bands=bands)
        datapath.send_msg(request)
	# print request
        #Prvent overwriting incase rule added before traffic seen
	port_to_meter[int(port_no)]=int(port_no)

        return 1

    def add_meter_service(self, datapath_id, src_addr, dst_addrs, speed):
        '''Adds meters to a datapath. The meter is between a single src to many dsts. speed argument is in kbps'''
	print "ADDING METER FOR SERVICE from " + str(src_addr) + " to "+ str(dst_addrs) + " at " + str(speed) + "Kbps on dp " + self._dp_name(datapath_id)
        datapath_id=int(datapath_id)
	if datapath_id not in self.datapathdict:
            print "### Error: datapath_id not in self.datapathdict"
            return -1
        else:
            datapath= self.datapathdict[datapath_id]

	speed= int(speed)

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
	

        if datapath_id in self.datapath_to_flows:
            flows = self.datapath_to_flows[datapath_id]
        else:
            flows = {}
            self.datapath_to_flows[datapath_id]=flows
       

	 #Check if meter id created for this switch
        if datapath_id in self.datapathID_to_meter_ID:
            meter_id = self.datapathID_to_meter_ID[datapath_id]
        else:
            meter_id=53
            self.datapathID_to_meter_ID[datapath_id]=meter_id

	key = src_addr + str(dst_addrs)
        #Check if the src and dst has already had a meter created for it
        if key in flows:
            #flow already exists!
            #find out what that flow used for its meter_id
            meter_id = flows[key]
        else:
            flows[key]=meter_id
	print key

        #create meter with rate of <speed> and intall - NEED TO GIVE A METER ID HIGHER THAN MAX PORTS
        bands=[]
        #set starting bit rate of meter
        dropband = parser.OFPMeterBandDrop(rate=speed, burst_size=0)
        bands.append(dropband)

        #Delete meter incase it already exists (other instructions pre installed will still work)
        request = parser.OFPMeterMod(datapath=datapath,command=ofproto.OFPMC_DELETE,flags=ofproto.OFPMF_KBPS,meter_id=meter_id,bands=bands)
        datapath.send_msg(request)

        #Create meter
        request = parser.OFPMeterMod(datapath=datapath,command=ofproto.OFPMC_ADD, flags=ofproto.OFPMF_KBPS,meter_id=meter_id,bands=bands)
        datapath.send_msg(request)


        #create flow with <src> and <dst> - with a higher priority than normal switch behaviour -
        #link to meter
	for dst_addr in dst_addrs:
		print dst_addr        	
		match = parser.OFPMatch(eth_type=0x800, ipv4_src=src_addr, ipv4_dst=dst_addr)
        	actions = [parser.OFPActionOutput(ofproto.OFPP_NORMAL)]
		#actions = []
        	cookie = 0x7fffffff & crc32(str(datapath)+src_addr+dst_addr)
        	# print "cookie: %s" % hex(cookie)
		# adds both meter for service and port
#		if dst_addr in self.ip_to_port[datapath_id]:
#			self.add_flow(datapath, 100, match, actions, buffer_id=None, meters=[meter_id,self.ip_to_port[datapath_id][dst_addr]], timeout=0, cookie=cookie)
#		else:
		self.add_flow(datapath, 101, match, actions, buffer_id=None, meters=[meter_id], timeout=0, cookie=cookie)
#			print "Warning ",dst_addr," not in   : ",self.ip_to_port[datapath_id]
        self.datapathID_to_meter_ID[datapath_id]=meter_id+1

        return meter_id

    def del_all_flows(self, datapath):
	'''Deletes all flows. Useful for when the controller is restarted
	   and we want to get rid of flows from a previous experiment'''
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        # msg = parser.OFPFlowMod(datapath=datapath, command=ofproto.OFPFC_DELETE, match=parser.OFPMatch(), table_id=ofproto.OFPTT_ALL)
        # datapath.send_msg(msg)
        #datapath.send_msg(parser.OFPFlowMod(datapath=datapath, command=ofproto.OFPFC_DELETE, match=parser.OFPMatch(), table_id=100))
	self.logger.info("Delete all flows on dp %s", datapath.id)

        match = parser.OFPMatch()
        instructions = []

        flow_mod = datapath.ofproto_parser.OFPFlowMod(datapath, 0, 0, 100, ofproto.OFPFC_DELETE, 0, 0, 1, ofproto.OFPCML_NO_BUFFER, ofproto.OFPP_ANY, ofproto.OFPG_ANY, 0, match, instructions)
	datapath.send_msg(flow_mod)


    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        '''Event triggered when packet is sent to the controller from the switch (packetin).
	   Mods are install for the switch to remember the packet and for meters for the flow.'''

	# If you hit this you might want to increase
        # the "miss_send_length" of your switch
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",
                              ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src
        
	dpid = datapath.id
	# print('DPID', dpid)
        self.mac_to_port.setdefault(dpid, {})
	self.ip_to_port.setdefault(dpid, {})
	#self.logger.info("%s", self.datapathdict)
        self.logger.info("packet in %s %s %s %s", self._dp_name(dpid), src, dst, in_port)


	if(pkt.get_protocol(ethernet.ethernet) and pkt.get_protocol(ipv4.ipv4)):
             ip4 = pkt.get_protocol(ipv4.ipv4)

             ip_dst = ip4.dst
             ip_src = ip4.src
             self.ip_to_port[dpid][ip_src] = in_port
	  #   print self.ip_to_port



        # learn a mac address to avoid FLOOD next time. Unless this is a flood! in which case we do not want to add it?
        self.mac_to_port[dpid][src] = in_port

	#Do not want to take destinations of flood. In that case, just flood.
        if dst in self.mac_to_port[dpid]:
	    # print "RECOGNISED mac to port, dst is ", dst, " sending to ", self.mac_to_port[dpid][dst]
            out_port = self.mac_to_port[dpid][dst]
	else:
            out_port = ofproto.OFPP_FLOOD
	    #print "did not recognise, dst is ", dst


        #get port to meter for this switch (mainly to see if meter already exists)
        #print self.datapathID_to_meters
	#check if switch already seen
	if dpid not in self.datapathID_to_meters:
		self.datapathID_to_meters[dpid]={}
	port_to_meter= self.datapathID_to_meters[dpid]


        #Create new meters
        #Check for flood, dont want to add meter for flood
        if out_port != ofproto.OFPP_FLOOD:
             # print "NOT A FLOOD PACKET"
             if out_port in port_to_meter:
                     #if the meter already exists for THIS SWITCH set instruction to use
                     # print "Meter already exists for this port"
                     pass
             else:
                 #This controller not added meter before, need to create one for this port
                 # print "NEW METER CREATED FOR :", out_port
                 bands=[]
                 #set starting bit rate of meter
                 dropband = parser.OFPMeterBandDrop(rate=1000000, burst_size=0)
                 bands.append(dropband)
                 #Delete meter first, it might already exist
                 request = parser.OFPMeterMod(datapath=datapath,command=ofproto.OFPMC_DELETE,flags=ofproto.OFPMF_KBPS,meter_id=out_port,bands=bands)
                 datapath.send_msg(request)
                 request = parser.OFPMeterMod(datapath=datapath,command=ofproto.OFPMC_ADD, flags=ofproto.OFPMF_KBPS,meter_id=out_port,bands=bands)
                 datapath.send_msg(request)
                 
		 port_to_meter[out_port]=out_port




        #Standard smart switch continues
        actions = [parser.OFPActionOutput(out_port)]

        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD and dst != "ff:ff:ff:ff:ff:ff":
	    match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            # verify if we have a valid buffer_id, if yes avoid to send both
            # flow_mod & packet_out
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 2, match, actions, msg.buffer_id, meters=[out_port], timeout=60)
                return
            else:
                self.add_flow(datapath, 2, match, actions, meters=[out_port], timeout=60)
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)


    #handle meter stats replies
    @set_ev_cls(ofp_event.EventOFPMeterStatsReply, MAIN_DISPATCHER)
    def meter_stats_reply_handler(self, ev):
	'''Event call back from a stats request'''
        def _unpack(meterStats):
            unpacked = {}
            for statsEntry in meterStats:
                meter = statsEntry.meter_id
                first_band = statsEntry.band_stats[0]
                assert len(statsEntry.band_stats) == 1 # this assertion ensures that the code is not used in more complex context than a single band without modification
		#assert statsEntry.flow_count < 2       # this assertion enures that the code is not used in more complex context than a single flow per meter without modification
                unpacked[meter] = TimedMeterRecord (statsEntry.packet_in_count, statsEntry.byte_in_count, first_band.packet_band_count, first_band.byte_band_count, statsEntry.duration_sec, statsEntry.duration_nsec )
            return unpacked

        meterStats = _unpack(ev.msg.body)


        # on first entry for a switch just save the stats, initiliase the max counters to zero and exit
        if ev.msg.datapath.id not in self.METER_CURRENT:
            # self.logger.info("meter_stats_reply_handler - first entry for switch %d", ev.msg.datapath.id )
            self.METER_CURRENT[ev.msg.datapath.id] = _unpack(ev.msg.body)
            self.METER_MAX[ev.msg.datapath.id] = {}
            self.METER_RATE[ev.msg.datapath.id] = {}
            maxStats = self.METER_MAX[ev.msg.datapath.id]
            for statsEntry in ev.msg.body:
                maxStats[statsEntry.meter_id] = MeterRecord(0,0,0,0)

        else: # we have a previous stats record so it is now possible to calculate the delta
            # self.logger.info("port_stats_reply_handler - repeat entry for switch %d", ev.msg.datapath.id )
            oldStats = self.METER_CURRENT[ev.msg.datapath.id]
            newStats = _unpack(ev.msg.body)
            self.METER_CURRENT[ev.msg.datapath.id] = newStats # save away this dataset for the next time around...
            maxStats = self.METER_MAX[ev.msg.datapath.id]     # always exists since it is initialised to zero on first stats report
            rate     = self.METER_RATE[ev.msg.datapath.id]

            for meter in newStats:
            # now check if there are any new meters in this report - in which case we cannot do anything other than initilaise the max values to zero
                if meter not in oldStats:
                    maxStats[meter] = MeterRecord(0,0,0,0)
                    rate[meter]     = MeterRecord(0,0,0,0)
                else:
                    delta_time = self.diff_time(oldStats[meter].duration_sec, oldStats[meter].duration_nsec, newStats[meter].duration_sec, newStats[meter].duration_nsec)
                    # print "delta time: %f\n" % delta_time
                    if (delta_time<0):
                        print "diff_time failure(flow stats)?"
                        pprint(ev.msg.body)
                    else:
    
                        rate[meter] = MeterRecord ((newStats[meter].packet_in_count - oldStats[meter].packet_in_count) / delta_time,
                                                        (newStats[meter].byte_in_count - oldStats[meter].byte_in_count) / delta_time,
                                                        (newStats[meter].packet_band_count - oldStats[meter].packet_band_count) / delta_time,
                                                        (newStats[meter].byte_band_count - oldStats[meter].byte_band_count) / delta_time)
    

                        maxStats[meter] = MeterRecord ( max(maxStats[meter].packet_in_count,rate[meter].packet_in_count),
                                                      max(maxStats[meter].byte_in_count,rate[meter].byte_in_count),
                                                      max(maxStats[meter].packet_band_count,rate[meter].packet_band_count),
                                                      max(maxStats[meter].byte_band_count,rate[meter].byte_band_count) )



    #handle flow stats replies
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):

        def _unpack(flowStats):
            unpacked = {}
            for statsEntry in flowStats:
                cookie = statsEntry.cookie
                if cookie != 0: # we only will collect statistics which we have marked with a cookie...
                    unpacked[cookie] = TimedFlowStatRecord (statsEntry.packet_count, statsEntry.byte_count, statsEntry.match, statsEntry.table_id, statsEntry.priority, statsEntry.duration_sec, statsEntry.duration_nsec )
            return unpacked

        flowStats = _unpack(ev.msg.body)

        # *** Unfinished stub - the returned flow stats should probably be saved in some global/persistent store.
        # *** Unfinished because the HP switches were observed not to return byte conters for any of the flows.


    #handle port stats replies
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
	'''Event: reply of throughput on a datapath. Saved for later so it can be requested and analysed'''
	#TODO change bytes to Kbits. Before change make sure everything that uses it is ready to use kbits not bytes	
        def _unpack(portStats):
            unpacked = {}
            for statsEntry in portStats:
                port = statsEntry.port_no
                if port != 4294967294: # this magic number is the 'local'port, which is not real.... 
		    #WARNING. Change here from bytes to kbits. TODO change names to say tx_kbits
                    unpacked[port] = TimedPortStatRecord (statsEntry.tx_packets, statsEntry.rx_packets, (statsEntry.tx_bytes*8)/1000, (statsEntry.rx_bytes*8)/1000, statsEntry.duration_sec, statsEntry.duration_nsec )
            return unpacked

	maxStats_debug={}
	rate_debug={}

        # on first entry for a switch just save the stats, initiliase the max counters to zero and exit
        if ev.msg.datapath.id not in self.PORT_CURRENT:
            self.PORT_CURRENT[ev.msg.datapath.id] = _unpack(ev.msg.body)
            self.PORT_MAX[ev.msg.datapath.id] = {}
            self.PORT_RATE[ev.msg.datapath.id] = {}
            maxStats = self.PORT_MAX[ev.msg.datapath.id]
            for statsEntry in ev.msg.body:
                if statsEntry.port_no != 4294967294: # this magic number is the 'local'port, which is not real....
                    maxStats[statsEntry.port_no] = PortStatRecord(0,0,0,0)

        else: # we have a previous stats record so it is now possible to calculate the delta
            oldStats = self.PORT_CURRENT[ev.msg.datapath.id]
            newStats = _unpack(ev.msg.body)
            self.PORT_CURRENT[ev.msg.datapath.id] = newStats # save away this dataset for the next time around...
            maxStats = self.PORT_MAX[ev.msg.datapath.id]     # always exists since it is initialised to zero on first stats report
            rate     = self.PORT_RATE[ev.msg.datapath.id]
	
            for port in newStats:
            # now check if there are any new ports in this report - in which case we cannot do anything other than initilaise the max values to zero
                if port not in oldStats:
                    maxStats[port] = PortStatRecord(0,0,0,0)
                    rate[port]     = PortStatRecord(0,0,0,0)

		    maxStats_debug[port] = [0,0]
                    rate_debug[port]     = [0,0]
                else:
                    delta_time = self.diff_time(oldStats[port].duration_sec, oldStats[port].duration_nsec, newStats[port].duration_sec, newStats[port].duration_nsec)
                    # print "delta time: %f\n" % delta_time
                    if (delta_time<0):
                        print "diff_time failure(port stats)?"
                        pprint(ev.msg.body)
                    else:
   			#TODO change bytes to kbits 
                        rate[port] = PortStatRecord ((newStats[port].tx_packets - oldStats[port].tx_packets) / delta_time,
                                                        (newStats[port].rx_packets - oldStats[port].rx_packets) / delta_time,
                                                        (newStats[port].tx_bytes - oldStats[port].tx_bytes) / delta_time,
                                                        (newStats[port].rx_bytes - oldStats[port].rx_bytes) / delta_time)


                        maxStats[port] = PortStatRecord ( max(maxStats[port].tx_packets,rate[port].tx_packets),
                                                      max(maxStats[port].rx_packets,rate[port].rx_packets),
                                                      max(maxStats[port].tx_bytes,rate[port].tx_bytes),
                                                      max(maxStats[port].rx_bytes,rate[port].rx_bytes) )

						
			rate_debug[port] = [format((((newStats[port].tx_bytes - oldStats[port].tx_bytes) / delta_time)),'.2f'),
                                                       format((((newStats[port].rx_bytes - oldStats[port].rx_bytes) / delta_time)),'.2f')]

                        maxStats_debug[port] = [format((max(maxStats[port].tx_bytes,rate[port].tx_bytes)),'.2f'),
								format((max(maxStats[port].rx_bytes,rate[port].rx_bytes)),'.2f')]


	    # visualise the stats in the server side
            print self._dp_name(ev.msg.datapath.id)
	    print "Port - current"
            pprint(rate_debug)
            print "Port - maximum"
            pprint(maxStats_debug)





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
