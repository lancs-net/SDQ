#!/bin/bash
for i in {201..223}
do   
   nova reboot h$i
done
for i in {234..235}
do
   nova reboot s$i
done
