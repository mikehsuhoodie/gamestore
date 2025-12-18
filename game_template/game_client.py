import socket
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
