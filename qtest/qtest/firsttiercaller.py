## WHAT: This is the first tier of the 2tier experiment. It defines how resource (with dynamic availability) on a shared link
##is divided between multiple 'households' based on the aggregated utility of each
## household, and the (dynamic) available link capcity of each household.
##How to use##
##Command: python firsttiercaller.py [total bandwidth] [number of households] [household_id,available bw]
##Example: python firsttiercaller.py 6000 [(A,4000) (B,600) (C,7000) (D,323) (E,8574)]
##RETURNS: [hh1_allocation,hh2_allocation etc.]
##EXAMPLE: [1565, 296, 2235, 270, 1630]

from sympy import *
import sympy
import numpy
import itertools
import sys
import time
import math
from threading import Timer
import os
import random
from subprocess import PIPE, Popen
import matplotlib.pyplot as plt

class FirstTier(object):

    clientfeature={'360':';360;10000,10000\n','720':';720;10000,10000\n','1080':';1080;10000,10000\n'}
    x=Symbol('x')
    representations={}
    representations['360']=[100,200,400,600,800,1000]
    representations['720']=[100,200,400,600,800,1000,1500,2000]
    representations['1080']=[100,200,600,1000,2000,4000,6000,8000]
    hh={}
    hh['A']=[360,720,1080,720]
    hh['B']=[720,720]
    hh['C']=[360,720,1080,720,360]
    hh['D']=[720,1080,1080]
    hh['E']=[360,720]
    hhuf={}
    hhuf['A']=-5.5 * (x**(-0.5558)) + 1.014
    hhuf['B']=-0.8461 * (x**(-0.2064)) + 1.131
    hhuf['C']=-5.846 * (x**(-0.5552)) + 1.014
    hhuf['D']=-12.99 * (x**(-0.6978)) + 1.002
    hhuf['E']=-1.06 * (x**(-0.3026)) + 1.074
    adjustedhhuf={}

    def call(self, totalbw, households):
        self.linkcap={}
	for household in households:
            self.linkcap[household[0]] = household[1]
        self.adjusthhuf(self.linkcap)
        share=self.getoptimalpoints(totalbw)
        return share

    def adjusthhuf(self, linkcap):
        cap=1
        for h in self.hhuf:
            cap=min(1,self.hhuf[h].evalf(subs={self.x:linkcap[h]}))
            self.adjustedhhuf[h]=self.hhuf[h]/(cap)

    def getoptimalpoints(self, totalbw):
        ufset={}
        y=0
        functionset=[]
        variableset=[]
        startingpointset=[]
        flag=0
	linkcaplist = []
	for h in ['A','B','C','D','E']: #Making sure they are in the correct order to match nsolve results
            linkcaplist.append(self.linkcap[h])
	    ufset[h]=self.adjustedhhuf[h].subs(self.x,Symbol('x'+str(h)))
            variableset.append(Symbol('x'+str(h)))
            startingpointset.append(int(totalbw)/len(self.hh))
            if flag==1:
                functionset.append(left-ufset[h])
                left=ufset[h]
                y+=Symbol('x'+str(h))
            else:
                left=ufset[h]
                flag=1
                y+=Symbol('x'+str(h))
        z=y-int(totalbw)
        functionset.append(z)
        result=nsolve(functionset, variableset,startingpointset)
        toreturn=[]
	i = 0
        for r in result:
	    rmin=min(int(r), int(linkcaplist[i]))
            toreturn.append(int(rmin))
	    i += 1
        return toreturn

    def randomlinkcap():
        return {'A':random.randint(3000,20000),'B':random.randint(3000,20000),'C':random.randint(3000,20000),'D':random.randint(3000,20000),'E':random.randint(3000,20000)}

    def randomtotal():
        ##return random.randint(20000,50000)
        return random.randint(10000,30000)

    def weighted_choice(self, weights):
        totals = []
        running_total = 0
        for w in weights:
            running_total += w
            totals.append(running_total)
        rnd = random.random() * running_total
        for i, total in enumerate(totals):
            if rnd < total:
                return i

    def writefile(share,h,j,ccount):
        # global clientfeature
        # global hh
        x=0
        #weightlist=[[1,5,2,2,2,2],[1,5,0,0,0,0],[1,0,2,2,2,2],[10,1,0,0,0,0]]
        weightlist=[[200*(x+4)/4,100*(x+4)/4,10,10,10,10]]
        txt=""
        txt+="0;totalbw;"+str(share[0][j])+","+str(share[0][j])+"\n"
        #txt+="10;start;stream1;720;3000,5000\n"
        #txt+="20;start;stream2;1080;2000,8000\n"
        #txt+="30;start;stream3;360;500,2000\n"
        #txt+="40;start;stream4;720;1000,3000\n"
        #txttoappend=[";720;1000,3000\n",";720;3000,5000\n",";1080;2000,8000\n",";360;500,2000\n"]
        z=1
        cc={}
        for c in self.hh[h]:
            txt+=str(z*10)+";start;stream"+str(z+ccount)+self.clientfeature[str(c)]
            cc[str(z+j)]=c
            z+=1
        #while z<=x:
            #streamid="stream"+str(z+4)
            #txt+=str(40+z*10)+";start;"+streamid+txttoappend[z%4]
            #weightlist[0].append(20)
            #z+=1
        i=z
        while i<(60+z-1):
            if i%6==0:
                txt+=str(10*i)+";totalbw;"+str(share[i/6][j])+","+str(share[i/6][j])+"\n"
            else:
                y=weighted_choice([1]*len(hh[h]))+1
                txt+=str(i*10)+";start;stream"+str(y+ccount)+clientfeature[str(cc[str(y+j)])]
            i+=1
        txt+=str((60+z)*10)+";finish"
        #print txt
        fn="test"+str(h)+".txt"
        fo=open(fn,"w+")
        fo.close()
        with open(fn, "a") as myfile:
            myfile.write(txt)
        myfile.close()
