import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
// BTL_RESEARCH_PYTHON wins; otherwise the backend venv's interpreter for this platform.
const python=process.env.BTL_RESEARCH_PYTHON??fileURLToPath(new URL(process.platform==='win32'?'../../backend/venv/Scripts/python.exe':'../../backend/venv/bin/python',import.meta.url));
const result=spawnSync(python,['-B',fileURLToPath(new URL('../../backend/tests/stitch_analytics.py',import.meta.url))],{stdio:'inherit'});
if(result.error)throw result.error;
if(result.status!==0)process.exit(result.status??1);
