import asyncio
import json
import os
import sys
import time
import traceback
from collections import deque
from pathlib import Path
from trajectory import Route, Journey
from storage import save_json

ROOT=Path(__file__).resolve().parent
DATA=ROOT.parent/'data'
MODE=sys.argv[1] if len(sys.argv)>1 else 'run'
last_phase=None
last_warning=0

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
    while not (DATA/'stop.flag').exists():
        tick=time.monotonic()
        # No catch-up teleport after an API stall: cap each movement interval.
        dt=min(tick-last,2/c['hz']); last=tick
        if tick>=next_change:
            target=route.rng.uniform(c['paceMin'],c['paceMax'])
            next_change=tick+route.rng.uniform(4,9)
        pace+=(target-pace)*(1-__import__('math').exp(-dt/3))
        if not first:
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
        await original_set(self,lat,lon)
        accepted_times.append(time.monotonic())
        actual_hz=(len(accepted_times)-1)/(accepted_times[-1]-accepted_times[0]) if len(accepted_times)>1 else 0
        first=False
        # Display telemetry at 5 Hz; coordinate writes use the requested rate.
        if accepted_times[-1]-last_report>=0.2:
            status('holding_endpoint' if journey.holding else 'running',latitude=lat,longitude=lon,distance=distance,total=route.total,pace=None if journey.holding else pace,hz=c['hz'],actual_hz=round(actual_hz,2),loop=journey.loop,lap=journey.lap,travelled=journey.travelled,route_version=journey.version)
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
    started=time.monotonic()
    sys.argv=['pymobiledevice3','developer','dvt','simulate-location','set','--','0','0']
    status('connecting')
    try:
        main()
        if last_phase!='simulation_cleared': status('failed',error='定位命令提前结束；恢复状态未确认')
    except SystemExit as exc:
        if exc.code not in (None,0) or last_phase!='simulation_cleared':
            status('failed',error=f'定位命令退出：{exc.code}；恢复真实定位尚未确认')
    except BaseException as exc:
        status('failed',error=str(exc)+'；恢复真实定位尚未确认，请点击停止并恢复')
        traceback.print_exc()
