import subprocess
import time
import sys
import signal
import os

# Launcher for Game Store System Servers
# 1. DB Server (8880)
# 2. Dev Server (8881)
# 3. Lobby Server (8888)

processes = []

def start_process(script, name):
    print(f"[Launcher] Starting {name}...")
    p = subprocess.Popen([sys.executable, script], cwd=os.path.dirname(os.path.abspath(__file__)))
    processes.append(p)
    return p

def signal_handler(sig, frame):
    print("\n[Launcher] Shutting down...")
    for p in processes:
        p.terminate()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    
    start_process('db_server.py', 'DB Server')
    time.sleep(1) # Wait for DB to be ready
    
    start_process('dev_server.py', 'Dev Server')
    start_process('lobby_server.py', 'Lobby Server')
    
    print("[Launcher] All servers running. Press Ctrl+C to stop.")
    signal.pause()
