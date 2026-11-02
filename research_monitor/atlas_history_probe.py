"""Bounded read-only availability/contract evidence. Never authentication or orders."""
import argparse,json,hashlib
from datetime import datetime,timezone,timedelta
from pathlib import Path
import MetaTrader5 as mt5
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);root=p.parse_args().root;out=root/'outputs/atlas_risk_audit_v1';out.mkdir(exist_ok=True)
    evidence=dict(captured_utc=datetime.now(timezone.utc).isoformat(),operation='Existing-session metadata and bounded history requests only;no order_send/order_check/login or settings mutation',probes=[])
    if not mt5.initialize(r'C:\Program Files\MetaTrader 5\terminal64.exe',timeout=15000):
        evidence.update(connected=False,error=mt5.last_error());(out/'availability.json').write_text(json.dumps(evidence,indent=2));return
    try:
        terminal=mt5.terminal_info();account=mt5.account_info();evidence.update(connected=bool(terminal.connected),algorithmic_trading_allowed=bool(terminal.trade_allowed),account_trade_mode=int(account.trade_mode),account_currency=account.currency,margin_mode=int(account.margin_mode),terminal_maxbars=int(terminal.maxbars),symbols={})
        for symbol in ['NAS100','SPX500']:
            info=mt5.symbol_info(symbol);quote=mt5.symbol_info_tick(symbol);meta={k:getattr(info,k) for k in ['point','digits','trade_tick_size','trade_tick_value_loss','trade_tick_value_profit','trade_contract_size','volume_min','volume_step','volume_max','trade_stops_level','trade_freeze_level','swap_long','swap_short','currency_profit','currency_margin']}
            meta.update(current_quote_raw_epoch=quote.time,current_minlot_margin=mt5.order_calc_margin(mt5.ORDER_TYPE_BUY,symbol,meta['volume_min'],quote.ask),margin_quote=quote.ask,historical_applicability='Unverified;current read-only snapshot is not historical account evidence');evidence['symbols'][symbol]=meta
            for day in ['2025-06-02','2025-11-24','2025-12-11']:
                start=datetime.fromisoformat(day).replace(hour=15,tzinfo=timezone.utc);end=start+timedelta(hours=1);q=mt5.copy_ticks_range(symbol,start,end,mt5.COPY_TICKS_ALL);error=mt5.last_error();row=dict(symbol=symbol,requested_raw_start=start.isoformat(),requested_raw_end=end.isoformat(),error=error,rows=0 if q is None else len(q))
                if q is not None and len(q):
                    valid=q[(q['time_msc']>=int(start.timestamp()*1000))&(q['time_msc']<int(end.timestamp()*1000))&(q['bid']>0)&(q['ask']>=q['bid'])];f=out/f'probe_{symbol}_{day}.npz';np.savez_compressed(f,quotes=q);row.update(valid_rows=len(valid),first_raw_msc=int(q['time_msc'][0]),last_raw_msc=int(q['time_msc'][-1]),sha256=hashlib.sha256(f.read_bytes()).hexdigest())
                evidence['probes'].append(row);(out/'availability.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(row),flush=True)
        evidence['conclusion']='Availability probes only;do not score strategies or treat a one-hour probe as a complete validation period. All previously exposed dates remain ineligible for untouched validation.'
        (out/'availability.json').write_text(json.dumps(evidence,indent=2))
    finally:mt5.shutdown()


if __name__=='__main__':main()
