import os, json, base64, sys
from importlib import util

# Create dummy fastapi modules to allow importing main.py in an environment
# without FastAPI installed (we only need consolidate_remote_catalogs)
import types
if 'fastapi' not in sys.modules:
    # minimal fake FastAPI class with decorator methods
    class FakeFastAPI:
        def __init__(self, *a, **k):
            pass
        def on_event(self, *a, **k):
            def _dec(f):
                return f
            return _dec
        def post(self, *a, **k):
            def _dec(f):
                return f
            return _dec
        def get(self, *a, **k):
            def _dec(f):
                return f
            return _dec
    fake_module = types.ModuleType('fastapi')
    setattr(fake_module, 'FastAPI', FakeFastAPI)
    setattr(fake_module, 'Request', object)
    setattr(fake_module, 'BackgroundTasks', object)
    sys.modules['fastapi'] = fake_module
if 'fastapi.responses' not in sys.modules:
    fr = types.ModuleType('fastapi.responses')
    setattr(fr, 'JSONResponse', lambda *a, **k: None)
    sys.modules['fastapi.responses'] = fr

p = os.path.join(os.path.dirname(__file__), 'main.py')
spec = util.spec_from_file_location('tg_main', p)
mod = util.module_from_spec(spec)
spec.loader.exec_module(mod)

token = os.environ.get('GITHUB_TOKEN')
repo = os.environ.get('GITHUB_REPO')
if not token or not repo:
    print('GITHUB_TOKEN and GITHUB_REPO must be set in environment')
    sys.exit(2)

headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}

res = mod.consolidate_remote_catalogs(headers, delete_extra=False)
print(json.dumps(res, indent=2, ensure_ascii=False))
