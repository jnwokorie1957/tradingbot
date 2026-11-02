"""Scoped AC-only idle-sleep request for an already verified paper worker.

No broker connection, strategy import, power-plan change, display request,
restart or manual-sleep override. Lease ends on worker exit, stop file or expiry.
"""
import argparse,ctypes,json,os,time
from ctypes import wintypes
from datetime import datetime,timezone
from pathlib import Path

CONTINUOUS=0x80000000
SYSTEM_REQUIRED=0x00000001


class PowerStatus(ctypes.Structure):
    _fields_=[('ACLineStatus',wintypes.BYTE),('BatteryFlag',wintypes.BYTE),('BatteryLifePercent',wintypes.BYTE),('SystemStatusFlag',wintypes.BYTE),('BatteryLifeTime',wintypes.DWORD),('BatteryFullLifeTime',wintypes.DWORD)]


def should_hold(ac,worker_alive,expired,stop_requested):
    return ac==1 and worker_alive and not expired and not stop_requested


def atomic(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2),encoding='utf-8');tmp.replace(path)


def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=int,required=True);p.add_argument('--state',type=Path,required=True);p.add_argument('--hours',type=float,default=8.);a=p.parse_args()
    if os.name!='nt':raise RuntimeError('Windows-only request')
    if not 0<a.hours<=24:raise ValueError('Lease duration must be positive and at most24 hours')
    k=ctypes.WinDLL('kernel32',use_last_error=True);k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
    k.CloseHandle.argtypes=[wintypes.HANDLE];k.CloseHandle.restype=wintypes.BOOL
    k.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4;k.GetProcessTimes.restype=wintypes.BOOL
    k.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];k.GetExitCodeProcess.restype=wintypes.BOOL
    k.SetThreadExecutionState.argtypes=[wintypes.DWORD];k.SetThreadExecutionState.restype=wintypes.DWORD
    k.GetSystemPowerStatus.argtypes=[ctypes.POINTER(PowerStatus)];k.GetSystemPowerStatus.restype=wintypes.BOOL
    k.CreateMutexW.argtypes=[wintypes.LPVOID,wintypes.BOOL,wintypes.LPCWSTR];k.CreateMutexW.restype=wintypes.HANDLE
    worker=k.OpenProcess(0x1000,False,a.worker)
    if not worker:raise ctypes.WinError(ctypes.get_last_error())
    times=[wintypes.FILETIME() for _ in range(4)]
    if not k.GetProcessTimes(worker,*[ctypes.byref(t) for t in times]):raise ctypes.WinError(ctypes.get_last_error())
    creation=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime;ctypes.set_last_error(0);mutex=k.CreateMutexW(None,True,f'Local\\AtlasPaperPowerLease_{a.worker}_{creation}')
    if not mutex:raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error()==183:k.CloseHandle(mutex);k.CloseHandle(worker);raise SystemExit('An existing lease already owns this worker identity')
    a.state.mkdir(parents=True,exist_ok=True);stop=a.state/'stop.request';start=time.time();end=start+a.hours*3600;held=False;reason='stopped';record={}
    try:
        while True:
            now=time.time();exitcode=wintypes.DWORD()
            if not k.GetExitCodeProcess(worker,ctypes.byref(exitcode)):raise ctypes.WinError(ctypes.get_last_error())
            alive=exitcode.value==259;power=PowerStatus()
            if not k.GetSystemPowerStatus(ctypes.byref(power)):raise ctypes.WinError(ctypes.get_last_error())
            expired=now>=end;requested=stop.exists();desired=should_hold(power.ACLineStatus,alive,expired,requested)
            if desired!=held:
                if not k.SetThreadExecutionState(CONTINUOUS|SYSTEM_REQUIRED if desired else CONTINUOUS):raise ctypes.WinError(ctypes.get_last_error())
                held=desired
            record=dict(updated_utc=datetime.now(timezone.utc).isoformat(),helper_pid=os.getpid(),worker_pid=a.worker,worker_creation_filetime=creation,started_utc=datetime.fromtimestamp(start,timezone.utc).isoformat(),expires_utc=datetime.fromtimestamp(end,timezone.utc).isoformat(),AC_line_status=power.ACLineStatus,battery_percent=power.BatteryLifePercent,system_idle_request_active=held,status='ac_idle_request_active' if held else 'waiting_for_AC_power',power_plan_changed=False,display_request=False,broker_connections=0,paper_only=True,manual_sleep_or_lid_close_respected=True)
            if not alive or expired or requested:
                reason='worker_exited' if not alive else 'lease_expired' if expired else 'stop_requested';break
            atomic(a.state/'status.json',record);time.sleep(15)
    except Exception as exc:
        reason='failed';record.update(error_type=type(exc).__name__,error=str(exc));raise
    finally:
        # Clearing this thread's request restores ordinary idle behavior; it
        # changes no global timer and cannot override deliberate user sleep.
        cleared=bool(k.SetThreadExecutionState(CONTINUOUS));record.update(status=reason,system_idle_request_active=False,request_cleared=cleared,updated_utc=datetime.now(timezone.utc).isoformat());atomic(a.state/'status.json',record);k.CloseHandle(worker);k.CloseHandle(mutex)


if __name__=='__main__':main()
