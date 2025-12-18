import json
import socket

def send_json(sock, data):
    msg = json.dumps(data) + '\n'
    sock.sendall(msg.encode())

def recv_json(f):
    try:
        line = f.readline()
        if not line: return None
        return json.loads(line)
    except:
        return None
