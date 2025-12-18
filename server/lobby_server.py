import socket
import threading
import json
import os
import shutil
import sys
import uuid
import subprocess

# Ensure we can import utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import send_json, recv_json, DBClient

# Lobby Server (Port 8888)
HOST = '0.0.0.0'
# PORT = 8888
PORT = 10192
db = DBClient()

# Global Lock for DB Transactions
# Global Lock for DB Transactions
lock = threading.RLock()

# Process Registry: {room_id: subprocess.Popen}
running_games = {}
running_games_lock = threading.RLock()
pending_crashes = {} # {rid: timestamp} to track potential crashes with grace period
import time

def monitor_game_processes():
    """
    Background thread to monitor running game processes:
    1. Reaps zombies (proc.poll())
    2. Detects crashes (process ended but room status is 'playing')
    3. Resets room status if crashed
    """
    while True:
        time.sleep(1.0)
        with running_games_lock:
            # Create a list of (rid, proc) to iterate safely
            current_games = list(running_games.items())
            
        for rid, proc in current_games:
            ret = proc.poll()
            if ret is not None:
                # Process has ended
                print(f"[Lobby Monitor] Game Process for Room {rid} ended with code {ret}")
                
                # Check room status
                with lock:
                    rooms = db.get('rooms') or {}
                    if rid in rooms:
                        room = rooms[rid]
                        if room['status'] == 'playing':
                             # Check Grace Period
                             now = time.time()
                             if rid not in pending_crashes:
                                  print(f"[{now:.4f}] [Lobby Monitor] Process End Detected for Room {rid}. Starting Grace Period.")
                                  pending_crashes[rid] = now
                                  continue # Skip cleanup, wait for next tick
                             
                             if now - pending_crashes[rid] < 3.0:
                                  # Still in grace period
                                  continue

                             print(f"[{now:.4f}] [Lobby Monitor] CRASH CONFIRMED for Room {rid}. Resetting to idle.")
                             # Game crashed without reporting result.
                             # Reset room, remove players? or state migration?
                             # For now: Reset to idle so it's not stuck.
                             room['status'] = 'idle'
                             room.pop('port', None)
                             
                             # Notify players of crash?
                             msg = {"type": "event", "event": "game_over", "winner": "None", "reason": "Server Crashed"}
                             for p in room['players']:
                                 broadcast_to_user(p, msg)
                                 
                             db.update_all('rooms', rooms)
                             
                             if rid in pending_crashes: del pending_crashes[rid]
                
                # Cleanup registry
                with running_games_lock:
                    if rid in running_games:
                        del running_games[rid]
                        print(f"[{time.time():.4f}] [Lobby Monitor] Cleaned up Process {rid}")

def handle_client(sock, addr):
    print(f"[Lobby] New connection from {addr}")
    user_session = {"type": None, "id": None} 
    
    f = sock.makefile('r', encoding='utf-8')

    while True:
        req = recv_json(f)
        if not req: 
            # Cleanup on disconnect
            if user_session['id']:
                handle_disconnect(user_session['id'])
            break
        
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
                    register_online_user(user_session['id'], sock)
            
            elif action == 'reconnect':
                 resp, user_data = handle_reconnect(req)
                 response = resp
                 if response['status'] == 'ok':
                     user_session = user_data
                     register_online_user(user_session['id'], sock)
            
            elif action == 'logout':
                if user_session['id']:
                    handle_disconnect(user_session['id'])
                    user_session = {"type": None, "id": None}
                response = {"status": "ok"}
            
            # Lobby Actions
            
            elif action == 'list_games':
                 games = db.get('games') or {}
                 response = {"status": "ok", "games": games}
                 
            elif action == 'get_game_info':
                 games = db.get('games') or {}
                 gid = req.get('game_id')
                 if gid in games:
                     response = {"status": "ok", "data": games[gid]}
                 else:
                     response = {"status": "error", "message": "Not found"}

            elif action == 'download_game':
                 response = handle_download_game(req)

            elif action == 'create_room':
                if not user_session['id']:
                    response = {"status": "error", "message": "Login required"}
                else:
                    response = handle_create_room(req, user_session['id'])

            elif action == 'list_rooms':
                 rooms = db.get('rooms') or {}
                 response = {"status": "ok", "rooms": rooms}
                 
            elif action == 'join_room':
                if not user_session['id']:
                    response = {"status": "error", "message": "Login required"}
                else:
                    response = handle_join_room(req, user_session['id'])
                    
            elif action == 'get_room_info':
                 rooms = db.get('rooms') or {}
                 rid = req.get('room_id')
                 if rid in rooms:
                     response = {"status": "ok", "room": rooms[rid]}
                 else:
                     response = {"status": "error", "message": "Room not found"}
            
            elif action == 'get_reviews':
                 reviews = db.get('reviews') or {}
                 gid = req.get('game_id')
                 response = {"status": "ok", "reviews": reviews.get(gid, [])}
            
            elif action == 'add_review':
                 if user_session['type'] != 'player':
                      response = {"status": "error", "message": "Access denied"}
                 else:
                       response = handle_add_review(req, user_session['id'])

            elif action == 'leave_room':
                 if not user_session['id']:
                      response = {"status": "error", "message": "Login required"}
                 else:
                      response = handle_leave_room(req, user_session['id'])

            elif action == 'start_game':
                 if not user_session['id']:
                      response = {"status": "error", "message": "Login required"}
                 else:
                      response = handle_start_game(req, user_session['id'])

            elif action == 'game_result':
                 # Internal action from Game Server
                 response = handle_game_result(req)

        except Exception as e:
            print(f"[Lobby] Error {action}: {e}")
            response = {"status": "error", "message": str(e)}

        send_json(sock, response)

    f.close()
    sock.close()

# --- Online Users & Broadcast ---
online_users = {} # {user_id: socket}
active_tokens = {} # {token: user_session}

def register_online_user(uid, sock):
    with lock:
        online_users[uid] = sock
        print(f"[Lobby] User {uid} online")

def handle_disconnect(uid):
    with lock:
        if uid in online_users:
            del online_users[uid]
            print(f"[Lobby] User {uid} offline")
            
        # Potentially clean up rooms if host disconnects?
        # For HW simplicity, we keep room but maybe mark user as away?
        # Or if in 'waiting' room, leave it.
        rooms = db.get('rooms') or {}
        dirty = False
        # Use list(rooms.items()) to safely modify dict while iterating
        for rid, r in list(rooms.items()):
            if uid in r['players'] and r['status'] == 'waiting':
                r['players'].remove(uid)
                dirty = True
                
                if len(r['players']) == 0:
                    del rooms[rid]
                    continue
                
                # Host Migration
                if r['host'] == uid:
                    r['host'] = r['players'][0]
                    print(f"[Lobby] Room {rid} Host migrated to {r['host']}")
                    
                # Broadcast update
                broadcast_room_update(r)
                
        if dirty: 
            db.update_all('rooms', rooms)

def broadcast_room_update(room):
    # Sends "room_update" event to all players in the room
    msg = {
        "type": "event",
        "event": "room_update",
        "room": room
    }
    for p in room['players']:
        broadcast_to_user(p, msg)

def broadcast_to_user(uid, msg):
    # Sends an async message to a connected user (Push Notification)
    with lock:
        if uid in online_users:
            try:
                send_json(online_users[uid], msg)
            except:
                pass # Socket dead, will be cleaned up by receive loop

# --- Logic ---

def handle_register(req):
    username = req.get('username')
    password = req.get('password')
    users = db.get('users') or {}
    players = users.get('players', {})
    
    if username in players:
        return {"status": "error", "message": "User exists"}
    
    players[username] = {"pwd": password, "data": {}}
    users['players'] = players
    db.update_all('users', users)
    return {"status": "ok", "message": "Registered successfully"}

def handle_login(req):
    username = req.get('username')
    password = req.get('password')
    users = db.get('users') or {}
    players = users.get('players', {})
    
    if username not in players or players[username]['pwd'] != password:
        return {"status": "error", "message": "Invalid"}, None
        
    token = str(uuid.uuid4())
    user_data = {"type": "player", "id": username}
    
    with lock:
        active_tokens[token] = user_data
        
    return {"status": "ok", "token": token}, user_data

def handle_reconnect(req):
    token = req.get('token')
    with lock:
        if token in active_tokens:
            return {"status": "ok", "message": "Session restored"}, active_tokens[token]
    return {"status": "error", "message": "Invalid token"}, None

def handle_download_game(req):
    gid = req.get('game_id')
    games = db.get('games') or {}
    if gid not in games: return {"status": "error", "message": "Game not found"}
    
    game_path = games[gid]['path']
    files = {}
    if os.path.exists(game_path):
        for fname in os.listdir(game_path):
            path = os.path.join(game_path, fname)
            if os.path.isfile(path):
                with open(path, 'r') as f:
                    files[fname] = f.read()
    return {"status": "ok", "files": files}

def handle_create_room(req, user_id):
    with lock:
        gid = req.get('game_id')
        name = req.get('room_name')
        rid = str(uuid.uuid4())[:8]
        
        rooms = db.get('rooms') or {}
        rooms[rid] = {
            "id": rid, "name": name, "game_id": gid, 
            "host": user_id, "players": [user_id], 
            "status": "waiting"
        }

        db.update_all('rooms', rooms)
        return {"status": "ok", "room_id": rid, "message": "Created"}

def handle_leave_room(req, user_id):
    with lock:
        rid = req.get('room_id')
        rooms = db.get('rooms') or {}
        if rid not in rooms: return {"status": "error", "message": "Room not found"}
        
        room = rooms[rid]
        if user_id in room['players']:
            room['players'].remove(user_id)
            
            # If empty, delete
            if len(room['players']) == 0:
                del rooms[rid]
                db.update_all('rooms', rooms)
                return {"status": "ok", "message": "Left and deleted"}
            
            # If Host left, migrate
            if room['host'] == user_id:
                room['host'] = room['players'][0]
                
            db.update_all('rooms', rooms)
            broadcast_room_update(room)
            return {"status": "ok", "message": "Left"}
        
        return {"status": "error", "message": "Not in room"}

def handle_start_game(req, user_id):
    with lock:
        rid = req.get('room_id')
        rooms = db.get('rooms') or {}
        if rid not in rooms: return {"status": "error", "message": "Room not found"}
        
        room = rooms[rid]
        if room['host'] != user_id: return {"status": "error", "message": "Not host"}
        if room['status'] != 'waiting': return {"status": "error", "message": "Already started"}
        
        # Check player count match
        gid = room['game_id']
        games = db.get('games') or {}
        game = games.get(gid, {})
        max_players = int(game.get('max_players', 2)) # Default 2
        
        if len(room['players']) != max_players:
             return {"status": "error", "message": f"Waiting for players ({len(room['players'])}/{max_players})"}
             
        # Start
        print(f"Room {rid} Starting...")
        if start_game_instance(room):
            room['status'] = 'playing'
            db.update_all('rooms', rooms)
            
            # Broadcast Game Start explicitly
            # Though lobby client might Poll or we push
            # Let's push a specific "game_started" event or just "room_update" with status playing
            broadcast_room_update(room)
            return {"status": "ok"}
        
        return {"status": "error", "message": "Start failed"}

def handle_join_room(req, user_id):
    with lock:
        rid = req.get('room_id')
        rooms = db.get('rooms') or {}
        if rid not in rooms: return {"status": "error", "message": "Room not found"}
        
        room = rooms[rid]
        if user_id in room['players']: return {"status": "error", "message": "Already in room"}
        
        # Check max players from game metadata
        gid = room['game_id']
        games = db.get('games') or {}
        game = games.get(gid, {})
        max_players = int(game.get('max_players', 2)) # Default 2 if not set

        if len(room['players']) > max_players: 
            return {"status": "error", "message": "Full"}
        
        room['players'].append(user_id)
        
        db.update_all('rooms', rooms)
        
        # Broadcast update to room
        broadcast_room_update(room)
        
        return {"status": "ok", "message": "Joined"}

def handle_add_review(req, user_id):
    with lock:
        gid = req.get('game_id')
        reviews = db.get('reviews') or {}
        if gid not in reviews: reviews[gid] = []
        
        reviews[gid].append({
            "reviewer": user_id,
            "score": req.get('score'), "comment": req.get('comment')
        })
        db.update_all('reviews', reviews)
        return {"status": "ok", "message": "Review added"}



def handle_game_result(req):
    with lock:
        rid = req.get('room_id')
        winner = req.get('winner')
        reason = req.get('reason')
        print(f"[{time.time():.4f}] [Lobby] Game Result: Room {rid}, Winner {winner}, Reason {reason}")
        
        rooms = db.get('rooms') or {}
        if rid in rooms:
            # Clean up process if tracked
            if rid in pending_crashes: del pending_crashes[rid]
            
            with running_games_lock:
                if rid in running_games:
                    proc = running_games[rid]
                    # Wait for process to exit to avoid zombie (it should be exiting now as it reported result)
                    # We can use wait with timeout or just let monitor reap it?
                    # Better to wait explicitly if we know it's done.
                    try:
                        proc.wait(timeout=1) 
                    except subprocess.TimeoutExpired:
                        print(f"[Lobby] Warning: Game {rid} process slow to exit after report.")
                    
                    if rid in running_games:
                        del running_games[rid]
                        print(f"[Lobby] Process for Room {rid} reclaimed.")

            rooms[rid]['status'] = 'idle'
            # Reset port? Keep players? 
            # Requirement says: Back to room.
            rooms[rid].pop('port', None)
            
            # Persist Result for Polling Clients
            rooms[rid]['last_winner'] = winner
            rooms[rid]['last_reason'] = reason
            
            # Broadcast to players
            for p in rooms[rid]['players']:
                # Notify client to switch view
                msg = {
                    "type": "event", 
                    "event": "game_over", 
                    "winner": winner,
                    "reason": reason
                }
                broadcast_to_user(p, msg)
                
            db.update_all('rooms', rooms)
            
        return {"status": "ok"}

def supports_room_id_arg(script_path):
    try:
        with open(script_path, 'r') as f:
            content = f.read()
        return "--room_id" in content
    except OSError:
        return False

def start_game_instance(room):
    # Find free port
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    
    gid = room['game_id']
    games = db.get('games') or {}
    game = games.get(gid)
    if not game: return False
    
    script = os.path.join(game['path'], game.get('entry_point', 'game_server.py'))
    try:
        # Standard: python3 game_server.py --port <port> --room_id <room_id> --lobby_port <lobby_port>
        cmd = [sys.executable, script, "--port", str(port), "--lobby_port", str(PORT)]
        if supports_room_id_arg(script):
            cmd += ["--room_id", room['id']]
        
        proc = subprocess.Popen(cmd, cwd=game['path'])
        
        with running_games_lock:
            running_games[room['id']] = proc
        
        # Give it a second to bind
        import time
        time.sleep(1)
        
        room['port'] = port
        print(f"Game {gid} started on port {port}")
        return True
    except Exception as e:
        print(f"Start Error: {e}")
        return False

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"[Lobby] Listening on {HOST}:{PORT}")
    
    # Start Monitor Thread
    t_mon = threading.Thread(target=monitor_game_processes, daemon=True)
    t_mon.start()
    
    while True:
        client, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(client, addr))
        t.start()

if __name__ == "__main__":
    start_server()
