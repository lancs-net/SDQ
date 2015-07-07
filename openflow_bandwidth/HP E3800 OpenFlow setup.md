<h1>HP E3800 OpenFlow setup<h1>

<h2> Current set up </h2>

<b><br>SW1 - AccessSW2</b>
<br>Software revision  : KA.15.15.0006
<br>ROM Version        : KA.15.09 
<br>Configured OpenFlow instance - ryu
<b><br>SW2 - HP-3800-48G-PoEP-4XG</b>
<br>Software revision  : KA.15.15.0006 
<br>ROM Version        : KA.15.09
<br>Configured OpenFlow instance - ryu
<b><br>SW3 - AccessSW4</b> 
<br>Software revision  : KA.15.15.0006
<br>ROM Version        : KA.15.09 
<br>Configured OpenFlow instance - ryu

<h2> Set up </h2>

Modified from the HP OpenFlow docs (http://h20628.www2.hp.com/km-ext/kmcsdirect/emr_na-c03512348-4.pdf)

Configure VLANs, assign ports and IP address
<br>Management vlan - needs a network address which the controller IP needs to be within
<br>Member vlan - no ip address

Create openflow instance

`openflow instance <instance_name>`

Assign member vlan to instance

`openflow instance <instance_name> member vlan <vlan_id>`

Set mode - active

`openflow instance <instance_name> mode active`

Set controller listen port - 6633

`openflow instance <instance_name> listen-port 6633`

Set interruption mode 

`openflow instance connection-interruption-mode { fail-secure | fail-standalone }`

Create controller, set IP, set interface (vlan)

`openflow controller <controller_id> ip <controller_ip> controller-interface vlan <management_vlan_id>`

Assign controller to openflow instance

`openflow instance <instance_name> controller-id <controller_id>`

Set openflow version - 1.3

`openflow instance <instance_name> version 1.3 only`

Enable

```
openflow enable
openflow instance ryu enable
```



