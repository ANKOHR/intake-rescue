import os
import sys
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from config import load, ROOT
load()
os.chdir(ROOT)
import uvicorn
uvicorn.run('app.main:create_app',factory=True,host=os.environ.get('IR_BIND','127.0.0.1'),port=int(os.environ.get('IR_PORT','8765')),access_log=False)
