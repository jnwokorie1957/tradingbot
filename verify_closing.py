import json,time,unittest
from pathlib import Path
suite=unittest.defaultTestLoader.discover('tests');start=time.monotonic();r=unittest.TextTestRunner(verbosity=1).run(suite)
Path('CLOSING-TEST-RESULT.json').write_text(json.dumps(dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped),elapsed_seconds=round(time.monotonic()-start,3),passed=r.wasSuccessful(),synthetic_only=True),indent=2)+'\n')
raise SystemExit(not r.wasSuccessful())
