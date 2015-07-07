#!/bin/bash
for i in {234..235}
do
   ping 192.168.1.$i -c 2 > /dev/null
   rc=$?
done
if [[ $rc -eq 0 ]] ; then
	tput setaf 2; echo "[OK]"; tput sgr0
else
	tput setaf 1; echo "[FAIL]"; tput sgr0
fi

