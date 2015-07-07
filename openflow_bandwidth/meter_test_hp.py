from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
import threading

#
class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
	self.port_to_meter = {}

    #Called when connected to new switch
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # install table-miss flow entry to make switch forward new packets to controller
        # IMPORTANT FOR HP SWITCH, priority must be higher than 1
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 1, match, actions, meter=None, timeout=0)

        print datapath.id
    
        #requesting meter features
	self.send_meter_features_stats_request(datapath)


        #print out meter stats
        self.printit(datapath)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, meter=None, timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        #Meter instruction here
	print "The meter is :",meter
        if meter != None:
	    print "Sending flow mod with meter instruction, meter :", meter
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,actions),parser.OFPInstructionMeter(meter)]
        else:
	    print "Not sending instruction"
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,priority=priority, match=match,instructions=inst, hard_timeout=timeout, idle_timeout=timeout, table_id=100)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,match=match, instructions=inst, hard_timeout=timeout, idle_timeout=timeout, table_id=100)
        datapath.send_msg(mod)

    #gets the meter stats from switch periodically
    def printit(self,dd):
        threading.Timer(5.0, self.printit,[dd]).start()
        self.send_meter_stats_request(dd)

    
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        # If you hit this you might want to increase
        # the "miss_send_length" of your switch
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.info("packet truncated: only %s of %s bytes",
                              ev.msg.msg_len, ev.msg.total_len)

        msg = ev.msg
        reason = msg.reason
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']


        pkt = packet.Packet(msg.data)
        eth = None
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        self.logger.info("dpid:%s src:%s dst:%s in_port:%s buffer_id:%d", dpid, src, dst, in_port, msg.buffer_id)

        # learn a mac address to avoid FLOOD next time.
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]




	#Create new meters
	#Check for flood, dont want to add meter for flood
	if out_port != ofproto.OFPP_FLOOD:	
             print "NOT A FLOOD PACKET"
	     if out_port in self.port_to_meter:
                 #if the meter already exists set instruction to use	
                 print "Meter already exists for this port"
	     else:
	         #This controller not added meter before, need to create one for this port
	         print "NEW METER CREATED FOR :", out_port 
	         bands=[]
		 #set starting bit rate of meter
                 dropband = parser.OFPMeterBandDrop(rate=10000, burst_size=0)
                 bands.append(dropband)
	         #Delete meter first, it might already exist
	         request = parser.OFPMeterMod(datapath=datapath,command=ofproto.OFPMC_DELETE,flags=ofproto.OFPMF_KBPS,meter_id=out_port,bands=bands)
	         datapath.send_msg(request)
                 request = parser.OFPMeterMod(datapath=datapath,command=ofproto.OFPMC_ADD, flags=ofproto.OFPMF_KBPS,meter_id=out_port,bands=bands)
	         datapath.send_msg(request)	    
	         self.port_to_meter[out_port]=out_port




        # install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            # verify if we have a valid buffer_id, if yes avoid to send both
            # flow_mod & packet_out
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
		print "Valid buffer"
                self.add_flow(datapath, 2, match, actions, msg.buffer_id, meter=out_port, timeout=60)
                return
            else:
                self.add_flow(datapath, 2, match, actions, meter=out_port, timeout=60)
        
	data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)




    #Ask switch about its meter features
    def send_meter_features_stats_request(self, datapath):
        ofp_parser = datapath.ofproto_parser

        req = ofp_parser.OFPMeterFeaturesStatsRequest(datapath, 0)
        datapath.send_msg(req)

    #Response from switch telling us if switch works with meters
    @set_ev_cls(ofp_event.EventOFPMeterFeaturesStatsReply, MAIN_DISPATCHER)
    def meter_features_stats_reply_handler(self, ev):
        features = []
        for stat in ev.msg.body:
            features.append('max_meter=%d band_types=0x%08x '
                            'capabilities=0x%08x max_bands=%d '
                            'max_color=%d' %
                            (stat.max_meter, stat.band_types,
                             stat.capabilities, stat.max_bands,
                             stat.max_color))
        print('MeterFeaturesStats: ', features)


    #Gets response from switch about the meter stats
    @set_ev_cls(ofp_event.EventOFPMeterStatsReply, MAIN_DISPATCHER)
    def meter_stats_reply_handler(self, ev):
        meters = []
        for stat in ev.msg.body:
            meters.append('meter_id=0x%08x len=%d flow_count=%d '
                          'packet_in_count=%d byte_in_count=%d '
                          'duration_sec=%d duration_nsec=%d '
                          'band_stats=%s' %
                          (stat.meter_id, stat.len, stat.flow_count,
                           stat.packet_in_count, stat.byte_in_count,
                           stat.duration_sec, stat.duration_nsec,
                           stat.band_stats))
        print('MeterStats:', meters)


    def send_meter_stats_request(self, datapath):
        ofp = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        req = ofp_parser.OFPMeterStatsRequest(datapath, 0, ofp.OFPM_ALL)
        datapath.send_msg(req)
