from errno import ENOENT
from stat import S_IFDIR, S_IFREG
from sys import argv, exit
import os
import os.path
from time import time, mktime
from datetime import datetime
import dateutil.parser
from dateutil.tz import tzlocal


# import gevent
# from gevent import monkey
# from gevent.pool import Pool
from personal_info import userid, password, sid, progKey # setup your personal information, see personal_info.example.py

# monkey.patch_all()
from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
import AsusWebStorage

class AsusFS(LoggingMixIn, Operations):
    def __init__(self, sid, progKey, userid, password):
        self.aws =  AsusWebStorage.AsusWebStorage(sid, progKey, userid, password)
        if not self.aws.connect():
            raise "Not Connected"
        self.rootid = int(self.aws.getmysyncfolder())
        self._id_cache={'/': (self.rootid, None)}
        self._attr_cache=dict()
        self.uid = os.getuid()
        self.gid = os.getgid()
        
    def update_dir_ids(self,  path):        
        _id, isdir = self._id_cache[path]
        if isdir == S_IFREG:
            return
        self._id_cache[path] = _id, S_IFDIR
        result = self.aws.browsefolder(_id)
        folders, files = result.get("folder", []), result.get("file", [])   
        self._id_cache.update( (os.path.join( path, f['rawfoldername'][0]) ,  (f['id'][0], None)) for f in folders)
        self._id_cache.update( (os.path.join(path, f['rawfilename'][0]) ,  (f['id'][0], S_IFREG)) for f in files)  
                
    def path_to_id(self, path):
        while path.endswith('/'):
            path=path[:-1]
        if not path.startswith('/'):
            path="/"+path
        if path in self._id_cache:
            _id, isdir = self._id_cache[path]
        else:
            head, tail = os.path.split(path)
            if tail == ".hidden":
                return None, None
            headid, isdir = self.path_to_id(head)
            if headid is None or isdir == S_IFREG or path not in self._id_cache:
                return None, None
            else:
                _id, isdir = self._id_cache
        if isdir is None:
            self.update_dir_ids(path)
            isdir = S_IFDIR
        return _id, isdir
        

    def getattr(self, path, fh=None):
        if path in self._attr_cache:
            return self._attr_cache[path]
        print "getattr", path
        _id, isdir = self.path_to_id(path)
        if _id is None:             
            print "getattr not found", path            
            raise FuseOSError(ENOENT)
        result = self.aws.getentryinfo(isdir==S_IFDIR, _id)
        st ={ "st_mode": isdir|0755, "st_uid": self.uid, "st_gid":self.gid}
        if isdir == S_IFREG and 'filesize' in result:
            st['st_size']=int(result['filesize'][0])
        if isdir == S_IFDIR:
            st['st_link']=2
        if 'createdtime' in result:
            # yyyy-MM-dd HH:mm:ss            
            t = datetime.strptime(result['createdtime'][0], "%Y-%m-%d %H:%M:%S")
            st['st_ctime'] = st['st_mtime'] = st['st_atime']= mktime(t.timetuple())
        self._attr_cache[path]=st
        return st
    
    def read(self, path, size, offset, fh):
        print "read", path, size, offset, fh
        _id, isdir = self.path_to_id(path)
        if isdir == S_IFDIR:
            raise FuseOSError(EFAULT)
        rtn = self.aws.directdownload(_id, offset, offset+size-1)
        if rtn == None:
            raise FuseOSError(EFAULT)
        return rtn
                  
    def readdir(self, path, fh):
        print "readdir path=", path
        _id, isdir = self.path_to_id(path)
        if _id is None or isdir != S_IFDIR:
            print "readdir not found", path, _id, isdir
            raise FuseOSError(ENOENT)
        rtn = self.aws.browsefolder(_id)
        folders, files = rtn.get("folder", []), rtn.get("file", [])
        return [".", ".."] +[f['rawfoldername'][0] for f in folders]+[f['rawfilename'][0] for f in files]
    
    # Disable unused operations:
    #getattr = None
    access = None
    flush = None
    getxattr = None
    listxattr = None
    open = None
    opendir = None
    release = None
    releasedir = None
    statfs = None

  


if __name__ == '__main__':
    if len(argv) != 2:
        print('usage: %s <mountpoint>' % argv[0])
        exit(1)
    print "starting fuse"
    fuse = FUSE(AsusFS(sid, progKey, userid, password), argv[1], foreground=True, ro=True)