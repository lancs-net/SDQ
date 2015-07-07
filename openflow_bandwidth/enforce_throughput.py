#!/usr/bin/python
# coding: utf-8

import json
import pyjsonrpc
import sys, getopt

def __init__(self):
	http_client = None


def main(argv):

	http_client = pyjsonrpc.HttpClient(url = "http://localhost:4000/jsonrpc")

	if http_client is None:
		print 'Could not connect to JSON-RPC server'
		sys.exit(2)

	usage = "usage: python enforce_throughput.py <switch_id> <port_no> <speed B/s>"

	try:
		opts, args = getopt.getopt(argv,"h",[])
	except getopt.GetoptError:
		print usage
		sys.exit()

	switch = args[0]
	port = args[1]
	speed = args[2]

	http_client.notify("enforce_port_outbound", switch, port, speed)

if __name__ == '__main__':
	main(sys.argv[1:])



