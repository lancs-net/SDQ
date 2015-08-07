Respository containing all the tools used for the QoE meets OpenFlow work. Also explains how far we got with experimentation.

Topology & Experiment
--------

<img src=qtest/2tierdigram.png width=600  />

Mu has a diagram of the topology (above), but here is a brief description of it:

There are 5 households, each consisting of between 3 and 6 clients. The clients in a household are connected together by a single OpenFlow switch. These households are the second tier (and served by the ```resourceallocationcaller.py``` functions) This OpenFlow switch is also the gateway out of the local network. These switches are then connected to an arregation switch, which forms the first tier (represented in the ```firsttiercaller.py```). This switch is then connected to another switch, which has directly attached to it the background server and the foreground server.

In reality, each of these hosts and servers are virtual machines sat on the OpenStack testbed. In order to guarantee which port they exit from, they are each connected to a virtual switch with OpenStack. This switch tags them with a specific VLAN. When the traffic exits the OpenStack deployment towards the first physical switch, the VLAN tagging is used to determine which physical port the packets emerged from. 

These physical ports are then connected to a second physical switch. This switch is concertinaed into a number of virtual switches, each acting as a separate entity. The wiring is done to replicate the above topology.

qTest
-----
This is glues together the various elements. Confusingly, it includes both my integration code *and* Mu's QoE code, and can be found in the ```\qtest``` folder. The code to run is the ```\qtest\integration.py``` script. This will do the talking between the OpenFlow controller and Mu's QoE code. Try ```python integration.py -h``` to check out the parameters you can pass. To install the required packages, run ```pip install -r requirements.txt```; that should install everything. 

I've also included the config file used in the experiments (```\qtest\config.json```). It's basically a tree structure, describing the nodes (hosts, servers and switches) and the connections between them (the edges). The config is fairly self explanatory, but is rather tedious to build. 

I've also documented the ```\qtest\integration.py``` code pretty well, so it should be relatively easy to modify it (which you will undoubtedly have to). There is some hardcoded variables at the start (the household mappings, for example). These might need to be changed if you scale things up or name things differently.

OpenFlow Bandwidth
------------------

The modified Ryu controller used in our experiments can be found in the ```/openflow_bandwidth``` folder. It is almost identical to the version originally developed by Jamie and Lyndon, and further developed by Nic. The latest version can be found [here](https://github.com/hdb3/openflow_bandwidth). It might be worth combining the changes in a pull request so that we can have a definitive version. I would imagine we will want to expand the interface soon anyway. It worth noting that documentation in Nic's version is old (*hint hint*), and doesn't reflect what is actually implemented.

The version I used has minor changes to the parameters in the *enforce_services* RPC call. It now accepts a list of destinations, rather than single item. This enables the required higher tier functionality, whereby a flow can be limited from the server to a group of destinations (belonging to a single household). This list produces a number of rules that point to the same shared meter.

Scootplayer
-----------
An unmodified version of Scootplayer was used. This can be found [here](https://github.com/broadbent/scootplayer). Ask Mu for the dataset. I'll see if we still have the various MPDs, but they are easy to create and modify.

Tools
-----

There is a number of additional scripts I used in the experimentation. For example, the ```/tools/reboot.sh``` script is used to reboot all the nodes via the nova interface. It could be used again (assuming we naming the hosts and servers the same). This naming shouldn't be an issue if we use the ```/tools/specmuall.py``` script in conjunction with Nic's [ministack tools](https://github.com/hdb3/ministack). This will recreate the exact same configuration of VMs and networks that we used in the experiment. The only think missing is the configuration of the HP switches and the VLAN trickery used to ensure VMs appear on particular ports on each of the *virtual* switches present on the physical HP switch.

There is two bash scripts used during the experiments. These were run simultaneously on each of the VMs using [cluster SSH](http://bit.ly/1dKcMNz). The ```/tools/pre.sh``` script was run before experiments started and basically ensured that there was connectivity between each of the hosts and the server. It prints a nice green message if there is, a big red ```[FAIL]``` if not. This helped debug connectivity issued before even before we started. The ```/tools/go.sh``` was run in a similar manner ()using cluster SSH) to start the tests. The one included is for the background traffic generation using *wget*; evidently, it will different on the hosts playing video (I forgot to retrieve that one, but it basically started Scootplayer pointing at the server and playing the desired version of Big Buck Bunny). I just called it the same so that you could simply hit ```$ ./go.sh``` and start the damned thing!

An alternative to cssh was created because it had a tendency to close sessions or fail to open some. The experiments can be ran using [cluster command](https://github.com/lyndon160/cluster_command) simple RPC program which contains scripts specific to this experiment. The server is already installed and running on the clients.


Samples
-------

I included  a sample output from the integration code in ```/samples/debug.log```. This is basically so that you know what the output will be like. This is also what Mu needs to plot. I also included the ```/samples/history.txt``` which is a dump of the bash history. It should give you an idea of what I was doing to run the experiment (and test things earlier on).

Current Limitations
-------------------
At the moment, the API does not allow the mixing of flow-based and port-based monitoring. This is because a packet will always match on the flow-based rule before the port-based rule (it has more detail, and is thus more specific; OpenFlow will always match on that first). It would be better if the flow-rule then matched on a port-rule, thus combining the two. -- This is going to be fixed by creating two tables, one for flow based matches and one for port based matches. The per flow matches will include an instruction to go to a per port matches table, this combines the two and ensures that both meters are incremented. --

~~There also appears to be an arbitary conversion factor between some of the calls. In the current implementation, I tuned this with some trial and error, so they may not be exactly right. This needs some time to confirm the responses from the API (and the underlying OpenFlow) are consistent. For example, the measurement from the switch does not seem to be the in the same format as the rate-limiting threshold. However, I did confirm that the results (at least those derviced from *wget* and *iperf*) where what I expected. Further experiments need to be done to confirm the result from Scootplayer are what we expect (and no, #inb4scootplayerisbroken).~~

All stats relating to bandwidth should’ve been changed to kilobits. When installing meters, API calls and what is represented in the meter tables as well as in practice (from *wget* and *iperf*), appear to be consistent.

“ERROR: Impossible to fine optimial points.” exception when trying to calculate bandwidth split in the resourceallocationcaller.py. This is most likely due to incorrect input values in the config/hardcoded variables. 



