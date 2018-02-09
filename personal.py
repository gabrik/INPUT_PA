#!/usr/bin/env python3


import socket
import threading
import logging
import json
import time
import os
import signal
import sys
import copy
import urllib.request as urllib2 
from unidecode import unidecode
from utils import utility


LOG_FILE = 'pa.log'

# Enable logging
logging.basicConfig(filename=LOG_FILE,format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
	level=logging.DEBUG)
logger = logging.getLogger(__name__)




#TODO load configuration from file (ip,port, controller ip)

class ThreadedServer(object):

    def __init__(self,host,port,name):
        logger.info('######### Starting - INPUT - vSTB - Personal Acquirer #########')
        self.host = host
        self.port = port
        self.name=name
        self.edge_ip = conf['edge']['ip']
        self.edge_port = int(conf['edge']['port'])
        self.ffconf=conf['daemon']['ffconf']
        self.stream_map={}

        signal.signal(signal.SIGINT, self.signal_handler)

       

        logger.info("[ CONF ] Personal Acquirer configuration ")
        logger.info("[ CONF ] Address %s Port %s " % (self.host, self.port))
        logger.info("[ CONF ] Input User is %s " % self.name)
        logger.info("[ CONF ] FFServer configuration file %s" %  self.ffconf)
        logger.info("[ CONF ] Edge Streamer IP %s Port %s " % (self.edge_ip, self.edge_port))
        logger.info("[ DONE ] Personal Acquirer Configuration")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        logger.info('[ INFO ] Getting Providers and Channels from Edge Acquirer')
        self.providers=self.send_to_edge('provider list')
        self.channels=self.send_to_edge('channel list')
        logger.info('[ DONE ] Getting Providers and Channels from Edge Acquirer')
        logger.info('################# INPUT - vSTB - Personal Acquirer #################')
        logger.info('[ DONE ] Server binded on %s:%d' % (self.host, self.port))
        logger.info('[ INFO ] Generating FFServer configuration')
        self.stream_map = utility.generate_ffserver_conf(self.ffconf,self.providers)
        logger.info('[ DONE ] Generating FFServer configuration')
        logger.info('[ INFO ] Starting FFServer with configuration file %s' %  self.ffconf)
        template = "ffserver -f %s -d -hide_banner -loglevel panic  > ff_out/ffserver.out 2>&1 & echo $! > ff_out/ffserver.pid"
        cmd= str(template %  self.ffconf )
        os.system('rm -rf ff_out')
        os.system('mkdir ff_out')
        os.system(cmd)
        self.ffpid=utility.read_file("ff_out/ffserver.pid")
        logger.info('[ DONE ] FFServer pid: %s' % self.ffpid)
        logger.info('[ INFO ] Starting FFMpeg for provide streams')
        '''
        for key in self.stream_map:
            stream_data=self.stream_map.get(key)
            url_template='http://%s:8090/%s.mp4'
            url=str(url_template % (self.edge_ip,key))
            ffpid=self.start_ffmpeg(url,key)
            url_new=str("%s.mp4" % key)
            self.stream_map.update({key: [url_new,ffpid]})
            logger.info('[ DONE ] FFMpeg for: %s started with pid %s' % (key,ffpid))
        '''
        print ("###### INPUT - vSTB - Personal Acquirer Started ######")

    def listen(self):
        self.sock.listen(5)
        logger.info('[ DONE ] Server listen on %s:%d' % (self.host, self.port))
        while True:
            client, address = self.sock.accept()
            logger.info('[ INFO ] Connection from %s:%s' % address)
            client.settimeout(120)
            threading.Thread(target=self.serve_client, args=(client, address)).start()

    def signal_handler(self,signal, frame):
        logger.info('[ INFO ] Received SINGINT')
        
        for k in self.stream_map:
            v=self.stream_map.get(k)
            if v[1]!=-1:
                logger.info('[ INFO ] Killing FFMpeg [%s]' % v[1])
                os.system('kill -9 ' + str(v[1]))
                logger.info('[ DONE ] Killing FFMpeg [%s]' % v[1])    
        
        logger.info('[ INFO ] Killing FFServer')
        os.system('kill -9 ' + str(self.ffpid))
        logger.info('[ DONE ] Killing FFServer')
        logger.info('[ INFO ] Closing INPUT - vSTB - Personal Acquirer')
        print('\n## Closed INPUT - vSTB - Personal Acquirer ##\n')
        sys.exit(0)

    def read_all(self,client):
        SIZE=65535
        tmp=""
        try:
            while True:
                data = unidecode(client.recv(SIZE).decode())
                tmp += data
                if tmp[-1] == '\n' or tmp[-1] == ']' or tmp[-1] == '}':
                    break
            providerList = tmp
            #providerList = json.loads(providerList)
            return providerList
        #providerList = loadImage(json.loads(providerList))
        except ValueError as ex:
            print("Cannot decode providerList {}".format(ex))
            sys.exit()

    def send_all(self,client,msg):
        logger.debug('[ VERB ] Sending %s to client' % msg)
        msg_len = len(msg)
        total_sent=0
        while total_sent < msg_len:
            sent = client.send(msg[total_sent:])
            if sent==0:
                raise RuntimeError("Cannot sent to socket")
            total_sent=total_sent+sent


    def read_from_client(self,client):
        SIZE=1024
        recv_data=self.read_all(client) #unidecode(client.recv(SIZE).decode().strip())
        #logger.info('Received %s from client' % recv_data)
        recv_data=json.loads(recv_data)
        log_data = copy.deepcopy(recv_data)
        #print("Type of log_data " + str(type(log_data)))
        for log in log_data:
            #print("TYpe of log "+ str(type(log)))
            if type(log) == dict:
                log.pop('image',None)
        logger.info('Received %s from client' % log_data) 
        return recv_data

    def start_ffmpeg(self,url,mapped_stream):
        logger.debug('[ VERB ] start_ffmpeg()')
        logger.info('[ INFO ] Starting FFMpeg with source %s and destination %s' % (url,mapped_stream) )
        template = "ffmpeg -hide_banner -loglevel panic -re -acodec mp3 -i %s -preset ultrafast -acodec copy -vcodec copy http://127.0.0.1:8090/feed%s.ffm > ff_out/%s.out 2>&1 & echo $! > ff_out/%s.pid"
        cmd= str(template %  (url,mapped_stream,mapped_stream,mapped_stream))
        logger.info('[ INFO ] Starting FFMpeg with command %s' % cmd )
        os.system(cmd)
        file_ff=str("ff_out/%s.pid" % mapped_stream )
        ffpid=utility.read_file(file_ff)
        logger.info('[ DONE ] FFMpeg pid: %s' % ffpid)
        return ffpid



    def send_to_edge(self,message,id_content=None):
        logger.info('[ INFO ] msgContacting the INPUT - vSTB - Edge Acquirer')
        logger.info('[ INFO ] Edge Acquirer is on %s:%s' % ( self.edge_ip, self.edge_port))
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.connect((self.edge_ip,self.edge_port))
            if id_content is not None:
                msg_value={"operation":message,"idContent":id_content,"name":self.name}
            else:
                msg_value={"operation":message,"name":self.name}

            msg=json.dumps(msg_value)+'\n'#.encode()
            logger.info('[ INFO ] Sending %s to Edge Acquirer' % msg)
            server.send(msg.encode())
            recv_data=self.read_from_client(server)
            #logger.info('[ INFO ] Received %s from Edge Acquirer' % recv_data)
        except Exception as e:
            logger.error('[ ERRO ] Cannot send to INPUT - vSTB - Edge Acquirer: %r' % e)
            print ('[ ERRO ] Cannot send to INPUT - vSTB - Edge Acquirer: %r' % e)
            return '[]'

        return recv_data


    def channel_list(self,client):
        logger.debug('[ VERB ] channelList()' )
        #data=[]
        #data.append({"http_url":"http://127.0.0.1:50040","id_prog":1,"nome_prog":"Cinema","id_prov":1,"inizio":"2016-09-21 00:00:00","descrizione":"Film"})
        #data.append({"http_url":"http://127.0.0.2:50040","id_prog":2,"nome_prog":"Cinema2","id_prov":2,"inizio":"2016-09-21 00:00:00","descrizione":"Film"})
        log_data = copy.deepcopy(self.channels)
        for log in log_data:
            log.pop('image',None) 
        msg = json.dumps(self.channels).encode() #json.dumps(self.send_to_edge('channel list')) #FOR TEST ONLY NEED TO ASK TO EDGE Acquirer #
        logger.info('[ INFO ]Sending %s to client' % log_data )
        self.send_all(client,msg)
        #client.send(msg)

    def provider_list(self,client):
        logger.debug('[ VERB ] providerList()' )
        #data=[]
        #data.append('{"id_content_prov":1,"nome":"Sky Cinema"}')
        #data.append('{"id_content_prov":2,"nome":"Sky Cinema2"}')
        log_data = copy.deepcopy(self.providers)
        for log in log_data:
            log.pop('image',None) 
        msg = json.dumps(self.providers).encode()  #self.send_to_edge('provider list')
        logger.info('Sending %s to client' % log_data )
        self.send_all(client,msg)
        #client.send(msg)

    def register_dms(self,client,address):
        logger.info('[ INFO ] Registering INPUT - Digital Media Server at %s',address[0])
        self.dms=address[0]
        self.send_all(client,json.dumps({'status':'success'}).encode())
        '''
        logger.info('[ INFO ] Adding live channels to INPUT - Digital Media Server')
        for c in self.channels:
            url = 'http://%s:8080/add/source/%s' %(self.dms,c['http_url'].replace('http://',''))
            resp = urllib2.urlopen(url)
            if resp=='ok':
                logger.info('[ DONE ] Added live channels %s to INPUT - Digital Media Server' % c['http_url'])
            else:
                logger.error('[ ERRO ] Adding live channels %s to INPUT - Digital Media Server' % c['http_url'])
        logger.info('[ DONE ] Adding live channels to INPUT - Digital Media Server')
        '''


    def start_content(self,client,data):
        #id cp (content), destinazione (device)
        logger.info('[ INFO ] Starting a Content')
        
        c = [x for x in self.providers if x['idContentProvider'] == data['idContentProvider']]
        
        key=c[0]['name']
        stream_data=self.stream_map.get(key)
        if(stream_data[1]==-1):
            url_template='http://%s:8090/%s.mp4'
            url=str(url_template % (self.edge_ip,key))
            logger.info('[ DONE ] Starting FFMpeg for: %s '% (key))
            ffpid=self.start_ffmpeg(url,key)
            url_new=str("%s.mp4" % key)
            self.stream_map.update({key: [url_new,ffpid]})
            logger.info('[ DONE ] FFMpeg for: %s started with pid %s' % (key,ffpid))

        dev=data.get('device',None)

        #TODO make as a function
        if  dev != None and dev == 'dlna':

            url_new=stream_data[0]
            dms_data={'address':url_new}
            
            url_dms = 'http://{}:8080/add/source/'.format(self.dms)
            
            logger.info('[ INFO ] URL to INPUT - Digital Media Server: %s'  % url_dms)

            logger.info('[ INFO ] Send to INPUT - Digital Media Server: %s'  % url_dms)


            req = urllib2.Request(url_dms)
            req.add_header('Content-Type', 'application/json; charset=utf-8')
            req.add_header('Content-Length', len(json.dumps(dms_data).encode('utf-8')))
            resp = json.loads(urllib2.urlopen(req, json.dumps(dms_data).encode('utf-8')).read().decode())

            
            
            if resp['status']=='success':
                logger.info('[ DONE ] Added live channel %s to INPUT - Digital Media Server' % url_new)
            else:
                logger.error('[ ERRO ] Adding live channel %s to INPUT - Digital Media Server' % url_new)



        msg = json.dumps({'status':'success'}).encode()
        self.send_all(client,msg)

    #{"operation": "get content", "idContentProvider": 1, "device": "dlna"}
    def stop_content(self,client,data):
        logger.info('[ INFO ] Stopping a Content')
        c = [x for x in self.providers if x['idContentProvider'] == data['idContentProvider']]
        key=c[0]['name']
        v=self.stream_map.get(key)
        dev=data.get('device',None)
        url_new=v[0]
        dms_data={'address':url_new}


        if dev==None:
           
            if v[1]!=-1:
                logger.info('[ INFO ] Killing FFMpeg [%s]' % v[1])
                os.system('kill -9 ' + str(v[1]))
                logger.info('[ DONE ] Killing FFMpeg [%s]' % v[1])


                v[1]=-1
                self.stream_map.update({key: v})



                url_dms = 'http://{}:8080/remove/content/'.format(self.dms)
                logger.info('[ INFO ] URL to INPUT - Digital Media Server: %s'  % url_dms)
                req = urllib2.Request(url_dms)
                req.add_header('Content-Type', 'application/json; charset=utf-8')
                req.add_header('Content-Length', len(json.dumps(dms_data).encode('utf-8')))
                resp = json.loads(urllib2.urlopen(req, json.dumps(dms_data).encode('utf-8')).read().decode())
            
                if resp['status']=='success':
                    logger.info('[ DONE ] Deleted live channel %s to INPUT - Digital Media Server' % url_new)
                else:
                    logger.error('[ ERRO ] Deleting live channel %s to INPUT - Digital Media Server' % url_new)


        elif dev == 'dlna':
            url_dms = 'http://{}:8080/remove/content/'.format(self.dms)
            logger.info('[ INFO ] URL to INPUT - Digital Media Server: %s'  % url_dms)
            req = urllib2.Request(url_dms)
            req.add_header('Content-Type', 'application/json; charset=utf-8')
            req.add_header('Content-Length', len(json.dumps(dms_data).encode('utf-8')))
            resp = json.loads(urllib2.urlopen(req, json.dumps(dms_data).encode('utf-8')).read().decode())
            
            if resp['status']=='success':
                logger.info('[ DONE ] Deletted live channel %s to INPUT - Digital Media Server' % url_new)
            else:
                logger.error('[ ERRO ] Deletting live channel %s to INPUT - Digital Media Server' % url_new)
            
        msg = json.dumps({'status':'success'}).encode()
        self.send_all(client,msg)

        


    def serve_client(self, client,address):
        logger.info('[ INFO ] New Thread on connection from %s:%s' % address)
        SIZE = 1024
        while True:
            try:
                recv_data=unidecode(client.recv(SIZE).decode('ascii').strip())
                logger.info('Received %s from client' % recv_data)
                if recv_data==None:
                    raise Exception('client disconnected')

                ammisible_types = ['channel list','provider list','register dms','get content','stop content','rec content']
                recv_data = json.loads(recv_data)
               
                msg_operation = recv_data.get('operation', None)
                if msg_operation in ammisible_types:

                    if msg_operation=='channel list':
                        self.channel_list(client)
                    elif msg_operation=='provider list':
                        self.provider_list(client)
                    elif msg_operation=='register dms':
                        self.register_dms(client,address)
                    elif msg_operation=='get content':
                        self.start_content(client,recv_data)
                    elif msg_operation=='stop content':
                        self.stop_content(client,recv_data)
                    elif msg_operation=='rec content':
                        id_c=recv_data['idContent']
                        msg=self.send_to_edge('rec content',id_c)
                        print(msg)
                        self.send_all(client,json.dumps(msg).encode())

                else:
                    client.close()
                    logger.error('[ ERRO ] Wrong command: %s' % msg_operation)
                    logger.error('[ ERRO ] Client %s:%s wrong command!' % address)
                    raise Exception('client disconnected')
            except Exception as e:
                #client.send("{'status':false,'error':'aborting'}\n")
                #client.close()
                logger.error('%r' % e)
                print ('error %r' % e)
                return False


if __name__ == "__main__":
    print ("###### INPUT - vSTB - Personal Acquirer ######")
    if len(sys.argv)>1:
        global conf
        conf=utility.load_configuration(sys.argv[1])
        ThreadedServer(conf['daemon']['address'],int(conf['daemon']['port']),conf['daemon']['name']).listen()
    else:
        print ("\t[Usage] python personal.py conf.cfg")