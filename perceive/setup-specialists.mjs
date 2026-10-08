import {spawnSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {homedir} from 'node:os';
import {fileURLToPath} from 'node:url';
process.chdir(fileURLToPath(new URL('.',import.meta.url)));
const candidates=[process.env.ANIMA_PYTHON,'python3.12','python3.11','python3',homedir()+'/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'].filter(Boolean);
const python=candidates.find(command=>spawnSync(command,['-c','import sys; sys.exit(0 if (3,11)<=sys.version_info[:2]<(3,13) else 1)'],{stdio:'ignore'}).status===0);
if(!python)throw new Error('需要 Python 3.11 或 3.12；可通过 ANIMA_PYTHON 指定已有安装。');
const run=(command,args)=>{const r=spawnSync(command,args,{stdio:'inherit'});if(r.status!==0)throw new Error('安装未完成，请检查上方错误。');};
if(!existsSync('integrations/.venv/bin/python'))run(python,['-m','venv','integrations/.venv']);
const local='integrations/.venv/bin/python';
run(local,['-m','pip','install','-r','integrations/requirements.lock']);
// Upstream metadata bundles incompatible duplicate OpenCV pins. All imported
// dependencies are pinned in requirements.lock; install the official package alone.
run(local,['-m','pip','install','--no-deps','openface-test==0.1.26']);
run(local,['integrations/setup.py']);
console.log('面部与声音模型已安装。重新启动 Anima 后自动加载。');
