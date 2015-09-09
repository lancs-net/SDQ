##Copyright (C) 2015 Mu Mu - All Rights Reserved
##You may use, distribute and modify this code under the
##terms of the XYZ license, which unfortunately won't be
##written for another century.
##You should have received a copy of the XYZ license with
##this file. If not, please write to mumu.mm@gmail.com

##How to use##
##Command: python resourceallocationcaller.py [total bandwidth] [number of clients] [client1id,available bw,resolution client2id,available bw,resolution ...]
##Example: python resourceallocationcaller.py 4000 3 asd,8000,720 xid,4000,1080 zop,1600,360 testtag=testtag
##Prerequisites:
###The network management function must update the clientid.txt file
###in the ./testtag/si sub-directory as the python script as soon as a new stream
###is detected OR a change of stream representation is made/detected.
###
###The format of the testtag/si/clientid.txt file is:
###timestamp,bitrate
###timestamp,bitrate
###...
### Output: results:{streamid: [vq_optimized_allocation, si_optimized_allocation, ct_optimized_allocation, al_optimized_allocation], 'xid': [2000, 2000, 2000, 2000], 'asd': [1000, 1000, 1000, 1000]}

from sympy import *
import sympy
import numpy
import itertools
import sys
import time
import math
import logging

#def main():
    #x1 = Symbol('x1')
    #x2 = Symbol('x2')
    #x3 = Symbol('x3')
    #uf360 = -17.53 * (x1**(-1.048)) + 0.9912
    #uf720 = -4.85 * (x2**(-0.647)) + 1.011
    #uf1080 = -3.035 * (x3**(-0.5061)) + 1.022
    #f1=uf360-uf720
    #f2=uf720-uf1080
    #f3=x1+x2+x3-totalbw
    #result=nsolve((f1,f2,f3), (x1, x2,x3), (totalbw/3, totalbw/3,totalbw/3))
    #print uf360.evalf(subs={x1:result[0]})
    #print uf720.evalf(subs={x2:result[1]})
    #print uf1080.evalf(subs={x3:result[2]})
    #print result

class SecondTier(object):

    ##Initialize utility functions
    session_index={}
    standarduf={}
    output={}
    x=Symbol('x')
    standarduf['360']=-17.53 * (x**(-1.048)) + 0.9912
    standarduf['720']=-4.85 * (x**(-0.647)) + 1.011
    standarduf['1080']=-3.035 * (x**(-0.5061)) + 1.022
    ##Initialize MPD
    representations={}
#    representations['360']=[100,200,400,600,800,1000]
#    representations['720']=[100,200,400,600,800,1000,1500,2000]
#    representations['1080']=[100,200,600,1000,2000,4000,6000,8000]


    representations['360']=[331,529,720,922,1124]
    representations['720']=[530,728,926,1120,1620,2120]
    representations['1080']=[629,1090,2300,4136,5790,8082]



#    def __init__(self):
#	logging.info('test')
#	logger = logging.getLogger(__name__)

    def call(self, totalbw, clients):
        self.output={}
        self.ext = 1
        # for client in clients:
        clients = dict(enumerate(clients))
        # while i<len(clients):
        #     _clients[i]=clients[i]
        #     i+=1

        #print totalbw
        for client in clients:
            #print clients[client]
            # self.clients[client]=self.clients[client].split(",")
            clients[client]=list(clients[client])
            clients[client][1]=int(clients[client][1])
            #print "Build utility function"
            adjusteduf=self.builduf(clients[client])
            clients[client].append(adjusteduf)
        #print clients
            #print adjusteduf.evalf(subs={x:1000
        # if nclients==1:
        #     res=getlowerpoints(clients[0][2],min(totalbw,int(clients[0][1])))
        #     if ext==1:
        #         print "Total BW:"+ str(totalbw)
        #         clientorder=""
        #         for client in clients:
        #             clientorder+=clients[client][0]+","
        #         #print clients
        #         print "Client order:"+str(clientorder)
        #         print "VQ report:[("+str(res)+"), ("+str(ufmap(clients[0][3],float(res)))+"),0,0,0,0,0,0,0]"
        #         print "SI report:[("+str(res)+"), ("+str(ufmap(clients[0][3],float(res)))+"),0,0,0,0,0,0,0]"
        #         print "CT report:[("+str(res)+"), ("+str(ufmap(clients[0][3],float(res)))+"),0,0,0,0,0,0,0]"
        #         print "AL report:[("+str(res)+"), ("+str(ufmap(clients[0][3],float(res)))+"),0,0,0,0,0,0,0]"
        #         print "BASE report:[("+str(res)+"), ("+str(ufmap(clients[0][3],float(res)))+"),0,0,0,0,0,0,0]"
        #     output[clients[0][0]]=[]
        #     output[clients[0][0]].append(res)
        #     output[clients[0][0]].append(res)
        #     output[clients[0][0]].append(res)
        #     output[clients[0][0]].append(res)
        #     output[clients[0][0]].append(res)
        #     print "results:"+str(output)
        #     exit()
        clients = self.getoptimalpoints(clients, totalbw)
        clients = self.getcandidatepoints(clients)
        self.walkthroughvq(clients, totalbw)
        return self.output

    def ufmap(self, uf,bitrate):
        vq=uf.evalf(subs={self.x:float(bitrate)})
        if vq>1:
            vq=1
        return vq

    def builduf(self, clientparam):
        standardinstance=self.standarduf[clientparam[2]]
        maxrep=max(self.representations[clientparam[2]])
        linkcap=int(clientparam[1])
        adjusteduf=standardinstance/(standardinstance.evalf(subs={self.x:min(maxrep,linkcap)}))
        ##adjust uf by the maxium bitrate offered in the MPD
        #adjusteduf=standardinstance/(standardinstance.evalf(subs={x:max(representations[clientparam[2]])}))
        return adjusteduf

    def getoptimalpoints(self, clients, totalbw):
        y=0
        ufset={}
        functionset=[]
        variableset=[]
        startingpointset=[]
        flag=0
        for client in clients:
            ufset[client]=clients[client][3].subs(self.x,Symbol('x'+str(client)))
            variableset.append(Symbol('x'+str(client)))
            if clients[client][2]=='360':
                startingpointset.append(totalbw/len(clients)/2)
            else:
                startingpointset.append(int(totalbw)/len(clients))
            if flag==1:
                functionset.append(left-ufset[client])
                left=ufset[client]
                y+=Symbol('x'+str(client))
            else:
                left=ufset[client]
                flag=1
                y+=Symbol('x'+str(client))
        z=y-int(totalbw)
        #print type(z)
            #print ufset[client]
        #print z
        functionset.append(z)
        #print functionset
        #print variableset
        #print "Optimizing..."
        #result=nsolve((', '.join(functionset)), (', '.join(variableset)), (int(totalbw)/3, int(totalbw)/3,int(totalbw)/3))
        b=1
        while b<12:
            try:
                result=nsolve(functionset, variableset,startingpointset)
            except:
                #print "oops"
                if b>10:
		    logging.error("[mu]Impossible to find optimal points.")
                    raise ImpossibleSolution("ERROR: Impossible to fine optimial points.")
                    # sys.exit()
                b+=1
                continue
            break
        #print result
        for client in clients:
	  #/  print result[client]
            clients[client].append(float(result[client]))
        return clients

    def getcandidatepoints(self, clients):
        for client in clients:
            left=min(self.representations[clients[client][2]])
            right=max(self.representations[clients[client][2]])
            for rep in self.representations[clients[client][2]]:
                if rep<clients[client][4]:
                    left=rep
                    #right=rep
                if rep>clients[client][4]:
                    right=rep
                    break
            clients[client].append([left,right])
            leftresult=0
            rightresult=0
            leftresult=clients[client][3].evalf(subs={self.x:left})
            rightresult=clients[client][3].evalf(subs={self.x:right})
            clients[client].append([leftresult,rightresult])
        return clients

    def getlowerpoints(self, res,bitrate):
        left=0
        left=min(self.representations[str(res)])
        for rep in self.representations[str(res)]:
            if rep<=bitrate:
                left=rep
            if rep>bitrate:
                return left
        return left

    def calrsd(self, clist):
        #print clist
        s=0
        rsd=0
        tmp=0
        try:
            cmean=sum(clist)/len(clist)
        except ZeroDivisionError:
            cmean = 0
        for cl in clist:
            tmp+=(cl-cmean)**2
        s=sqrt(tmp/(len(clist)-1))
        #print tmp
        if cmean==0:
            rsd=0
        else:
            rsd=100*s/cmean
        #print rsd
        return rsd

    def calsidev(self, bcomb, clients):
        sidevlist=[]
        filename=""
        ctime=time.time()
        #print ctime
        si=""
        #[[time,deltaq],...]
        i=0
        while i<len(bcomb):
            j=0
            silist=[]
            while j<len(bcomb[i]):
                si=self.calsi([ctime,bcomb[i][j]],clients[j])
                if si=="skip":
                    j+=1
                    continue
                silist.append(si)
                j+=1
            #print silist
            ## If there is only one item in the silist (causing by one new stream joining one existing stream), we
            ## add a 0 to enable the deviation calculation. This will not affect the cases that there are multiple existing
            ## streams.
            if len(silist)==1:
                silist.append(0)
            sidevlist.append(self.calrsd(silist))
            #sidevlist.append(sum(silist))
            i+=1
        #print sidevlist
        return sidevlist

    def set_session_index(self, client, timestamp, bitrate):
        try:
            self.session_index[client].append([timestamp, bitrate])
        except KeyError:
            self.session_index[client] = []
            self.set_session_index(client, timestamp, bitrate)

    # def get_session_index(self, client):
    #     return
    #     filename=self.directory+"si/"+sclient[0]+".txt"
    #     fo=open(filename,"r")
    #     tmp=(fo.read()).split('\n')
    #     #print tmp
    #     if tmp[0]!='':
    #         for t in tmp:
    #             if len(t.split(","))>1:
    #                 vqqueue.append(t.split(","))

    def calsi(self, candi,sclient):
        # tmp=[]
        si=0
        try:
            vqqueue = self.session_index[sclient[0]]
        except KeyError:
            vqqueue = []
        vqqueue.append(candi)
        #print vqqueue
        if len(vqqueue)<2:
            logging.warning("[mu] SESSION LOG EMPTY! ERROR or NEW STREAM")
            return "skip"
        i=1
        while i<len(vqqueue):
            #print vqqueue
            #print sclient
            #print "temp"
            #print abs(float(vqqueue[i][1])-float(vqqueue[i-1][1]))
            #print math.exp(-0.015*(float(candi[0])-float(vqqueue[i][0])))
            #print ufmap(sclient[3],float(vqqueue[i][1]))
            inisi=abs(self.ufmap(sclient[3],float(vqqueue[i][1]))-self.ufmap(sclient[3],float(vqqueue[i-1][1])))
            fogsi=inisi*(math.exp(-0.015*(float(candi[0])-float(vqqueue[i][0]))))
            if fogsi<(inisi*0.1):
                fogsi=inisi*0.1
            si+=fogsi
            #print si
            i+=1
        # fo.close()
        return si


    def walkthroughvq(self, clients, totalbw):
        # global totalbw
        # global clients
        # global output
        # global ext
        blist=[]
        bvlist=[]
        bvrsd=[]
        costlist=[]
        silist=[]
        nf=()
        nfv=()
        totallc=0
        tmp={}
        #print clients
        for client in clients:
            totallc+=int(clients[client][1])
        for client in clients:
            blist.append(clients[client][5])
            bvlist.append(clients[client][6])
            if totallc<=totalbw:
                nf+=(int(clients[client][1]),)
                nfv+=(float(self.ufmap(clients[client][3],clients[client][1])),)
            else:
                share=self.getlowerpoints(clients[client][2],int(clients[client][1])*totalbw/totallc)
                nf+=(share,)
                nfv+=(self.ufmap(clients[client][3],share),)
        bcomb=list(itertools.product(*blist))
        bvcomb=list(itertools.product(*bvlist))
        ##Mu: Uncomment the following two appends to add the case of equal bw division to the results
        #nf+=(getlowerpoints(clients[client][2],totalbw/len(clients)),)
        #nfv+=(ufmap(clients[client][3], getlowerpoints(clients[client][2],totalbw/len(clients))),)
        refbcomb=[]
        refbvcomb=[]
        refbcomb.append(nf)
        refbvcomb.append(nfv)
        refqdock=self.calrsd(refbvcomb[0])
        refcdock=(sum(refbcomb[0])/sum(refbvcomb[0]))
        refsidock=self.calsidev(refbcomb, clients)
        ##SI deviation calculation
        sidevlist=self.calsidev(bcomb, clients)
        j=0
        qdock=[-1]*len(bcomb)
        cdock=[-1]*len(bcomb)
        sidock=[-1]*len(bcomb)
        while j<len(bcomb):
            if sum(bcomb[j])>totalbw:
                #print 'Sum too large, drop this option.'
                #bvrsd.append([bcomb[i],9999,-9999,9999])
                pass
            else:
                qdock[j]=self.calrsd(bvcomb[j])
                cdock[j]=(sum(bcomb[j])/sum(bvcomb[j]))
                sidock[j]=(sidevlist[j])
            j+=1
        #print bcomb
        #print bvcomb
        #print sidock
        ##Quality deviation calculation
        i=0
        while i<len(bcomb):
            if sum(bcomb[i])>totalbw:
                #print "N"
                pass
            else:
                #print "Y"
                qoutput=0
                if max(qdock)!=0:
                    qoutput=qdock[i]/max(qdock)
                coutput=0
                if max(cdock)!=0:
                    coutput=cdock[i]/max(cdock)
                soutput=0
                if max(sidock)!=0:
                    soutput=sidock[i]/max(sidock)
                bvrsd.append([bcomb[i],bvcomb[i],qdock[i],sidock[i],cdock[i],qoutput,soutput,coutput,(qoutput+coutput+soutput)/3])
            i+=1
        bvrsd.sort(key=lambda x: float(x[2]))
        if self.ext==1:
            clientorder=""
            for client in clients:
                clientorder+=clients[client][0]+","
            #print clients
            logging.debug("[mu] Client order:"+str(clientorder))
            logging.debug("[mu] VQ report:"+str(bvrsd[0]))
        #for b in bvrsd:
            #print b
        #print "----"
        if not bvrsd:
            logging.error("[mu] Impossible to find allocation solution. totalbw too small??")
            sys.exit()
        for client in clients:
            clients[client].append(bvrsd[0][0][client])
            self.output[clients[client][0]]=[]
            self.output[clients[client][0]].append(bvrsd[0][0][client])
        ### COST calculation
        bvrsd.sort(key=lambda x: float(x[3]))
        if self.ext==1:
                logging.debug("[mu] SI report:"+str(bvrsd[0]))
        #for b in bvrsd:
            #print b
        #print "----"
        for client in clients:
            clients[client].append(bvrsd[0][0][client])
            self.output[clients[client][0]].append(bvrsd[0][0][client])
        ### COST calculation
        bvrsd.sort(key=lambda x: float(x[4]))
        if self.ext==1:
                logging.debug("[mu] CT report:"+str(bvrsd[0]))
        #for b in bvrsd:
            #print b
        #print "----"
        for client in clients:
            clients[client].append(bvrsd[0][0][client])
            self.output[clients[client][0]].append(bvrsd[0][0][client])
        ### Combine calculation
        bvrsd.sort(key=lambda x: float(x[8]))
        if self.ext==1:
                logging.debug("[mu] AL report:"+str(bvrsd[0]))
        #for b in bvrsd:
            #print b
        #print "----"
        for client in clients:
            clients[client].append(bvrsd[0][0][client])
            self.output[clients[client][0]].append(bvrsd[0][0][client])
        if self.ext==1:
            logging.debug("[mu] Total BW:"+ str(totalbw))
            qboutput=0
            if max(qdock)!=0:
                qboutput=refqdock/max(qdock)
            cboutput=0
            if max(cdock)!=0:
                cboutput=refcdock/max(cdock)
            sboutput=0
            if max(sidock)!=0:
                sboutput=refsidock[0]/max(sidock)
            logging.debug("[mu] BASE report:"+str([refbcomb[0],refbvcomb[0],refqdock,refsidock[0],refcdock,qboutput,cboutput,sboutput,(qboutput+cboutput+sboutput)/3]))

class ImpossibleSolution(Exception):
    pass


#print 'Number of arguments:', len(sys.argv), 'arguments.'
#print 'Argument List:', str(sys.argv)
#total available bandwidth
#Number of clients
#ParametersofclientN(uniqueIDforsessionmgm,linkcapacity,resolution)

