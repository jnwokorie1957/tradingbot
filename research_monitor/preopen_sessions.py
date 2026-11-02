"""Exact historical quote working set with explicit earlier-session eligibility."""
import json,hashlib
from datetime import datetime,timezone
import numpy as np
from .audited_run import NY

def load_sessions(folders,first='2025-12-15',last_exclusive='2026-10-31',open_clock=540):
    sessions=[]
    for folder in folders:
        for r in json.loads((folder/'manifest.json').read_text()):
            if not first<=r['date']<last_exclusive:continue
            f=folder/'quotes'/f"{r['date']}.npz"
            if not f.exists():continue
            assert hashlib.sha256(f.read_bytes()).hexdigest()==r['sha256'];local=datetime.fromisoformat(r['date']).replace(hour=10,tzinfo=NY);offset=3 if local.dst() else 2
            lo=(local.replace(hour=open_clock//60,minute=open_clock%60).astimezone(timezone.utc).timestamp()+offset*3600)*1000;hi=(local.replace(hour=16,minute=0).astimezone(timezone.utc).timestamp()+offset*3600)*1000
            raw=np.load(f)['quotes'];raw=raw[(raw['time_msc']>=int(lo))&(raw['time_msc']<=int(hi))];q=np.empty(len(raw),dtype=[('time_msc','i8'),('bid','f8'),('ask','f8')])
            for key in q.dtype.names:q[key]=raw[key]
            sessions.append((r['date'],q,offset))
    assert all(b[0]>a[0] for a,b in zip(sessions,sessions[1:]));return sessions
