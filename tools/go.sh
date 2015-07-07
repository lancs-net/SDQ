#!/bin/bash
target=192.168.1.224
interval=30
total=600
samples=$(($total/$interval))
i=1
unset IFS # restore IFS to default
for i in $(seq "$samples"); do
	bandwidth=$(python -S -c "import random; print random.randrange(2000000,4000000)")
	tput setaf 2; echo "$i) generating background traffic at $bandwidth/bps"; tput sgr0
	timeout 30 wget -qO- http://192.168.1.234/sample.bin --limit-rate=$bandwidth &> /dev/null
done
