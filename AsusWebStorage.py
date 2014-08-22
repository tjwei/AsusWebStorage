import uuid
import time
import hashlib
import hmac
from urllib2 import quote
from getpass import getpass
import requests
from lxml import etree
from collections import OrderedDict
SERVICE_PORTAL = "https://sp.yostore.net/"

class odict(OrderedDict):
    def __str__(self):        
        def _str(x):
            if isinstance(x,list):
                if len(x)==1:
                    return _str(x[0])
                return "\n"+"\n".join(_str(y).replace("\n", "\n\t") for y in x)
            return str(x) 
        return "ODICT:\n" + "\n".join("\t%s: %s"%(k,_str(v).replace("\n", "\n\t")) for k,v in self.iteritems())
    def _repr_html_(self):
        def _html(x):
            if isinstance(x,list):
                if len(x)==1:
                    return _html(x[0])
                return "<ol><b>LIST</b>:"+"\n".join("<li>"+_html(y)+"</li>" for y in x)+"</ol>"
            elif hasattr(x, "_repr_html_"):
                return x._repr_html_()
            else:
                return str(x) 
        return "<ul><b>ODICT</b>:" + "\n".join("<li>%s: %s</li>"%(k,_html(v)) for k,v in self.iteritems())+"</ul>"
        
def recursive_dict(element):
    # return element.tag, odict(map(recursive_dict,element)) or element.text
    if len(element):        
        rtn = odict()
        for e in element:            
            tag, d = recursive_dict(e)            
            rtn.setdefault(tag, []).append(d)
    else:
        rtn = element.text
        if rtn is None and 'name' in element.attrib and 'value' in element.attrib:
            return element.tag+"."+element.attrib['name'], element.attrib['value']
    return element.tag, rtn

def xml_to_dict(xmlstr):
    try:
        return recursive_dict(etree.fromstring(xmlstr))
    except:
        print "failed", xmlstr

def recursive_xml(d, dep="  "):        
        return "\n".join("%s<%s>%s</%s>"%(dep,  k, 
                                                                ("\n"+recursive_xml(v, dep+"  ") if isinstance(v, dict) else v), 
                                                                k) for k,v in d.items())
            
def dict_to_xml(d, roottag):
    return '<?xml version="1.0" encoding="utf-8"?>\n<%s>\n%s\n</%s>'%(roottag, recursive_xml(d), roottag)

def time_stamp():
    return  int(round(time.time() ))

ERROR_MSG ={0:'Success', 
                       2:'User Authentication Fail', 
                       3: 'Payload is not validate', 
                       5: 'Developer Authentication Fail',                       
                       225: 'Parameter Error',
                       504: 'OTP Auth Failed: USer ID/password/OTP incoreect or without OTP when required',
                       505: 'OTP Credential ID is locked',
                       508: "CAPTCHA Failed", 
                       999:'General Error'}
def arg_props(d, *keys):
    return [(k,d[k]) for k in keys if k in d and d[k] is not None]

class AsusWebStorage(object):    
    def __init__(self, sid, progkey, userid, password, language='zh_TW', service=1):
        self.__dict__.update(locals())
        self.session = requests.Session()
        
    def authString(self):
        method = "HMAC-SHA1"
        nonce = str(uuid.uuid1()).replace('-','')
        timestamp = time_stamp()
        plain = "nonce=%s&signature_method=%s&timestamp=%s"%(nonce,method,timestamp)
        quoted = quote(plain)    
        signature = quote(hmac.new(self.progkey, quoted, hashlib.sha1).digest().encode('base64').rstrip('\n'))
        return 'signature_method="%s",timestamp="%s",nonce="%s",signature="%s"'%(method, timestamp, nonce, signature)
    
    def post(self, act, url, payload, oauth=False):
        print "post", act, url, payload
        headers =  { "Cookie": "sid=%s;"%self.sid}
        if oauth:
            headers["Authorization"] = self.authString()
        data = dict_to_xml(odict(payload), act)
        self.last_response  = self.session.post(url, data=data, headers=headers)        
        rootname, result = xml_to_dict(self.last_response.content) 
        self.result = result
        status = int(result['status'][0])        
        if status != 0:            
            print "url="+url, "act="+act, "rootname="+rootname
            print "DATA:"
            print data
            if status in ERROR_MSG:                
                print "Error:", ERROR_MSG[status]
            else:
                print "Error: code=%d"%status
            return status, None
        return status, result    

    
    def props(self, *keys):
        return [(k, time_stamp() if k=="time" else getattr(self, k)) for k in keys]
    
    def requestservicegateway(self):
        act = "requestservicegateway"
        url = SERVICE_PORTAL + "member/%s/"%act
        payload = self.props('userid','password', 'language', 'service')
        status, result = self.post(act, url, payload)
        if not status:
            self.gateway = "https://%s/"%result['servicegateway'][0]
            return self.gateway        
    
    def acquiretoken(self):        
        act = "aaa"
        url = self.gateway + "member/acquiretoken/"
        payload = self.props ('userid', 'password', 'time')
        
        status, result = self.post(act, url, payload, oauth=True)
        if not status:
            self.token = result['token'][0]
            self.inforelay = "https://%s/"%result['inforelay'][0]
            self.webrelay = "https://%s/"%result['webrelay'][0]
            self.searchserver = "https://%s/"%result['searchserver'][0]
            self.package = result['package'][0]
            return self.token
        
    def connect(self):
        if self.requestservicegateway():
            for i in range(2): # acquiretoken sometimes fails for some reason
                if self.acquiretoken():
                    return True
                
    def getinfo(self):
        act = "getinfo"
        url = self.gateway + "member/%s/"%act
        payload = self.props ('userid', 'token', 'time')
        status, result = self.post(act, url, payload)
        return result
    
    def browsefolder(self, folderid, type=None, pageno=None, pagesize=None, sortby=1, sortdirection=0):
        act = "browse"
        url = self.inforelay + "inforelay/browsefolder/"
        payload = self.props ('token', 'language', 'userid') 
        payload += arg_props(locals(), "folderid", "type", "pageno", "pagesize", "sortby", "sortdirection")
        status, result = self.post(act, url, payload)
        return result
    
    def getpersonalsystemfolder(self, rawfoldername):
        act = "getpersonalsystemfolder"
        url = self.inforelay + "folder/%s/"%act
        payload = self.props("token", "userid") + arg_props(locals(), "rawfoldername")
        status, result = self.post(act, url, payload)
        if status is 0:
            return result['folderid'][0]
        
    def getlatestchangefiles(self, top=None, targetroot="-5", sortdirection=0):
        act = "getlatestchangefiles"
        url = self.inforelay + "file/%s/"%act
        payload = self.props("token", "userid") + arg_props(locals(), "top", "targetroot", "sortdirection")
        status, result = self.post(act, url, payload)
        if status is 0:
            return result['entry', isdi]
    def getallchangeseq(self):
    
        act = "getentryinfo"
        url = self.inforelay + "fsentry/%s/"%act
        payload = self.props("token") 
        status, result = self.post(act, url, payload)
        if status is 0:
            return result
        
    def getentryinfo(self, isfolder, entryid):
        act = "getentryinfo"
        url = self.inforelay + "fsentry/%s/"%act
        payload = self.props("token") + arg_props(locals(), "isfolder", "entryid")
        status, result = self.post(act, url, payload)
        if status is 0:
            return result
        
    def propfind(self, parent, find, type="system.unknown", isshared=None):
        act = "propfind"
        url = self.inforelay + "find/%s/"%act
        find = find.encode("base64").strip("\n")
        payload = self.props("token", "userid") + arg_props(locals(), "parent", "find", "type", "isshared")
        status, result = self.post(act, url, payload)
        if status is 0:
            return result
        
    def directdownload(self, fid, start, end):
        headers = {"Range":"bytes=%d-%d"%(start, end)}
        payload = {"dis": self.sid, "fi": fid}
        r = self.session.get(self.webrelay+"webrelay/directdownload/"+self.token+"/", params=payload, headers=headers)
        if r.status_code in [200, 206]:
            return r.content
        
    def getmysyncfolder(self):
        act = "getmysyncfolder"
        url = self.inforelay + "folder/%s/"%act
        payload = self.props("userid", "token")
        status, result = self.post(act, url, payload)
        if status is 0:
            return result["id"][0]
    
    