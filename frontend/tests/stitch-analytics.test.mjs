import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const python=process.env.BTL_RESEARCH_PYTHON??fileURLToPath(new URL('../../backend/venv/Scripts/python.exe',import.meta.url));
const result=spawnSync(python,['-B',fileURLToPath(new URL('../../backend/tests/stitch_analytics.py',import.meta.url))],{stdio:'inherit'});
if(result.error)throw result.error;
if(result.status!==0)process.exit(result.status??1);
