import bisect
import math
import random

R = 6371000.0

def validate(c):
    pts = c.get('pins', [])
    if not 2 <= len(pts) <= 200:
        raise ValueError('请设置 2～200 个 pin')
    for p in pts:
        if len(p) != 2 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in p):
            raise ValueError('坐标无效')
        if not -85 <= p[0] <= 85 or not -180 <= p[1] <= 180:
            raise ValueError('坐标超出范围')
    for k in ('paceMin', 'paceMax', 'jitter', 'pinJitter', 'hz'):
        if not isinstance(c.get(k), (int, float)) or not math.isfinite(c[k]):
            raise ValueError('参数必须是有限数字')
    if not 0.5 <= c['paceMin'] <= c['paceMax'] <= 120:
        raise ValueError('配速应在 0:30～120:00 /公里，最快值不能大于最慢值')
    if not 0 <= c['pinJitter'] <= c['jitter'] <= 200:
        raise ValueError('需满足 0 ≤ pin 抖动 ≤ 普通抖动 ≤ 200 米')
    if not 1 <= c['hz'] <= 20:
        raise ValueError('更新频率为 1～20 Hz')
    if c.get('loopEnabled', False):
        start=c.get('loopStart')
        if isinstance(start,bool) or not isinstance(start,int) or not 1 <= start < len(pts):
            raise ValueError('循环起始点须为整数，且至少保留两个循环点')
    return c

class Route:
    def __init__(self, config, seed=None, start_direction=None, end_direction=None):
        if len(config['pins'])==201 and config['pins'][0]==config['pins'][-1] and start_direction is not None:
            validate({**config,'pins':config['pins'][:-1]})
            c=config
        else:
            c = validate(config)
        self.rng = random.Random(seed)
        self.origin = c['pins'][0]
        self.cos = math.cos(math.radians(self.origin[0]))
        pts = [self.xy(p) for p in c['pins']]
        if any(math.dist(a,b) < 1 for a,b in zip(pts, pts[1:])):
            raise ValueError('相邻 pin 至少间隔 1 米')
        if sum(math.dist(a,b) for a,b in zip(pts,pts[1:])) > 100000:
            raise ValueError('第一版单条轨迹限制为 100 公里')
        offsets = [self.rng.uniform(-c['pinJitter'],c['pinJitter']) for _ in pts]
        offsets[0] = offsets[-1] = 0
        self.points = []
        for i in range(len(pts)-1):
            p0,p1,p2,p3 = pts[max(0,i-1)],pts[i],pts[i+1],pts[min(len(pts)-1,i+2)]
            # Cubic Hermite through pins, shared tangents on both sides.
            t1 = tuple((p2[k]-p0[k])*0.35 for k in (0,1))
            t2 = tuple((p3[k]-p1[k])*0.35 for k in (0,1))
            if start_direction is not None and math.hypot(*t1)<1e-9:
                t1=(-(p2[1]-p1[1])*.35,(p2[0]-p1[0])*.35)
            if end_direction is not None and math.hypot(*t2)<1e-9:
                t2=(-(p3[1]-p2[1])*.35,(p3[0]-p2[0])*.35)
            def tangent(direction):
                return (math.radians(direction[1])*R*self.cos,math.radians(direction[0])*R)
            if i==0 and start_direction is not None: t1=tangent(start_direction)
            if i==len(pts)-2 and end_direction is not None: t2=tangent(end_direction)
            n = max(20, math.ceil(math.dist(p1,p2)/0.75))
            waves = [self.rng.uniform(-1,1) for _ in range(max(2, math.ceil(math.dist(p1,p2)/25)+1))]
            for j in range(n):
                t=j/n
                h=3*t*t-2*t*t*t
                base=[(2*t**3-3*t*t+1)*p1[k]+(t**3-2*t*t+t)*t1[k]+(-2*t**3+3*t*t)*p2[k]+(t**3-t*t)*t2[k] for k in (0,1)]
                d=[(6*t*t-6*t)*p1[k]+(3*t*t-4*t+1)*t1[k]+(-6*t*t+6*t)*p2[k]+(3*t*t-2*t)*t2[k] for k in (0,1)]
                length=math.hypot(*d) or 1
                w=t*(len(waves)-1); wi=min(int(w),len(waves)-2); f=w-wi; f=f*f*(3-2*f)
                noise=waves[wi]*(1-f)+waves[wi+1]*f
                envelope=math.sin(math.pi*t)**2
                offset=(offsets[i]*(1-h)+offsets[i+1]*h)*(1-envelope)+noise*c['jitter']*envelope
                self.points.append((base[0]-d[1]/length*offset,base[1]+d[0]/length*offset))
        self.points.append(pts[-1])
        self.distances=[0.0]
        for a,b in zip(self.points,self.points[1:]):
            self.distances.append(self.distances[-1]+math.dist(a,b))
        self.total=self.distances[-1]

    def xy(self,p):
        return (math.radians(p[1]-self.origin[1])*R*self.cos, math.radians(p[0]-self.origin[0])*R)

    def latlon(self,p):
        return [self.origin[0]+math.degrees(p[1]/R),self.origin[1]+math.degrees(p[0]/(R*self.cos))]

    def at(self,s):
        if s >= self.total: return self.latlon(self.points[-1])
        i=max(0,bisect.bisect_right(self.distances,s)-1)
        f=(s-self.distances[i])/max(1e-9,self.distances[i+1]-self.distances[i])
        return self.latlon(tuple(self.points[i][k]*(1-f)+self.points[i+1][k]*f for k in (0,1)))

    def preview(self):
        step=max(1,len(self.points)//2500)
        return [self.latlon(p) for p in self.points[::step]]+[self.latlon(self.points[-1])]


class Journey:
    """One prefix followed by independently randomized closed laps."""
    def __init__(self, config):
        self.config=validate(config)
        self.loop=bool(config.get('loopEnabled',False))
        self.lap=0
        self.version=0
        self.distance=0.0
        self.travelled=0.0
        self.rng=random.Random()
        if not self.loop:
            self.route=Route(config)
            return
        index=config['loopStart']-1
        self.loop_pins=config['pins'][index:]
        a,b,z=self.loop_pins[0],self.loop_pins[1],self.loop_pins[-1]
        self.direction=((b[0]-z[0])*.35,(b[1]-z[1])*.35)
        if math.hypot(*self.direction)<1e-10:
            # A two-pin loop needs a nonzero shared tangent at the seam.
            cos=math.cos(math.radians(a[0]))
            self.direction=((b[1]-a[1])*cos*.35,-(b[0]-a[0])/cos*.35)
        # Prepare the first lap before touching the phone, validating closure too.
        self.pending=self.new_lap()
        if index:
            self.route=Route({**config,'loopEnabled':False,'pins':config['pins'][:index+1]},end_direction=self.direction)
        else:
            self.route=self.pending
            self.lap=1

    def new_lap(self):
        return Route({**self.config,'loopEnabled':False,'pins':self.loop_pins+[self.loop_pins[0]]},start_direction=self.direction,end_direction=self.direction)

    def advance(self,meters):
        if not self.loop:
            step=min(meters,self.route.total-self.distance)
            self.distance+=step; self.travelled+=step
            return
        self.distance+=meters; self.travelled+=meters
        while self.distance>=self.route.total:
            self.distance-=self.route.total
            self.route=self.pending if self.lap==0 else self.new_lap()
            self.lap+=1
            self.version+=1

    @property
    def holding(self):
        return not self.loop and self.distance>=self.route.total
