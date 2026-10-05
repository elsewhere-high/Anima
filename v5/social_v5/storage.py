"""Authenticated encryption for personal payloads; OS-protected local key."""
import base64, ctypes, hashlib, hmac, json, os
from pathlib import Path
from cryptography.fernet import Fernet

def _dpapi(data, decrypt=False):
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_ubyte))]
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)))
    dest = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(source),None,None,None,None,0,ctypes.byref(dest)):
        raise ctypes.WinError()
    try: return ctypes.string_at(dest.pbData,dest.cbData)
    finally: ctypes.windll.kernel32.LocalFree(dest.pbData)

class Cipher:
    def __init__(self,path):
        path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            saved=path.read_bytes(); key=_dpapi(saved,True) if os.name=='nt' else saved
        else:
            key=Fernet.generate_key(); saved=_dpapi(key) if os.name=='nt' else key
            with path.open('xb') as f:f.write(saved)
            if os.name!='nt':os.chmod(path,0o600)
        self.fernet=Fernet(key)
        self.index_key=base64.urlsafe_b64decode(key)
    def dump(self,value):return self.fernet.encrypt(json.dumps(value,ensure_ascii=False).encode()).decode()
    def load(self,value):return json.loads(self.fernet.decrypt(value.encode()).decode())
    def index(self,value):return hmac.new(self.index_key,value.encode(),hashlib.sha256).hexdigest()
