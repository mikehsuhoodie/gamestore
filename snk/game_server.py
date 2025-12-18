#!/usr/bin/env python3
import argparse
import json
import random
import socket
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

# ===== Config =====
GRID_W = 32
GRID_H = 24
TICK_HZ = 10

LOBBY_HOST = "127.0.0.1"
LOBBY_PORT = 10192

Vec = Tuple[int, int]
DIRS: Dict[str, Vec] = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}
OPPOSITE = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}


def send_json_line(conn: socket.socket, obj: dict) -> None:
    data = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
    conn.sendall(data)


def recv_json_lines(conn: socket.socket):
    buf = b""
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue


@dataclass
class Player:
    pid: int
    conn: socket.socket
    addr: Tuple[str, int]
    username: str = ""
    desired_dir: str = "RIGHT"
    alive: bool = True
    score: int = 0


class SnakeDuelServer:
    def __init__(self, host: str, port: int, room_id: str, lobby_port: int = 10192):
        self.host = host
        self.port = port
        self.room_id = room_id
        self.lobby_port = lobby_port

        self.server_sock: Optional[socket.socket] = None
        self.players: Dict[int, Player] = {}
        self.lock = threading.Lock()

        self.started = False
        self.running = True
        self.tick = 0

        self.snakes: Dict[int, List[Vec]] = {}
        self.dirs: Dict[int, str] = {}
        self.food: Vec = (0, 0)

        self.reported = False  # ensure report once

    def start(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(5)
        print(f"[SERVER] listening on {self.host}:{self.port} room_id={self.room_id}")

        threading.Thread(target=self._accept_loop, daemon=True).start()
        self._game_loop()

    def _accept_loop(self):
        assert self.server_sock is not None
        while self.running:
            try:
                conn, addr = self.server_sock.accept()
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                break

            with self.lock:
                if len(self.players) >= 2:
                    try:
                        send_json_line(conn, {"type": "error", "message": "Server full (2 players)."})
                    finally:
                        conn.close()
                    continue

                pid = 1 if 1 not in self.players else 2
                self.players[pid] = Player(pid=pid, conn=conn, addr=addr, username=f"P{pid}")

            print(f"[SERVER] Player{pid} connected from {addr}")
            threading.Thread(target=self._client_reader, args=(pid,), daemon=True).start()

            try:
                send_json_line(conn, {
                    "type": "welcome",
                    "player_id": pid,
                    "grid_w": GRID_W,
                    "grid_h": GRID_H,
                    "tick_hz": TICK_HZ
                })
            except OSError:
                self._disconnect(pid)

    def _disconnect(self, pid: int):
        p = None
        with self.lock:
            p = self.players.pop(pid, None)
        if p:
            try:
                p.conn.close()
            except OSError:
                pass
            print(f"[SERVER] Player{pid} disconnected")

        if self.started and self.running:
            # Disconnect during a live match => draw
            self._end_game(winner="DRAW", reason="disconnect")

    def _client_reader(self, pid: int):
        with self.lock:
            p = self.players.get(pid)
        if not p:
            return

        try:
            for msg in recv_json_lines(p.conn):
                t = msg.get("type")
                if t == "hello":
                    name = str(msg.get("username", msg.get("name", f"P{pid}")))[:24]
                    with self.lock:
                        if pid in self.players:
                            self.players[pid].username = name
                elif t == "input":
                    d = msg.get("dir")
                    if d in DIRS:
                        with self.lock:
                            if pid in self.players:
                                self.players[pid].desired_dir = d
        except (ConnectionError, OSError):
            pass
        finally:
            self._disconnect(pid)

    def _broadcast(self, obj: dict):
        dead = []
        with self.lock:
            items = list(self.players.items())
        for pid, p in items:
            try:
                send_json_line(p.conn, obj)
            except OSError:
                dead.append(pid)
        for pid in dead:
            self._disconnect(pid)

    def _init_game(self):
        self.snakes = {
            1: [(6, GRID_H // 2), (5, GRID_H // 2), (4, GRID_H // 2)],
            2: [(GRID_W - 7, GRID_H // 2), (GRID_W - 6, GRID_H // 2), (GRID_W - 5, GRID_H // 2)],
        }
        self.dirs = {1: "RIGHT", 2: "LEFT"}

        with self.lock:
            for pid in (1, 2):
                if pid in self.players:
                    self.players[pid].alive = True
                    self.players[pid].score = 0
                    self.players[pid].desired_dir = self.dirs[pid]

        self.food = self._spawn_food()
        self.tick = 0
        self.started = True

    def _spawn_food(self) -> Vec:
        occupied = set(self.snakes.get(1, [])) | set(self.snakes.get(2, []))
        empties = [(x, y) for x in range(GRID_W) for y in range(GRID_H) if (x, y) not in occupied]
        return random.choice(empties) if empties else (0, 0)

    def _apply_inputs(self):
        with self.lock:
            for pid, p in self.players.items():
                if pid not in self.dirs:
                    continue
                want = p.desired_dir
                cur = self.dirs[pid]
                if want in DIRS and want != OPPOSITE[cur]:
                    self.dirs[pid] = want

    def _is_alive(self, pid: int) -> bool:
        with self.lock:
            p = self.players.get(pid)
            return bool(p and p.alive)

    def _kill(self, pid: int):
        with self.lock:
            if pid in self.players:
                self.players[pid].alive = False

    def _add_score(self, pid: int, delta: int):
        with self.lock:
            if pid in self.players:
                self.players[pid].score += delta

    def _step(self):
        self._apply_inputs()

        next_head: Dict[int, Vec] = {}
        for pid in (1, 2):
            if not self._is_alive(pid):
                continue
            hx, hy = self.snakes[pid][0]
            dx, dy = DIRS[self.dirs[pid]]
            next_head[pid] = (hx + dx, hy + dy)

        # head-to-head same cell => draw
        if 1 in next_head and 2 in next_head and next_head[1] == next_head[2]:
            self._kill(1)
            self._kill(2)
            return

        for pid in (1, 2):
            if pid not in next_head:
                continue
            nh = next_head[pid]
            other = 2 if pid == 1 else 1

            # wall
            if nh[0] < 0 or nh[0] >= GRID_W or nh[1] < 0 or nh[1] >= GRID_H:
                self._kill(pid)
                continue

            will_eat = (nh == self.food)
            my_body = self.snakes[pid]
            other_body = self.snakes.get(other, [])

            # if not eating, tail moves => don't count last segment for self-collision
            my_check = my_body if will_eat else my_body[:-1]
            other_check = other_body if self._is_alive(other) else []

            if nh in my_check or nh in other_check:
                self._kill(pid)
                continue

            # move
            self.snakes[pid].insert(0, nh)
            if will_eat:
                self._add_score(pid, 1)
                self.food = self._spawn_food()
            else:
                self.snakes[pid].pop()

    def _state_payload(self) -> dict:
        with self.lock:
            p1 = self.players.get(1)
            p2 = self.players.get(2)

            names = {"1": (p1.username if p1 else "P1"), "2": (p2.username if p2 else "P2")}
            scores = {"1": (p1.score if p1 else 0), "2": (p2.score if p2 else 0)}
            alive = {"1": (p1.alive if p1 else False), "2": (p2.alive if p2 else False)}

        return {
            "type": "state",
            "tick": self.tick,
            "grid_w": GRID_W,
            "grid_h": GRID_H,
            "snakes": {"1": self.snakes.get(1, []), "2": self.snakes.get(2, [])},
            "food": self.food,
            "scores": scores,
            "alive": alive,
            "names": names,
        }

    def _result_if_over(self) -> Optional[Tuple[str, str]]:
        a1 = self._is_alive(1)
        a2 = self._is_alive(2)
        if a1 and a2:
            return None
        if (not a1) and (not a2):
            return ("DRAW", "both_dead")
        if a1 and (not a2):
            return ("P1", "p2_dead")
        if a2 and (not a1):
            return ("P2", "p1_dead")
        return None

    def _report_to_lobby(self, winner: str, reason: str):
        if self.reported:
            return
        self.reported = True

        # winner: username or "P1"/"P2"/"DRAW"
        if winner in ("P1", "P2"):
            pid = 1 if winner == "P1" else 2
            with self.lock:
                p = self.players.get(pid)
                if p and p.username:
                    winner_val = p.username
                else:
                    winner_val = winner
        else:
            winner_val = winner

        payload = {
            "action": "game_result",
            "room_id": self.room_id,
            "winner": winner_val,
            "reason": reason,
        }

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((LOBBY_HOST, self.lobby_port))
            sock.sendall(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
            sock.close()
            print(f"[SERVER] reported to lobby: {payload}")
        except OSError as e:
            print(f"[SERVER] WARNING: failed to report to lobby: {e} payload={payload}")

    def _end_game(self, winner: str, reason: str):
        if not self.running:
            return
        self._broadcast({"type": "game_over", "result": winner, "reason": reason})
        self._report_to_lobby(winner=winner, reason=reason)
        self.running = False

    def _shutdown(self):
        print("[SERVER] shutting down")
        try:
            if self.server_sock:
                self.server_sock.close()
        except OSError:
            pass
        with self.lock:
            conns = [p.conn for p in self.players.values()]
            self.players.clear()
        for c in conns:
            try:
                c.close()
            except OSError:
                pass

    def _game_loop(self):
        step_dt = 1.0 / TICK_HZ
        last = time.perf_counter()
        acc = 0.0

        while self.running:
            now = time.perf_counter()
            acc += (now - last)
            last = now

            with self.lock:
                n_players = len(self.players)

            if not self.started:
                if n_players == 2:
                    print("[SERVER] 2 players ready. Starting game.")
                    self._init_game()
                    self._broadcast({"type": "start"})
                else:
                    self._broadcast({"type": "waiting", "have": n_players, "need": 2})
                    time.sleep(0.2)
                    continue

            while acc >= step_dt and self.running:
                self.tick += 1
                self._step()

                self._broadcast(self._state_payload())

                res = self._result_if_over()
                if res:
                    winner, reason = res
                    self._end_game(winner=winner, reason=reason)
                    break

                acc -= step_dt

            time.sleep(0.001)

        # ensure report if somehow ended without explicit end (shouldn't happen)
        self._shutdown()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True, help="Port to listen on for game connections")
    ap.add_argument("--room_id", type=str, required=True, help="Room ID used for reporting game results back to the lobby")
    ap.add_argument("--lobby_port", type=int, default=10192, help="Lobby Port")
    args = ap.parse_args()

    srv = SnakeDuelServer(host="0.0.0.0", port=args.port, room_id=args.room_id, lobby_port=args.lobby_port)
    srv.start()


if __name__ == "__main__":
    main()
