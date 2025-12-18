import os
import sys
import json

TEMPLATE_SERVER = """import socket
import sys
import threading
import argparse
import time

import json

class GameServer:
    def __init__(self, port, room_id, lobby_port=8888):
        self.host = '0.0.0.0'
        self.port = int(port)
        self.room_id = room_id
        self.lobby_port = int(lobby_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = []
        self.lock = threading.Lock()
        self.game_over = False
        
    def start(self):
        self.sock.bind((self.host, self.port))
        self.sock.listen(2)
        print(f"Game listening on {self.port}")
        sys.stdout.flush()
        
        # Wait for 2 players
        while len(self.clients) < 2:
            client, addr = self.sock.accept()
            print(f"Player joined: {addr}")
            sys.stdout.flush()
            self.clients.append(client)
            
        self.broadcast("Game Starting! Battle Mode.\\n")
        self.run_game()
        
    def broadcast(self, msg):
        for c in self.clients:
            try:
                c.sendall(msg.encode())
            except:
                pass
                
    def run_game(self):
        # Battle Logic Placeholder
        hp = [20, 20]
        turn = 0
        
        while not self.game_over and hp[0] > 0 and hp[1] > 0:
            try:
                self.clients[turn].sendall(b"Your Turn! Enter attack (1-10): ")
                self.clients[1-turn].sendall(b"Opponent turn...\\n")
                
                try:
                    data = self.clients[turn].recv(1024).strip()
                    if not data: raise Exception("Disconnected")
                except Exception as e:
                    print(f"Player {turn+1} disconnected: {e}")
                    # Handle Disconnect: Opponent Wins
                    winner_idx = 1 - turn
                    self.clients[winner_idx].sendall(b"Opponent disconnected. You Win!\\n")
                    self.report_result(winner_idx, "OPPONENT_LEFT")
                    self.game_over = True
                    break
                
                val = int(data.decode())
                dmg = val if 1 <= val <= 10 else 0
                hp[1-turn] -= dmg
                
                res = f"P{turn+1} attacks with {val}. Dmg: {dmg}. HP: {hp}\\n"
                self.broadcast(res)
                
                if hp[1-turn] <= 0:
                    self.broadcast(f"P{turn+1} Wins!\\n")
                    self.report_result(turn, "NORMAL_WIN")
                    self.game_over = True
                    
                turn = 1 - turn
            except Exception as e:
                print(f"Game Loop Error: {e}")
                break
                
        self.broadcast("Game Over. Closing in 3s.\\n")
        time.sleep(3)
        self.close()

    def report_result(self, winner_idx, reason):
        try:
            # We need room_id. I will assume it's stored in self.room_id
            if not self.room_id: return
            
            payload = {
                "action": "game_result",
                "room_id": self.room_id,
                "winner": f"P{winner_idx+1}", # Simple player index mapping
                "reason": reason
            }
            
            # Connect to Lobby
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('127.0.0.1', self.lobby_port))
            s.sendall(json.dumps(payload).encode())
            s.close()
            print(f"Reported result: {payload}")
        except Exception as e:
            print(f"Failed to report result: {e}")

    def close(self):
        for c in self.clients:
            c.close()
        self.sock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Game Server')
    parser.add_argument('--port', type=int, required=True, help='Port to listen on')
    parser.add_argument('--room_id', type=str, required=False, default="unknown", help='Room ID for reporting')
    parser.add_argument('--lobby_port', type=int, required=False, default=8888, help='Lobby Port')
    
    args = parser.parse_args()
    
    server = GameServer(args.port, args.room_id, args.lobby_port)
    server.start()
"""

TEMPLATE_CLIENT = """import socket
import sys
import threading
import argparse

def game_client(ip, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((ip, port))
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    print(f"Connected to Game Server at {ip}:{port}")
    print("Type your moves (1-10) for battle!")
    
    stop_event = threading.Event()
    
    def listen():
        while not stop_event.is_set():
            try:
                data = s.recv(4096)
                if not data: break
                print(data.decode(), end='', flush=True)
            except:
                break
        stop_event.set()
        
    t = threading.Thread(target=listen, daemon=True)
    t.start()
    
    try:
        while not stop_event.is_set():
            msg = input() 
            if stop_event.is_set(): break
            s.sendall(msg.encode())
    except KeyboardInterrupt:
        pass
    except Exception:
        pass
        
    s.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Game Client')
    parser.add_argument('--ip', type=str, required=True, help='Server IP')
    parser.add_argument('--port', type=int, required=True, help='Server Port')
    parser.add_argument('--username', type=str, required=False, help='Player Username')
    
    args = parser.parse_args()
    
    game_client(args.ip, args.port)
"""

def create_template(name):
    # Sanitize name
    folder = name.replace(" ", "_")
    if os.path.exists(folder):
        print(f"Error: Folder {folder} already exists.")
        return

    os.makedirs(folder)
    
    # Write Server
    with open(os.path.join(folder, 'game_server.py'), 'w') as f:
        f.write(TEMPLATE_SERVER)
        
    # Write Client
    with open(os.path.join(folder, 'game_client.py'), 'w') as f:
        f.write(TEMPLATE_CLIENT)
        
    # Write Metadata
    with open(os.path.join(folder, 'metadata.json'), 'w') as f:
        json.dump({
            "name": name, 
            "version": "1.0", 
            "entry_point": "game_server.py",
            "min_players": 2,
            "max_players": 2,
            "type": "CLI"
        }, f, indent=2)
        
    print(f"Game project '{name}' created in ./{folder}/")
    print("Structure:")
    print(f"  {folder}/game_server.py  (Game Logic)")
    print(f"  {folder}/game_client.py  (Player UI/Input)")
    print(f"  {folder}/metadata.json   (Config)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        game_name = input("Enter game name: ")
    else:
        game_name = sys.argv[1]
    create_template(game_name)
