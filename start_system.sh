#!/bin/bash

# Game Store System - Startup Script with Tmux
# Layout: 3 Rows x 2 Columns
# [ DB Server  | Lobby Serv ]
# [ Dev Srv    | Dev Client ]
# [ P. Client 1| P. Client 2]

SESSION="gamestore"

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "Tmux not found. Please install tmux or run servers manually."
    exit 1
fi

# Kill existing session if any
tmux kill-session -t $SESSION 2>/dev/null

echo "Starting Game Store System..."
echo "Building 3x2 Grid Layout..."

# 1. Create Session (Row 1 established, Pane 0)
# We name the window 'Main' so we can reference it easily
tmux new-session -d -s $SESSION -n "Main"

# 2. Create 3 Rows first
# Split Pane 0 vertically -> Creates Pane 1 (Bottom)
tmux split-window -v -t ${SESSION}:Main.0

# Split Pane 1 vertically -> Creates Pane 2 (Bottom)
tmux split-window -v -t ${SESSION}:Main.1

# Distribute height evenly for the 3 rows
tmux select-layout -t ${SESSION}:Main even-vertical

# Now we have:
# [ Pane 0 ]
# [ Pane 1 ]
# [ Pane 2 ]

# 3. Create Columns (Split each row horizontally)
# IMPORTANT: When we split Pane 0, the new pane becomes Pane 1, pushing others down.
# So we need to be careful with indices or split from bottom up?
# Let's simple split specific targets which we know should be there.

# Split Top Row (Pane 0) -> New Pane 1. Old 1->2. Old 2->3.
tmux split-window -h -t ${SESSION}:Main.0

# Middle Row is now Pane 2. Split it -> New Pane 3. Old 3->4.
tmux split-window -h -t ${SESSION}:Main.2

# Bottom Row is now Pane 4. Split it -> New Pane 5.
tmux split-window -h -t ${SESSION}:Main.4

# Layout Check:
# Row 1: Pane 0, Pane 1
# Row 2: Pane 2, Pane 3
# Row 3: Pane 4, Pane 5

# 4. Inject Commands
run_pane() {
    tmux send-keys -t ${SESSION}:Main.$1 "$2" C-m
}

run_pane 0 "python3 server/db_server.py"
run_pane 1 "python3 server/lobby_server.py"
run_pane 2 "python3 server/dev_server.py"
run_pane 3 "python3 client/developer_client.py"
run_pane 4 "python3 client/lobby_client.py"
run_pane 5 "python3 client/lobby_client.py --port 8001"

# 5. Connect
tmux select-pane -t ${SESSION}:Main.0
tmux attach-session -t $SESSION
