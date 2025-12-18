import json
import struct
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

def recvall(sock, n):
    """
    Helper to receive exactly n bytes.
    """
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data

class DBClient:
    def __init__(self, host='127.0.0.1', port=10195):
        self.addr = (host, port)
        
    def _req(self, payload):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(self.addr)
            sock.sendall(json.dumps(payload).encode())
            resp = json.loads(sock.recv(16384).decode())
            sock.close()
            return resp
        except Exception as e:
            # print(f"DB Connect Error: {e}")
            return {"status": "error", "message": str(e)}

    def get(self, collection, key=None):
        return self._req({"action": "GET", "collection": collection, "key": key}).get('data')

    def set(self, collection, key, value):
        return self._req({"action": "SET", "collection": collection, "key": key, "value": value})
        
    def delete(self, collection, key):
        return self._req({"action": "DELETE", "collection": collection, "key": key})
        
    def update_all(self, collection, data):
        return self._req({"action": "UPDATE_ALL", "collection": collection, "data": data})
