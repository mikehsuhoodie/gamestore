#!/usr/bin/env python3
import argparse
import json
import queue
import socket
import threading
import time
import tkinter as tk
from typing import Any, Dict, Optional, Tuple, List

Vec = Tuple[int, int]
DIRS = {"UP", "DOWN", "LEFT", "RIGHT"}

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

KEY_TO_DIR = {
    "Up": "UP",
    "Down": "DOWN",
    "Left": "LEFT",
    "Right": "RIGHT",
    "w": "UP",
    "s": "DOWN",
    "a": "LEFT",
    "d": "RIGHT",
    "W": "UP",
    "S": "DOWN",
    "A": "LEFT",
    "D": "RIGHT",
}

class NetClient:
    def __init__(self, ip: str, port: int, username: str):
        self.ip = ip
        self.port = port
        self.username = username

        self.conn: Optional[socket.socket] = None
        self.inbox: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.running = True

        self.player_id: Optional[int] = None
        self.grid_w = 32
        self.grid_h = 24
        self.tick_hz = 10

    def connect(self):
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.conn.connect((self.ip, self.port))
        threading.Thread(target=self._reader, daemon=True).start()
        send_json_line(self.conn, {"type": "hello", "username": self.username})

    def _reader(self):
        assert self.conn is not None
        try:
            for msg in recv_json_lines(self.conn):
                if msg.get("type") == "welcome":
                    self.player_id = int(msg.get("player_id", 0))
                    self.grid_w = int(msg.get("grid_w", self.grid_w))
                    self.grid_h = int(msg.get("grid_h", self.grid_h))
                    self.tick_hz = int(msg.get("tick_hz", self.tick_hz))
                self.inbox.put(msg)
        except (ConnectionError, OSError):
            pass
        finally:
            self.running = False
            try:
                if self.conn:
                    self.conn.close()
            except OSError:
                pass

    def send_dir(self, d: str):
        if not self.conn or d not in DIRS:
            return
        try:
            send_json_line(self.conn, {"type": "input", "dir": d})
        except OSError:
            self.running = False

class App:
    def __init__(self, net: NetClient):
        self.net = net
        self.latest_state: Optional[Dict[str, Any]] = None
        self.game_over: Optional[Dict[str, Any]] = None
        self.status = "Connecting..."

        self.cell = 22
        self.pad = 8

        self.root = tk.Tk()
        self.root.title("Snake Duel (Client)")

        self.info_var = tk.StringVar(value="Connecting...")
        self.info = tk.Label(self.root, textvariable=self.info_var, font=("Consolas", 11))
        self.info.pack(side=tk.TOP, anchor="w", padx=10, pady=(10, 6))

        self.canvas = tk.Canvas(self.root, width=32*self.cell, height=24*self.cell, highlightthickness=0, bg="#101010")
        self.canvas.pack(padx=10, pady=(0, 10))

        self.root.bind("<KeyPress>", self.on_key)

        self.last_sent_dir: Optional[str] = None

        # poll network messages + render
        self.root.after(16, self.tick_ui)

    def on_key(self, ev):
        if ev.keysym == "Escape":
            self.root.destroy()
            return
        d = KEY_TO_DIR.get(ev.keysym)
        if d and d != self.last_sent_dir and self.net.player_id is not None:
            self.net.send_dir(d)
            self.last_sent_dir = d

    def tick_ui(self):
        # drain inbox
        try:
            while True:
                msg = self.net.inbox.get_nowait()
                t = msg.get("type")
                if t == "waiting":
                    have = msg.get("have", 0)
                    self.status = f"Waiting for opponent... ({have}/2)"
                elif t == "start":
                    self.status = "Game started!"
                elif t == "state":
                    self.latest_state = msg
                elif t == "game_over":
                    self.game_over = msg
                elif t == "error":
                    self.status = f"Error: {msg.get('message','')}"
        except queue.Empty:
            pass

        if not self.net.running and not self.game_over:
            self.status = "Disconnected."

        # resize if we learned actual grid sizes
        gw = self.net.grid_w
        gh = self.net.grid_h
        if self.latest_state:
            gw = int(self.latest_state.get("grid_w", gw))
            gh = int(self.latest_state.get("grid_h", gh))
        self.canvas.configure(width=gw*self.cell, height=gh*self.cell)

        self.render(gw, gh)

        self.root.after(16, self.tick_ui)

    def render(self, gw: int, gh: int):
        self.canvas.delete("all")

        if not self.latest_state:
            self.info_var.set(self.status)
            self.canvas.create_text(
                (gw*self.cell)//2, (gh*self.cell)//2,
                text=self.status,
                fill="#E0E0E0",
                font=("Consolas", 14)
            )
            return

        names = self.latest_state.get("names", {"1": "P1", "2": "P2"})
        scores = self.latest_state.get("scores", {"1": 0, "2": 0})
        alive = self.latest_state.get("alive", {"1": False, "2": False})
        pid_txt = f"You are Player {self.net.player_id}" if self.net.player_id else "You are Player ?"
        header = (
            f"P1({names.get('1','P1')}): {scores.get('1',0)} {'ALIVE' if alive.get('1') else 'DEAD'}   "
            f"P2({names.get('2','P2')}): {scores.get('2',0)} {'ALIVE' if alive.get('2') else 'DEAD'}   "
            f"| {pid_txt}"
        )
        if self.game_over:
            header += f"   | GAME OVER: {self.game_over.get('result','')} ({self.game_over.get('reason','')})"
        self.info_var.set(header)

        # food
        fx, fy = self.latest_state.get("food", (0, 0))
        self._draw_cell(fx, fy, fill="#E05858", outline="")

        # snakes
        snakes = self.latest_state.get("snakes", {"1": [], "2": []})
        s1: List[Vec] = [tuple(p) for p in snakes.get("1", [])]
        s2: List[Vec] = [tuple(p) for p in snakes.get("2", [])]

        for i, (x, y) in enumerate(s1):
            self._draw_cell(x, y, fill=("#3CC878" if i == 0 else "#2F8F63"), outline="")
        for i, (x, y) in enumerate(s2):
            self._draw_cell(x, y, fill=("#4FA0E6" if i == 0 else "#3576B8"), outline="")

        # simple border
        self.canvas.create_rectangle(0, 0, gw*self.cell, gh*self.cell, outline="#404040")

        if self.game_over:
            # overlay text
            self.canvas.create_rectangle(
                0, (gh*self.cell)//2 - 40, gw*self.cell, (gh*self.cell)//2 + 40,
                fill="#000000", outline="", stipple="gray50"
            )
            self.canvas.create_text(
                (gw*self.cell)//2, (gh*self.cell)//2 - 10,
                text=f"GAME OVER: {self.game_over.get('result','')}",
                fill="#FFFFFF",
                font=("Consolas", 18, "bold")
            )
            self.canvas.create_text(
                (gw*self.cell)//2, (gh*self.cell)//2 + 16,
                text="Press ESC to quit",
                fill="#E0E0E0",
                font=("Consolas", 12)
            )

    def _draw_cell(self, x: int, y: int, fill: str, outline: str):
        x0 = x * self.cell
        y0 = y * self.cell
        self.canvas.create_rectangle(x0, y0, x0 + self.cell, y0 + self.cell, fill=fill, outline=outline)

    def run(self):
        self.root.mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", type=str, required=True, help="Game Server IP")
    ap.add_argument("--port", type=int, required=True, help="Game Server Port")
    ap.add_argument("--username", type=str, default=f"user_{int(time.time())%10000}", help="Displayed username")
    args = ap.parse_args()

    net = NetClient(args.ip, args.port, args.username)
    net.connect()

    App(net).run()


if __name__ == "__main__":
    main()
