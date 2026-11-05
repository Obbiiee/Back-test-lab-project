"""DuckDB-only bootstrap; keeps the existing one-day trading engine intact."""
import subprocess
import sys
import os
from pathlib import Path

from tests import qa_historical_day_v2 as historical
from tests import qa_parquet_day_worker as arrow_bootstrap
from tests.qa_duckdb_day_provider import DuckDBDayProvider


def install():
    arrow_bootstrap.ParquetDayProvider = DuckDBDayProvider
    arrow_bootstrap.install()
    original = subprocess.run
    def run(command, *args, **kwargs):
        if isinstance(command,list):
            command=list(command)
            for name in ('tests.qa_historical_day_v2','tests.qa_parquet_day_worker'):
                if name in command:
                    command[command.index(name)]='tests.qa_duckdb_day_worker'
                    # private_postgres resets PYTHONPATH for its own isolated
                    # tools; the cold child needs optional QA readers restored.
                    import pyarrow
                    env = dict(kwargs.get('env',os.environ))
                    env['PYTHONPATH'] = env.get('PYTHONPATH','') + ':' + str(Path(pyarrow.__file__).parents[1])
                    kwargs['env'] = env
        return original(command,*args,**kwargs)
    subprocess.run=run


if __name__=='__main__':
    install()
    if '--worker' in sys.argv:
        historical.main_worker()
    else:
        raise SystemExit(historical.main())
