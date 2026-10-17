import json
import os
import subprocess
import threading
import time
import uuid
import sys
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from trajectory import validate, Route, Journey
from storage import save_json,read_json

ROOT=Path(__file__).resolve().parent
DATA=ROOT.parent/'data'; DATA.mkdir(exist_ok=True)
PY=Path(sys.executable).with_name('pythonw.exe')
PORT=18763
LOCK=threading.Lock()
DEFAULT=dict(pins=[],paceMin=6,paceMax=8,jitter=5,pinJitter=1,hz=20)

def read(path,default):
    return read_json(path,default)

def save(path,obj):
    save_json(path,obj)

def processes():
    command="[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\\.exe$' } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    p=subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
    if p.returncode: raise RuntimeError('无法核对定位进程，未启动新任务')
    items=json.loads(p.stdout or '[]')
    if isinstance(items,dict): items=[items]
    current=[]
    for item in items:
        cmd=(item.get('CommandLine') or '').lower().replace('/','\\')
        if str(ROOT/'worker.py').lower() in cmd: current.append(item['ProcessId'])
    return current

def launch(mode):
    (DATA/'stop.flag').unlink(missing_ok=True)
    save(DATA/'status.json',dict(phase='connecting',time=time.time()))
    with (DATA/'worker.log').open('a',encoding='utf-8') as log:
        startup=subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow=subprocess.SW_HIDE
        subprocess.Popen([str(PY),'-B','-u',str(ROOT/'worker.py'),mode],cwd=ROOT,stdout=log,stderr=log,stdin=subprocess.DEVNULL,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT/'web'),**kw)
    def log_message(self,*args): pass
    def reply(self,obj,code=200):
        b=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path=='/api/instance': return self.reply(dict(project=str(ROOT.parent),pid=os.getpid()))
        if self.path=='/api/config': return self.reply(read(DATA/'config.json',DEFAULT))
        if self.path=='/api/history': return self.reply(read(DATA/'history.json',[]))
        if self.path=='/api/status':
            s=read(DATA/'status.json',dict(phase='idle'))
            if s.get('phase') in ('running','holding_endpoint','connecting') and time.time()-s.get('time',0)>15:
                s={**s,'phase':'unresponsive','error':'定位状态超过 15 秒未更新，连接或进程可能中断；真实定位未确认恢复'}
            return self.reply(s)
        if self.path=='/api/route': return self.reply(read(DATA/'route.json',dict(points=[])))
        if self.path.startswith('/api/'): return self.reply({'error':'不存在'},404)
        return super().do_GET()
    def do_POST(self):
        # Local control endpoints only: reject cross-site browser requests.
        if self.headers.get('Host') not in (f'127.0.0.1:{PORT}',f'localhost:{PORT}'):
            return self.reply({'error':'Host 不允许'},403)
        origin=self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'):
            return self.reply({'error':'Origin 不允许'},403)
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.reply({'error':'需要 JSON'},415)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>100000: raise ValueError('请求过大')
            body=json.loads(self.rfile.read(size) or '{}')
            with LOCK:
                if self.path=='/api/history/delete':
                    record_id=body.get('id')
                    if not isinstance(record_id,str) or not record_id:
                        raise ValueError('历史记录编号无效')
                    records=read(DATA/'history.json',[])
                    remaining=[r for r in records if r.get('id')!=record_id]
                    if len(remaining)==len(records):
                        return self.reply(dict(error='该历史记录已不存在'),404)
                    save(DATA/'history.json',remaining)
                    return self.reply(dict(ok=True))
                if self.path=='/api/history':
                    name=body.get('name','').strip()
                    if not name or len(name)>80: raise ValueError('名称需为 1～80 个字符')
                    c=validate(body.get('config',{})); Journey(c)
                    records=read(DATA/'history.json',[])
                    record=dict(id=uuid.uuid4().hex,name=name,time=time.time(),config=c)
                    records.insert(0,record)
                    save(DATA/'history.json',records)
                    save(DATA/'config.json',c)
                    return self.reply(dict(ok=True,id=record['id']))
                if self.path in ('/api/save','/api/start'):
                    c=validate(body); route=Journey(c).route
                    save(DATA/'config.json',c)
                    if self.path=='/api/save': return self.reply(dict(ok=True,total=route.total))
                    current=processes()
                    if current: raise ValueError('已有轨迹任务，请先停止并恢复真实定位')
                    save(DATA/'run.json',c)
                    (DATA/'route.json').unlink(missing_ok=True)
                    launch('run')
                    return self.reply(dict(ok=True))
                if self.path=='/api/stop':
                    current=processes()
                    if current:
                        (DATA/'stop.flag').touch()
                        return self.reply(dict(ok=True,message='已请求停止，等待 clear 调用结果'))
                    launch('clear')
                    return self.reply(dict(ok=True,message='正在建立连接以清除模拟'))
                return self.reply(dict(error='不存在'),404)
        except Exception as exc: self.reply(dict(error=str(exc)),400)

if __name__=='__main__':
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
