OpenFlow Bandwidth
==================
A modification of a the ryu (http://osrg.github.io/ryu/) simple learning switch controller app to report and enforce bandwidth.
Reporting by monotring the maximum passive throughput and enforcing using OpenFlow meters, both on a per port and per flow basis.
The controller runs a JSON-RPC server for interfacing. Procedures shown below. 

## Compatability
<b> HP OpenFlow 1.3 switches </b>
<br>Bandwidth reporting - Confirmed
<br>Bandwidth enforcing - Confirmed

<b> Open vSwitch </b>
<br>Bandwidth reporting - Confirmed
<br>Bandwidht enforcing - Failed

## Quick start
Install Ryu - simple pip installation has requirements

```
% git clone git://github.com/osrg/ryu.git 
% cd ryu  
% sudo pip install -r tools/pip-requires
% python ./setup.py install
```

Pull

`% git pull http://github.com/birrdy/openflow_bandwidth`

Run bandwidth_control_simple_switch_13.py as a Ryu app

`% ryu-manager bandwidth_control_simple_switch_13.py`

By default the RPC server is running on `http://localhost:4000/jsonrpc`

## JSON RPC interface
The JSON-RPC server is a HTTP server.
The following examples would be used to develop a python application using the python-jspnrpc library (https://pypi.python.org/pypi/python-jsonrpc), but procedures can be called using any JSON-RPC method. (I think)

Install 

`% pip install python-jsonrpc`

Import

`import pyjsonrpc`

Connection

`http_client = pyjsonrpc.HttpClient(url = "http://localhost:4000/jsonrpc")`

Procedure calling. 

```
# Direct call
result = http_client.call("<procedure>", arg1, arg2)

# Use the *method* name as *attribute* name
result = http_client.procedure(arg1, arg2)

# Notifcations send messages to the serevr without reply
http_client.notify("<procedure>", arg1, arg2)
```

<h3> Procedures </h3>

<b> report_port </b>
<br>Reports the maximum seen throughput of a specific port on a specific switch.
<br>Params: `[<switch_id>, <port_no>]` 
<br>Result: `[upload B/s, download B/s]`

```
--> {"jsonrpc": "2.0", "method": "report_port", "params": [<switch_id>, <port_no>], "id": 1}
<-- {"jsonrpc": "2.0", "result": [<upload B/s>, <download B/s>], "id": 1}
```

<b> report_flow -  Not implemented </b>
<br>Reports the throughout of a specific flow on a specific switch.
<br>Params: `[<switch_id>, <flow_id>]`
<br>Result: `<B/s>` 

<b> report_switch_ports </b>
<br>Reports the throughput of all ports on a specific switch.
<br>Params: `<switch_id>`
<br>Result: JSON formatted port list
```
{
  <port_no>:[<upload B/s>, <download B/s>],
  ...
  <port_no>:[<upload B/s>, <download B/s>]
}
```

<b> report_switch_flows - Not implemented </b>
<br>Reports the througput of all flows on a specific switch.
<br>Params: `<switch_id>`
<br>Result: JSON formatted flow list
```
{
  <flow_id>:<B/s>,
  ...
  <flow_id>:<B/s>
}
```

<b> report_all_ports </b>
<br>Report the throughput of all ports on all switches under the control of the controller.
<br>Result: JSON formatted switch & port list
```
{
  <switch_id>:{
    <port_no>:[<upload B/s>, download B/s],
    ...
    <port_no>:[<upload B/s>, download B/s]
  },
  ...
  <switch_id>:{
    <port_no>:[<upload B/s>, <download B/s>],
    ...
    <port_no>:[<upload B/s>, <download B/s>]
  }
}
```

<b> report_all_flows </b>
<br>Report the throughput of all flows on all switches under the control of the controller.
<br>Result: JSON formatted switch & flow list

```
{
  <switch_id>:{
    <flow_id>:<B/s>,
    ...
    <flow_id>:<B/s>
  },
  ...
  <switch_id>:{
    <flow_id>:<B/s>,
    ...
    <flow_id>:<B/s>
  }
}
```

<b> reset_port </b> - Notification
<br>Resets the throughput of a specific port. To be recalculated.
<br>Params: `[<switch_id>, <port_no>]`

<b> reset_flow </b> - Notification - <b> Not implemented </b>
<br>Resets the throughput of a specific flow. To be recalculated.
<br>Params: `[<switch_id>, <flow_id>]`

<b> reset_switch_ports </b> - Notification
<br>Resets all recorder throughputs of all ports on a specific switch.
<br>Params: `<switch_id>`

<b> reset_switch_flows </b> - Notification
<br>Resets all recorder throughputs of all ports on a specific switch.
<br>Params: `<switch_id>`

<b> reset_all_ports </b> - Notification
<br>Resets all recorder throughputs of all ports on all swtiches under the control of the controller.

<b> reset_all_flows </b> - Notification
<br>Resets all recorder throughputs of all flows on all swtiches under the control of the controller.

<b> Enforce procedures in progress </b>

<b> enforce_port_outbound </b> - Notification
<br>Enforces an outbound bandwidth restriction on a specific port. Any previous enforcements will be replaced.
<br>Params: `[<switch_id>, <port_no>, <speed B/s>]`

<b> enforce_port_inbound </b> - Notification
<br>Enforces an inbound bandwidth restriction on a specific port. Any previous enforcements will be replaced.
<br>Params: `[<switch_id>, <port_no>, <speed B/s>]`

<b> enforce_flow </b> - Notification - <b> Not implemented </b>
<br>Enforces a bandwidth restricion on an existing flow. Any previous enforcements will be replaced.
<br>Params:`[<switch_id>, <flow_id>]`

<b> enfore_service </b>
<br>Enforces a bandwith restricting on a service donated by the source and destination address pair.
<br>Params: `[<switch_id>, <src_addr>, <dst_addr>, <speed B/s>]`

<h2>CLI - In progress</h2>
<b> report_throughput.py </b> - Only port based for now

Show everything

`% python report_througput.py -a`

Show all ports on a switch

`% python report_throughput.py -s <switch_id>`

Show specifc port on a switch

`% python report_throughput.py -s <switch_id> -p <port_no>`

<b> enforce_throughput_port.py </b>

`% python enforce_throughput_port.py <switch_id> <port_no> <speed B/s>`

<b> enforce_throughput_service.py </b>

`% python enforce_throughput_service.py <switch_id> <src_ip> <dst_ip> <speed B/s>`




