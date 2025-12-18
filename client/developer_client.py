import socket
import sys
import os
import json
import time

# Import local utils
from utils import send_json, recv_json

# DEV_HOST = 'linux1.cs.nycu.edu.tw'
# DEV_PORT = 8881
DEV_HOST = 'linux1.cs.nycu.edu.tw'
DEV_PORT = 10191

class DeveloperClient:
    def __init__(self):
        self.session = None # {id, role}
        
    def connect(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((DEV_HOST, DEV_PORT))
            return sock
        except:
            return None

    def start(self):
        print("\n=== Game Store Developer Client ===")
        sock = self.connect()
        if not sock:
            print(f"Error: Cannot connect to Dev Server ({DEV_PORT}).")
            return

        f = sock.makefile('r', encoding='utf-8')
        self.auth_flow(sock, f)
        f.close()
        sock.close()

    def auth_flow(self, sock, f):
        while not self.session:
            print(f"\n--- Developer Login ---")
            print("1. Login")
            print("2. Register")
            print("q. Quit")
            c = input("Select: ").strip()
            
            if c == 'q': return

            if c in ['1', '2']:
                user = input("Username: ").strip()
                if not user: continue
                pwd = input("Password: ").strip()
                
                action = 'login' if c == '1' else 'register'
                req = {
                    "action": action,
                    "role": "dev",
                    "username": user,
                    "password": pwd
                }
                send_json(sock, req)
                
                try:
                     resp = recv_json(f)
                except:
                     print("Server disconnected.")
                     return
                     
                print(f"[{action.title()}] {resp.get('message')}")
                
                if resp.get('status') == 'ok':
                    if action == 'register':
                         # Auto login
                         login_req = {"action": "login", "role": "dev", "username": user, "password": pwd}
                         send_json(sock, login_req)
                         resp = recv_json(f)
                         if resp.get('status') == 'ok':
                             self.session = {"id": user}
                    else:
                        self.session = {"id": user}

        if self.session:
            self.dev_menu(sock, f)

    def dev_menu(self, sock, f):
        while True:
            print(f"\n=== Developer Menu ({self.session['id']}) ===")
            print("1. Upload Game")
            print("2. Update Game")
            print("3. Delete Game")
            print("4. List My Games") 
            print("5. Logout")
            
            c = input("Select: ").strip()
            if c == '5': break
            
            if c == '1':
                name = input("Name: ")
                path = input("Project Path (folder): ")
                if os.path.exists(path) and os.path.isdir(path):
                    self.upload_folder(sock, f, name, path)
                else:
                    print("Invalid folder path.")
                
            elif c == '2':
                gid = input("Game ID: ")
                path = input("New Project Path (folder): ")
                if os.path.exists(path) and os.path.isdir(path):
                     self.update_folder(sock, f, gid, path)
                else: 
                     print("Invalid folder path.")

            elif c == '3':
                gid = input("Game ID: ")
                send_json(sock, {"action": "delete_game", "game_id": gid})
                print(recv_json(f).get('message'))
                
            elif c == '4':
                self.list_my_games(sock, f)

    def _load_metadata(self, path):
        """Helper to load and normalize metadata (handles nested structure)"""
        meta_path = os.path.join(path, 'metadata.json')
        if not os.path.exists(meta_path):
            return {}
        try:
            with open(meta_path, 'r') as f:
                data = json.load(f)
                # Check if user used nested structure
                if 'metadata' in data and isinstance(data['metadata'], dict):
                    return data['metadata']
                return data
        except:
            print("Warning: Could not read metadata.json")
            return {}

    def upload_folder(self, sock, f_in, name, path):
        files_data = {}
        local_meta = self._load_metadata(path)
        
        # Recursively read files
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.startswith('.'): continue
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, path)
                try:
                    with open(abs_path, 'r') as f:
                        files_data[rel_path] = f.read()
                    print(f"Packing: {rel_path} ({len(files_data[rel_path])} bytes)")
                except Exception as e:
                    print(f"Error packing {rel_path}: {e}")

        # Construct payload
        final_meta = {
            "name": name, 
            "version": "1.0", 
            "description": "Uploaded via DevClient", 
            "entry_point": "game_server.py"
        }
        final_meta.update(local_meta) 
        
        final_meta['name'] = name 

        req = {
            "action": "upload_game",
            "metadata": final_meta,
            "file_data": files_data
        }
        send_json(sock, req)
        
        resp = recv_json(f_in)
        print(f"\n>> {resp.get('message')}")
        if resp.get('status') == 'ok':
             print(f">> Game ID format: {self.session['id']}_{name.replace(' ', '_')}")
             print(">> Use 'List My Games' to verify.")

    def update_folder(self, sock, f_in, gid, path):
        files_data = {}
        local_meta = self._load_metadata(path)

        for root, dirs, files in os.walk(path):
            for file in files:
                if file.startswith('.'): continue
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, path)
                try:
                    with open(abs_path, 'r') as f:
                        files_data[rel_path] = f.read()
                    print(f"Packing: {rel_path} ({len(files_data[rel_path])} bytes)")
                except Exception as e:
                     print(f"Error packing {rel_path}: {e}")
                    
        req = {
            "action": "update_game", 
            "game_id": gid, 
            "metadata": local_meta, 
            "file_data": files_data
        }
        if not local_meta:
             req['metadata'] = {"version": str(time.time())}

        send_json(sock, req)
        print(recv_json(f_in).get('message'))

    def list_my_games(self, sock, f_in):
        send_json(sock, {"action": "list_games"})
        resp = recv_json(f_in)
        if resp.get('status') == 'ok':
            games = resp.get('games', {})
            my_games = {k:v for k,v in games.items() if v.get('author') == self.session['id']}
            
            print(f"\n--- My Games ({len(my_games)}) ---")
            for gid, g in my_games.items():
                print(f"ID: {gid} | Name: {g['name']} | v{g['version']}")
        else:
            print("Failed to list games.")

if __name__ == "__main__":
    c = DeveloperClient()
    c.start()
