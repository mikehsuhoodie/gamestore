import http.server
import socketserver
import json
import os
import sys
import shutil
import socket
import threading
import subprocess
from urllib.parse import urlparse, parse_qs

# Import local utils
from utils import send_json, recv_json

# Config
# DEFAULT_PORT = 8000 
# LOBBY_PORT = 8888
# LOBBY_HOST = 'linux1.cs.nycu.edu.tw'

LOBBY_PORT = 10192
LOBBY_HOST = 'linux1.cs.nycu.edu.tw'

WEB_DIR = os.path.join(os.path.dirname(__file__), 'web')
DOWNLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../downloads'))

# Global State
session = {"id": None, "token": None}

class LobbyConnection:
    def __init__(self):
        self.sock = None
        self.lock = threading.Lock()

    def connect(self):
        if self.sock: return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((LOBBY_HOST, LOBBY_PORT))
            self.file = self.sock.makefile('r', encoding='utf-8')
            print("[LobbyConn] Connected to Lobby Server")
            
            # Auto-Reconnect if we have a token
            if session.get('token'):
                print(f"[LobbyConn] Attempting Session Restore...")
                try:
                    send_json(self.sock, {"action": "reconnect", "token": session['token']})
                    resp = recv_json(self.file)
                    if resp and resp.get('status') == 'ok':
                         print(f"[LobbyConn] Session Restored for {session['id']}")
                    else:
                         print(f"[LobbyConn] Session Restore Failed: {resp}")
                         session['token'] = None # Invalid token
                except Exception as e:
                    print(f"[LobbyConn] Reconnect Error: {e}")
                    
            return True
        except Exception as e:
            print(f"[LobbyConn] Connection Failed: {e}")
            self.sock = None
            self.file = None
            return False

    def send_request(self, payload):
        with self.lock:
            if not self.sock:
                if not self.connect():
                    return {"status": "error", "message": "Lobby Offline"}
            
            try:
                send_json(self.sock, payload)
                
                # Drain events loop
                while True:
                    resp = recv_json(self.file)
                    if not resp:
                        raise Exception("Empty response (connection closed?)")
                        
                    if resp.get('type') == 'event':
                        print(f"[LobbyConn] Ignored Event: {resp.get('event')}")
                        continue
                        
                    return resp
            except Exception as e:
                print(f"[LobbyConn] Error: {e}. Reconnecting...")
                if self.sock: 
                    self.sock.close()
                    if self.file: self.file.close()
                self.sock = None
                self.file = None
                
                # Retry once
                if self.connect():
                    try:
                        send_json(self.sock, payload)
                        return recv_json(self.file)
                    except:
                        pass
                
                return {"status": "error", "message": "Connection Lost"}
    
    def get_id(self):
        return id(self.sock)

lobby_conn = LobbyConnection()

def lobby_req(payload):
    return lobby_conn.send_request(payload)

class GameHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress logging
        pass

    def do_GET(self):
        # Serve API GETs
        if self.path.startswith('/api'):
            self.handle_api_get()
        else:
            # Serve Static Files
            if self.path == '/': self.path = '/index.html'
            return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        if self.path.startswith('/api'):
            length = int(self.headers['Content-Length'])
            body = json.loads(self.rfile.read(length).decode())
            res = self.handle_api_post(self.path, body)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode())

    def _send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def handle_api_get(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == '/api/games':
            resp = lobby_req({"action": "list_games"})
            self._send_json(resp)
            
        elif path == '/api/library':
            self._handle_library()
            
        elif path == '/api/rooms':
            resp = lobby_req({"action": "list_rooms"})
            self._send_json(resp)
            
        elif path == '/api/room/info':
            rid = qs.get('room_id', [None])[0]
            resp = lobby_req({"action": "get_room_info", "room_id": rid})
            self._send_json(resp)
            
        elif path == '/api/reviews':
            gid = qs.get('game_id', [None])[0]
            print(f"[Client] Fetching reviews for GID: {gid}")
            resp = lobby_req({"action": "get_reviews", "game_id": gid})
            print(f"[Client] Review Response: {resp}")
            self._send_json(resp)

    def handle_api_post(self, path, body):
        if path == '/api/login' or path == '/api/register':
            action = 'login' if 'login' in path else 'register'
            req = {
                "action": action,
                "role": "player", 
                "username": body.get('username'), 
                "password": body.get('password')
            }
            resp = lobby_req(req)
            if resp.get('status') == 'ok':
                session['id'] = body.get('username')
                session['token'] = resp.get('token')
                # For register, auto login is simulated by just setting session
            return resp

        if path == '/api/install':
             return self._handle_install(body.get('game_id'))
             
        if path == '/api/launch':
             return self._handle_launch(body.get('game_id'), body.get('port'))

        if path == '/api/room/create':
             if not session['id']: return {"status": "error", "message": "Login Required"}
             body['action'] = 'create_room'
             body['user_id'] = session['id'] # Inject Session ID
             return lobby_req(body)
             
        if path == '/api/room/join':
             if not session['id']: return {"status": "error", "message": "Login Required"}
             body['action'] = 'join_room'
             body['user_id'] = session['id'] # Inject Session ID
             return lobby_req(body)

        if path == '/api/room/start':
             if not session['id']: return {"status": "error", "message": "Login Required"}
             body['action'] = 'start_game'
             return lobby_req(body)
             
        if path == '/api/room/leave':
             if not session['id']: return {"status": "error", "message": "Login Required"}
             body['action'] = 'leave_room'
             return lobby_req(body)

        if path == '/api/review/add':
             if not session['id']: return {"status": "error", "message": "Login Required"}
             body['action'] = 'add_review'
             body['user_id'] = session['id']
             return lobby_req(body)

        return {"status": "error", "message": "Unknown Endpoint"}

    def _handle_library(self):
        # Scan local files
        uid = session['id']
        if not uid: 
            self._send_json({"status": "error", "message": "Not logged in"})
            return

        root = os.path.join(DOWNLOAD_DIR, uid)
        games = []
        if os.path.exists(root):
            # Fetch valid games from server to sync
            valid_games_resp = lobby_req({"action": "list_games"})
            valid_ids = set()
            if valid_games_resp.get('status') == 'ok':
                valid_ids = set(valid_games_resp['games'].keys())
                
                # Cleanup deleted games
                for d in os.listdir(root):
                    # d should be game_id
                    if d not in valid_ids:
                        print(f"[Library] Removing deleted game: {d}")
                        shutil.rmtree(os.path.join(root, d))
                        continue
                        
            for d in os.listdir(root):
                meta_path = os.path.join(root, d, '.meta')
                if os.path.exists(meta_path):
                    with open(meta_path, 'r') as f:
                        data = json.load(f)
                        
                        # Double check if server still has it (in case list failed but folder exists)
                        # If list succeded, we already cleaned up. 
                        # If list failed, valid_ids is empty, we skipped cleanup? 
                        # Wait, if list failed, we shouldn't delete everything. 
                        # My logic above: if status == 'ok', then valid_ids populated.
                        # If status != 'ok', valid_ids empty, we skip cleanup loop. SAFE.
                        
                        # Check update
                        update = False
                        svr_game = lobby_req({"action": "get_game_info", "game_id": data['id']})
                        if svr_game.get('status') == 'ok':
                            if svr_game['data'].get('version') != data.get('version'):
                                update = True
                        data['update_available'] = update
                        games.append(data)
        
        self._send_json({"status": "ok", "games": games})

    def _handle_install(self, gid):
        if not session['id']: return {"status": "error", "message": "Login Required"}
        
        # Get Info first
        g_info = lobby_req({"action": "get_game_info", "game_id": gid})
        if g_info.get('status') != 'ok': return g_info
        game_meta = g_info['data']
        
        # Download
        d_resp = lobby_req({"action": "download_game", "game_id": gid})
        if d_resp.get('status') != 'ok': return d_resp
        
        # Save
        user_dir = os.path.join(DOWNLOAD_DIR, session['id'], gid)
        if os.path.exists(user_dir): shutil.rmtree(user_dir)
        os.makedirs(user_dir, exist_ok=True)
        
        files = d_resp.get('files', {})
        for fname, content in files.items():
            with open(os.path.join(user_dir, fname), 'w') as f:
                f.write(content)
                
        # Save .meta
        meta = {
            "id": gid, 
            "name": game_meta['name'],
            "version": game_meta.get('version', '1.0'),
            "type": game_meta.get('type', 'GUI'),
            "entry_point": "game_client.py"
        }
        with open(os.path.join(user_dir, '.meta'), 'w') as f:
            json.dump(meta, f)
            
        return {"status": "ok"}

    def _handle_launch(self, gid, port):
        uid = session['id']
        game_dir = os.path.join(DOWNLOAD_DIR, uid, gid)
        
        try:
            with open(os.path.join(game_dir, '.meta'), 'r') as f:
                meta = json.load(f)
                game_type = meta.get('type', 'GUI')
        except:
             return {"status": "error", "message": "Game corrupted"}

        script_path = os.path.join(game_dir, "game_client.py")
        if not os.path.exists(script_path):
             return {"status": "error", "message": "Client script missing"}
             
        cmd = [sys.executable, script_path, "--ip", LOBBY_HOST, "--port", str(port), "--username", uid]
        
        # Launch Logic
        try:
            # Check for terminal availability
            found_terminal = False
            for term in ['gnome-terminal', 'x-terminal-emulator', 'xterm', 'konsole', 'xfce4-terminal']:
                if shutil.which(term):
                    found_terminal = term
                    break
            
            if game_type == 'CLI':
                 if found_terminal == 'gnome-terminal':
                    subprocess.Popen(['gnome-terminal', '--'] + cmd)
                 elif found_terminal:
                    subprocess.Popen([found_terminal, '-e'] + cmd)
                 else:
                    # Fallback to inline execution if no terminal emulator found
                    print("[Launcher] Warning: No terminal emulator found. Running inline.")
                    subprocess.Popen(cmd)
            else:
                subprocess.Popen(cmd)
                
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

# Change dir to serve static content easily
os.chdir(WEB_DIR)

# Auto-increment Port Logic
if __name__ == '__main__':
    import argparse
    import webbrowser
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()
    
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
        allow_reuse_address = True
        daemon_threads = True

    # Try ports
    start_port = args.port
    max_retries = 20
    final_port = None
    httpd = None

    for i in range(max_retries):
        port = start_port + i
        try:
            httpd = ThreadingHTTPServer(("", port), GameHandler)
            final_port = port
            break
        except OSError as e:
            if "Address already in use" in str(e) or e.errno == 98:
                print(f"Port {port} in use, trying next...")
                continue
            else:
                print(f"Failed to bind port {port}: {e}")
                sys.exit(1)
    
    if httpd and final_port:
        print(f"Lobby Client starting on http://localhost:{final_port}...")
        
        # Auto-open browser
        try:
            webbrowser.open(f"http://localhost:{final_port}")
        except:
            pass

        try:
             print("Server running... (Ctrl+C to stop)")
             httpd.serve_forever()
        except KeyboardInterrupt:
             print("\nStopping...")
             httpd.shutdown()
    else:
        print(f"Could not find an open port after {max_retries} attempts.")
        sys.exit(1)
