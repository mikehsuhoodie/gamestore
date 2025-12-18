import socket
import threading
import json
import os
import sys

# DB Server (Port 8880)
# Responsibilities:
# - Maintain in-memory state of users, games, rooms, reviews
# - Persist to JSON files
# - Handle requests from DevServer (8881) and LobbyServer (8888)

HOST = '127.0.0.1' # Internal only
PORT = 10195
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../server_data'))

os.makedirs(DATA_DIR, exist_ok=True)

class DBManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.files = {
            'users': os.path.join(DATA_DIR, 'users.json'),
            'games': os.path.join(DATA_DIR, 'games.json'),
            'rooms': os.path.join(DATA_DIR, 'rooms.json'),
            'reviews': os.path.join(DATA_DIR, 'reviews.json')
        }
        self.data = {}
        for k in self.files:
            self.data[k] = self._load(k)
            
    def _load(self, key):
        if not os.path.exists(self.files[key]):
            return {}
        try:
            with open(self.files[key], 'r') as f:
                return json.load(f)
        except:
            return {}

    def _save(self, key):
        with open(self.files[key], 'w') as f:
            json.dump(self.data[key], f, indent=2)

    def get(self, collection, key=None):
        with self.lock:
            if collection not in self.data: return None
            if key:
                return self.data[collection].get(key)
            return self.data[collection]

    def set(self, collection, key, value):
        with self.lock:
            if collection not in self.data: return False
            self.data[collection][key] = value
            self._save(collection)
            return True
            
    def delete(self, collection, key):
        with self.lock:
            if collection not in self.data: return False
            if key in self.data[collection]:
                del self.data[collection][key]
                self._save(collection)
                return True
            return False
            
    def update_all(self, collection, new_data):
        with self.lock:
            if collection not in self.data: return False
            self.data[collection] = new_data
            self._save(collection)
            return True

db = DBManager()

def handle_client(sock, addr):
    while True:
        try:
            data = sock.recv(4096).decode()
            if not data: break
            
            # Expecting separate JSONs per line or huge buffer? 
            # For simplicity, assuming request fits in buffer or line delimited
            # Using simple JSON per connection request for internal services
            
            req = json.loads(data)
            action = req.get('action')
            collection = req.get('collection')
            
            # --- LOGGING ADDED ---
            key_info = f" key={req.get('key')}" if req.get('key') else ""
            print(f"[DB] {action} {collection}{key_info}")
            # ---------------------
            
            resp = {"status": "error"}
            
            if action == 'GET':
                 res = db.get(collection, req.get('key'))
                 resp = {"status": "ok", "data": res}
                 
            elif action == 'SET':
                 db.set(collection, req.get('key'), req.get('value'))
                 resp = {"status": "ok"}
                 
            elif action == 'UPDATE_ALL':
                 db.update_all(collection, req.get('data'))
                 resp = {"status": "ok"}
                 
            elif action == 'DELETE':
                 db.delete(collection, req.get('key'))
                 resp = {"status": "ok"}
            
            sock.sendall(json.dumps(resp).encode())
            
        except Exception as e:
            # print(f"DB Error: {e}")
            break
    sock.close()

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"[DB] Listening on {HOST}:{PORT}")
    
    while True:
        client, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(client, addr))
        t.start()

if __name__ == "__main__":
    start_server()
