"""One-day QA bootstrap; hooks only the private historical runner."""
import json
import os
from pathlib import Path
import subprocess
import sys

from tests import qa_historical_day_v2 as historical
from tests.qa_parquet_day_provider import ParquetDayProvider, file_sha


def install():
    layout = os.environ['BTL_PARQUET_DAY_LAYOUT']
    manifest_path = Path(os.environ['BTL_PARQUET_DAY_MANIFEST'])
    if file_sha(manifest_path) != os.environ['BTL_PARQUET_DAY_MANIFEST_SHA256']:
        raise RuntimeError('DAY_MANIFEST_CHANGED')
    manifest = json.loads(manifest_path.read_text())
    original_load = historical.load_source
    def load(*args, **kwargs):
        source = original_load(*args, **kwargs)
        log_root = Path(args[4] if len(args)>4 else kwargs['log_root'])
        # The independent financial verifier always traverses original SQLite.
        if layout != 'sqlite' and log_root.name != 'source-logs-independent':
            def provider():
                source.assert_current()
                return ParquetDayProvider(args[1],source.version,manifest,layout)
            source.provider = provider
        return source
    historical.load_source = load
    historical.MIN_FREE = int(32.5*1024**3)
    historical.MAX_RAM = 896*1024**2
    original_run = subprocess.run
    def run(command,*args,**kwargs):
        if isinstance(command,list) and 'tests.qa_historical_day_v2' in command:
            command=list(command)
            command[command.index('tests.qa_historical_day_v2')]='tests.qa_parquet_day_worker'
            import pyarrow
            env = dict(kwargs.get('env', os.environ))
            env['PYTHONPATH'] = env.get('PYTHONPATH','') + ':' + str(Path(pyarrow.__file__).parents[1])
            kwargs['env'] = env
        return original_run(command,*args,**kwargs)
    subprocess.run = run


if __name__ == '__main__':
    install()
    if '--worker' in sys.argv:
        historical.main_worker()
    else:
        raise SystemExit(historical.main())
