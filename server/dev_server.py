import socket
import threading
import json
import os
import shutil
import sys

# Ensure we can import utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import send_json, recv_json, DBClient

# Developer Server (Port 8881)
HOST = '0.0.0.0'
# PORT = 8881
PORT = 10191
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../server_data'))
GAMES_DIR = os.path.join(DATA_DIR, 'game_files')
os.makedirs(GAMES_DIR, exist_ok=True)

db = DBClient()

def handle_client(sock, addr):
    print(f"[Dev] New connection from {addr}")
    user_session = {"type": None, "id": None} 
    
    f = sock.makefile('r', encoding='utf-8')

    while True:
        req = recv_json(f)
        if not req: break
        
        action = req.get('action')
        response = {"status": "error", "message": "Unknown action"}
        
        try:
            if action == 'register':
                response = handle_register(req)
            elif action == 'login':
                resp, user_data = handle_login(req)
                response = resp
                if response['status'] == 'ok':
                    user_session = user_data
            
            # Authenticated Actions
            elif action == 'upload_game':
                if user_session['type'] != 'dev':
                    response = {"status": "error", "message": "Unauthorized"}
                else:
                    response = handle_upload_game(req, user_session['id'])
            elif action == 'update_game':
                if user_session['type'] != 'dev':
                    response = {"status": "error", "message": "Unauthorized"}
                else:
                    response = handle_update_game(req, user_session['id'])
            elif action == 'delete_game':
                if user_session['type'] != 'dev':
                    response = {"status": "error", "message": "Unauthorized"}
                else:
                    response = handle_delete_game(req, user_session['id'])
            elif action == 'list_games':
                # Devs might want to see games too
                games = db.get('games') or {}
                response = {"status": "ok", "games": games}

        except Exception as e:
            print(f"[Dev] Error {action}: {e}")
            response = {"status": "error", "message": str(e)}

        send_json(sock, response)

    f.close()
    sock.close()

# --- Logic ---

def handle_register(req):
    username = req.get('username')
    password = req.get('password')
    
    users = db.get('users') or {}
    devs = users.get('devs', {})
    
    if username in devs:
        return {"status": "error", "message": "User exists"}
    
    devs[username] = {"pwd": password, "data": {}}
    users['devs'] = devs
    db.update_all('users', users)
    
    return {"status": "ok", "message": "Registered successfully"}

def handle_login(req):
    username = req.get('username')
    password = req.get('password')
    
    users = db.get('users') or {}
    devs = users.get('devs', {})
    
    if username not in devs or devs[username]['pwd'] != password:
        return {"status": "error", "message": "Invalid credentials"}, None
        
    return {"status": "ok", "token": "dummy"}, {"type": "dev", "id": username}

def handle_upload_game(req, dev_id):
    meta = req.get('metadata')
    game_name = meta.get('name')
    game_id = f"{dev_id}_{game_name.replace(' ', '_')}"
    
    games = db.get('games') or {}
    if game_id in games:
        return {"status": "error", "message": "Game ID exists. Use update."}
        
    file_data = req.get('file_data')
    game_dir = os.path.join(GAMES_DIR, game_id)
    os.makedirs(game_dir, exist_ok=True)
    
    # We trust the uploader to provide valid structure, or we enforce game_server.py
    # Let's NOT force rename arbitrarily anymore, trust the files are named correctly from the template
    for fname, content in file_data.items():
        with open(os.path.join(game_dir, fname), 'w') as f:
            f.write(content)
            
    db.set('games', game_id, {
        "name": game_name,
        "author": dev_id,
        "version": meta.get('version', '1.0'),
        "description": meta.get('description', ''),
        "path": game_dir,
        "entry_point": meta.get('entry_point', 'game_server.py'),
        # Add metadata fields that were previously dropped
        "type": meta.get('type', 'GUI'),
        "max_players": meta.get('max_players', 2),
        "min_players": meta.get('min_players', 2)
    })
    
    return {"status": "ok", "message": f"Game {game_id} uploaded"}

def handle_update_game(req, dev_id):
    game_id = req.get('game_id')
    games = db.get('games') or {}
    
    if game_id not in games:
        return {"status": "error", "message": "Game not found"}
        
    game = games[game_id]
    if game['author'] != dev_id:
        return {"status": "error", "message": "Not your game"}
        
    # Update files
    file_data = req.get('file_data')
    if file_data:
        for fname, content in file_data.items():
            with open(os.path.join(game['path'], fname), 'w') as f:
                f.write(content)
                
    # Update meta
    meta = req.get('metadata', {})
    if 'version' in meta: game['version'] = meta['version']
    if 'description' in meta: game['description'] = meta['description']
    if 'type' in meta: game['type'] = meta['type']
    if 'max_players' in meta: game['max_players'] = meta['max_players']
    if 'min_players' in meta: game['min_players'] = meta['min_players']
    
    db.set('games', game_id, game)
    return {"status": "ok", "message": "Game updated"}

def handle_delete_game(req, dev_id):
    game_id = req.get('game_id')
    games = db.get('games') or {}
    
    if game_id not in games or games[game_id]['author'] != dev_id:
        return {"status": "error", "message": "Cannot delete"}
        
    path = games[game_id]['path']
    if os.path.exists(path):
        shutil.rmtree(path)
        
    db.delete('games', game_id)
    return {"status": "ok", "message": "Game deleted"}

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"[DevServer] Listening on {HOST}:{PORT}")
    
    while True:
        client, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(client, addr))
        t.start()

if __name__ == "__main__":
    start_server()
