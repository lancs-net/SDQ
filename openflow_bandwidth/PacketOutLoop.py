from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
import time
from ryu.lib.packet import ethernet

class PacketOutLoop():
    def __init__(self):
        self._running = True

    def terminate(self):
        self._running = False

    #input switch to send to
    def packet_out(self, datapath):
        ofp = datapath.ofproto
        ofp_parser = datapath.ofproto_parser
        #req = ofp_parser.OFPPortStatsRequest(datapath, 0, ofp.OFPP_ANY)
        actions = [ofp_parser.OFPActionOutput(ofp.OFPP_FLOOD)]
        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(dst='ff:ff:ff:ff:ff:ff', src='00:00:00:00:00:00', ethertype=2048))
        pkt.add_protocol('j'*1380)
        pkt.serialize()
    #    print pkt.data
        out = ofp_parser.OFPPacketOut(datapath=datapath, buffer_id=ofp.OFP_NO_BUFFER,
                                   	in_port=ofp.OFPP_CONTROLLER, actions=actions, data=pkt.data)
        datapath.send_msg(out)

    #input time for every request and list of switches to request to
    def run(self, pollTime,datapathdict):
        time.sleep(10)
        t=time.time()
        counter =0
        while True:

            for the_key, datapath in datapathdict.iteritems():
                self.packet_out(datapath)
                counter=counter+1
                print counter
            #    print "packet_out to:" + str(datapath.id)
            if (t + 10) < time.time():
                print counter
                time.sleep(pollTime)
                t=time.time()
                counter=0
