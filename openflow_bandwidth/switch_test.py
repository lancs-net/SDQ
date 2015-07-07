from mininet.topo import Topo
class MyTopo( Topo ):
     def __init__( self ):
          # Initialize topology
          Topo.__init__( self )
          # Add hosts and switches
          switch1 = self.addSwitch( 's1' )
          switch2 = self.addSwitch( 's2' )
          # Add links
          self.addLink(switch2, switch1)
          self.addLink(switch2, switch1)
          self.addLink(switch2, switch1)

topos = { 'mytopo': ( lambda: MyTopo() ) }