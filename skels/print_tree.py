import re, sys
def load(path):
    joints={}; nv={}
    for line in open(path):
        m=re.match(r"SKELDUMP: joint=(\d+) parent=(-?\d+) world=\(([-\d.]+),([-\d.]+),([-\d.]+)\).*dl=(0x[0-9a-f]+)", line)
        if m:
            j=int(m.group(1)); joints[j]=(int(m.group(2)), float(m.group(3)), float(m.group(4)), float(m.group(5)), m.group(6)!="0x0")
        m=re.match(r"MESHDUMP: joint=(\d+) nverts=(\d+)", line)
        if m: nv[int(m.group(1))]=int(m.group(2))
    return joints, nv
def show(path):
    joints,nv=load(path)
    kids={}
    for j,(p,*_) in joints.items(): kids.setdefault(p,[]).append(j)
    def rec(j,d):
        p,x,y,z,dv=joints[j]
        print(f"{'  '*d}{j}: y={y:7.0f} lat={z:6.0f} fwd={x+2400:6.0f} {'dv('+str(nv.get(j,'?'))+'v)' if dv else '-'}")
        for c in sorted(kids.get(j,[])): rec(c,d+1)
    rec(0,0)
show(sys.argv[1])
