"""Keep signal warmup separate from funded observations and recovery state."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')


def local_date(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).astimezone(NY).date().isoformat()


def select_window(sessions, signals, start, end_exclusive):
    if date.fromisoformat(start) >= date.fromisoformat(end_exclusive):
        raise ValueError('Empty or reversed funded replay window')
    funded_sessions = []
    for day, quotes, offset in sessions:
        if not start <= day < end_exclusive:
            continue
        if len(quotes):
            for q in (quotes[0], quotes[-1]):
                if local_date(float(q['time_msc']) / 1000 - offset * 3600) != day:
                    raise ValueError('Session label differs from converted New York quote date')
        funded_sessions.append((day, quotes, offset))
    funded_signals = {t: s for t, s in signals.items() if start <= local_date(t) < end_exclusive}
    return funded_sessions, funded_signals


def assert_fills_in_window(fills, start, end_exclusive):
    for fill in fills:
        for key in ['entry_at', 'exit_at']:
            if not start <= local_date(fill[key]) < end_exclusive:
                raise ValueError('Funded fill outside registered evaluation window')
