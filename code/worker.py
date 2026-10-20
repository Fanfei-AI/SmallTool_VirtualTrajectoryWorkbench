import asyncio
import json
import math
import logging
import os
import sys
import time
import traceback
from collections import deque
from pathlib import Path
from trajectory import Route, Journey
from storage import save_json, read_json

ROOT=Path(__file__).resolve().parent
DATA=ROOT.parent/'data'
MODE=sys.argv[1] if len(sys.argv)>1 else 'run'
last_phase=None
last_warning=0

class ConnectionErrors(logging.Handler):
    detail=None
    def emit(self, record):
        text=record.getMessage().lower()
        for token, hint in (
            ('device is not connected','未检测到iPhone，请检查USB连接、解锁手机并确认信任此电脑'),
            ('device not found','未找到目标iPhone，请重新连接USB并解锁手机'),
            ('device is not paired','手机尚未与电脑配对，请解锁手机并确认信任'),
            ('waiting for user dialog approval','请在手机上确认信任此电脑'),
            ('user refused to trust','手机未信任此电脑，请重新连接并确认信任'),
            ('connection was terminated','手机连接已中断，请检查USB连接'),
        ):
            if token in text:
                self.detail=hint
                break

connection_errors=ConnectionErrors(level=logging.ERROR)
def failure_detail():
    return (connection_errors.detail or '定位命令提前结束，请检查手机连接与开发者模式')+'；恢复真实定位尚未确认'

def write(name,obj):
    save_json(DATA/name,obj)

def status(phase,**kw):
    global last_phase,last_warning
    last_phase=phase
    value=dict(phase=phase,pid=os.getpid(),time=time.time(),**kw)
    try:
        write('status.json',value)
    except OSError as exc:
        # Telemetry must never close the developer connection.
        if time.monotonic()-last_warning>10:
            print('Status file unavailable; positioning continues: '+str(exc),flush=True)
            last_warning=time.monotonic()
    if phase in ('connecting','simulation_cleared','failed'):
        print(json.dumps(value,ensure_ascii=False),flush=True)

async def execute(self,latitude,longitude):
    if MODE=='clear':
        await self.clear()
        status('simulation_cleared')
        return
    c=json.loads((DATA/'run.json').read_text(encoding='utf-8'))
    journey=Journey(c)
    route=journey.route
    write('route.json',dict(points=route.preview(),total=route.total,version=journey.version))
    distance=0.0
    pace=route.rng.uniform(c['paceMin'],c['paceMax'])
    target=pace
    next_change=0
    last=time.monotonic()
    first=True
    accepted_times=deque(maxlen=100)
    last_report=0
    control='running'
    anchor=None
    offset=[0.0,0.0]
    destination=[0.0,0.0]
    last_point=route.at(0)
    next_control=0

    while not (DATA/'stop.flag').exists():
        tick=time.monotonic()
        # No catch-up teleport after an API stall: cap each movement interval.
        dt=min(tick-last,2/c['hz']); last=tick
        if tick>=next_change:
            target=route.rng.uniform(c['paceMin'],c['paceMax'])
            next_change=tick+route.rng.uniform(4,9)
        pace+=(target-pace)*(1-__import__('math').exp(-dt/3))
        if tick>=next_control:
            requested=read_json(DATA/'control.json',{}).get('mode','running')
            next_control=tick+0.1
            if requested!=control:
                if requested in ('hold','jitter'):
                    anchor=last_point[:]
                    offset=[0.0,0.0]; destination=[0.0,0.0]
                control=requested
        returning=control=='running' and anchor is not None
        if not first and control=='running' and not returning:
            version=journey.version
            journey.advance(1000/(60*pace)*dt)
            route=journey.route
            if journey.version!=version:
                try:
                    write('route.json',dict(points=route.preview(),total=route.total,version=journey.version))
                except OSError as exc:
                    print('Route display update failed: '+str(exc),flush=True)
            distance=journey.distance
        lat,lon=route.at(distance)
        speed=1000/(60*pace)
        if control in ('hold','jitter'):
            if control=='jitter' and c['jitter']>0:
                delta=[destination[k]-offset[k] for k in (0,1)]
                length=math.hypot(*delta)
                if length<0.01:
                    angle=route.rng.uniform(0,2*math.pi)
                    radius=c['jitter']*math.sqrt(route.rng.random())
                    destination=[radius*math.cos(angle),radius*math.sin(angle)]
                else:
                    step=min(length,speed*dt)
                    offset=[offset[k]+delta[k]/length*step for k in (0,1)]
            lat=anchor[0]+math.degrees(offset[1]/6371000)
            lon=anchor[1]+math.degrees(offset[0]/(6371000*math.cos(math.radians(anchor[0]))))
        elif returning:
            dx=math.radians(lon-last_point[1])*6371000*math.cos(math.radians(lat))
            dy=math.radians(lat-last_point[0])*6371000
            length=math.hypot(dx,dy)
            fraction=min(1,speed*dt/max(length,1e-9))
            lat=last_point[0]+(lat-last_point[0])*fraction
            lon=last_point[1]+(lon-last_point[1])*fraction
            if fraction>=1: anchor=None
        last_point=[lat,lon]
        await original_set(self,lat,lon)
        accepted_times.append(time.monotonic())
        actual_hz=(len(accepted_times)-1)/(accepted_times[-1]-accepted_times[0]) if len(accepted_times)>1 else 0
        first=False
        # Display telemetry at 5 Hz; coordinate writes use the requested rate.
        if accepted_times[-1]-last_report>=0.2:
            status('paused' if control!='running' else 'resuming' if anchor is not None else 'holding_endpoint' if journey.holding else 'running',pause_mode=control,latitude=lat,longitude=lon,distance=distance,total=route.total,pace=None if journey.holding else pace,hz=c['hz'],actual_hz=round(actual_hz,2),loop=journey.loop,lap=journey.lap,travelled=journey.travelled,route_version=journey.version)
            last_report=accepted_times[-1]
        await asyncio.sleep(max(0,1/c['hz']-(time.monotonic()-tick)))
    await self.clear()
    status('simulation_cleared')

if __name__=='__main__':
    from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
    from pymobiledevice3.cli.cli_common import OSUTILS
    from pymobiledevice3.__main__ import main
    original_set=LocationSimulation.set
    LocationSimulation.set=execute
    OSUTILS.wait_return=lambda:None
    logging.getLogger('pymobiledevice3.__main__').addHandler(connection_errors)
    started=time.monotonic()
    sys.argv=['pymobiledevice3','developer','dvt','simulate-location','set','--','0','0']
    status('connecting')
    try:
        main()
        if last_phase!='simulation_cleared': status('failed',error=failure_detail())
    except SystemExit as exc:
        if exc.code not in (None,0) or last_phase!='simulation_cleared':
            status('failed',error=failure_detail())
    except BaseException as exc:
        status('failed',error=str(exc)+'；恢复真实定位尚未确认，请点击停止并恢复')
        traceback.print_exc()
