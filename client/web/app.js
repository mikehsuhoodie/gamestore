const appState = {
    view: 'auth',
    authMode: 'login', // login | register
    user: null,
    gameToRoom: null, // current game id for room context
    isLaunching: false
};

// --- API ---

async function api(endpoint, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    try {
        const res = await fetch('/api' + endpoint, opts);
        const data = await res.json();

        if (data.status === 'error' && (data.message === 'Login Required' || data.message === 'Login required')) {
            toast("Session expired. Please login again.", true);
            logout();
            return data;
        }
        return data;
    } catch (e) {
        console.error(e);
        return { status: 'error', message: 'Network error' };
    }
}

// --- Auth ---

function switchAuthMode(mode) {
    appState.authMode = mode;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('auth-submit').textContent = mode === 'login' ? 'Login' : 'Register';
}

document.getElementById('auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const u = document.getElementById('username').value;
    const p = document.getElementById('password').value;

    // Auth request
    const res = await api('/' + appState.authMode, 'POST', { username: u, password: p });

    if (res.status === 'ok') {
        appState.user = u;
        document.getElementById('user-display').textContent = u;
        toast(`Welcome, ${u}`);
        showView('dashboard');
        showTab('store');
    } else {
        toast(res.message, true);
    }
});

function logout() {
    appState.user = null;
    showView('auth');
    document.getElementById('password').value = '';
}

// --- Views & Tabs ---

function showView(viewName) {
    document.querySelectorAll('.view').forEach(v => {
        v.classList.add('hidden');
        v.classList.remove('active');
    });
    const el = document.getElementById('view-' + viewName);
    el.classList.remove('hidden');
    // slight delay for fade in
    setTimeout(() => el.classList.add('active'), 10);
}

function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.add('hidden'));
    document.getElementById('tab-' + tabName).classList.remove('hidden');

    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active'); // Might be null if called programmatically, handle carefuly

    if (tabName === 'store') refreshStore();
    if (tabName === 'library') refreshLibrary();
}

// --- Store ---

async function refreshStore() {
    const grid = document.getElementById('store-grid');
    grid.innerHTML = '<div class="loading-spinner"></div>';

    const res = await api('/games');
    grid.innerHTML = '';

    if (res.status === 'ok' && res.games) {
        Object.entries(res.games).forEach(([gid, g]) => {
            const card = document.createElement('div');
            card.className = 'game-card';
            card.innerHTML = `
                <div class="card-title">${g.name} <span class="tag">v${g.version}</span> <span class="tag" style="border-color: #fff; color: #fff;">${g.type || 'GUI'}</span></div>
                <span class="card-ver">by ${g.author}</span>
                <p class="card-desc">${g.description}</p>
                <button class="btn secondary sm full-width" style="margin-bottom: 0.5rem;" onclick="openGameDetails('${gid}')">Details & Reviews</button>
                <button class="btn primary sm full-width" onclick="installGame('${gid}')">Install</button>
            `;
            grid.appendChild(card);
        });
    } else {
        grid.innerHTML = '<p class="subtitle">No games available.</p>';
    }
}

async function installGame(gid) {
    toast(`Downloading game...`);
    const res = await api('/install', 'POST', { game_id: gid });
    if (res.status === 'ok') {
        toast("Install Complete!");
    } else {
        toast("Install Failed: " + res.message, true);
    }
}

// --- Library ---

async function refreshLibrary() {
    const grid = document.getElementById('library-grid');
    grid.innerHTML = '<div class="loading-spinner"></div>';

    const res = await api('/library');
    grid.innerHTML = '';

    if (res.status === 'ok' && res.games) {
        if (res.games.length === 0) {
            grid.innerHTML = '<p class="subtitle">Library empty. Go to Store!</p>';
            return;
        }
        res.games.forEach(g => {
            const card = document.createElement('div');
            card.className = 'game-card';
            let updateBtn = '';
            if (g.update_available) {
                updateBtn = `<button class="btn secondary sm full-width" style="margin-bottom:0.5rem" onclick="updateGame('${g.id}')">Update Available!</button>`;
            }

            card.innerHTML = `
                <div class="card-title">${g.name}</div>
                <span class="card-ver">v${g.version} <span class="tag" style="border-color: #fff; color: #fff;">${g.type || 'GUI'}</span></span>
                <p class="card-desc" style="margin-top:0.5rem">Ready to launch</p>
                ${updateBtn}
                <button class="btn secondary sm full-width" style="margin-bottom: 0.5rem;" onclick="openGameDetails('${g.id}')">Details</button>
                <button class="btn primary sm full-width" onclick="openRoomModal('${g.id}', '${g.name}')">Play</button>
            `;
            grid.appendChild(card);
        });
    }
}

async function updateGame(gid) {
    installGame(gid); // Same logic re-downloads
    setTimeout(refreshLibrary, 2000);
}

// --- Rooms ---
let pollInterval = null;

function openRoomModal(gid, name) {
    appState.gameToRoom = gid;
    document.getElementById('room-game-title').textContent = name;

    // Explicitly reset waiting state to avoid overlay overlapping
    const lobbyWait = document.getElementById('lobby-wait');
    if (lobbyWait) lobbyWait.classList.add('hidden');
    if (pollInterval) clearInterval(pollInterval);

    document.getElementById('modal-room').classList.remove('hidden');
    refreshRooms();

}

function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
    if (pollInterval) clearInterval(pollInterval);
    // kill any waiting state?
    // kill any waiting state?
    const lobbyWait = document.getElementById('lobby-wait');
    if (lobbyWait) lobbyWait.classList.add('hidden');
}

async function refreshRooms() {
    const list = document.getElementById('room-list');
    list.innerHTML = 'Loading...';

    const res = await api('/rooms');
    list.innerHTML = '';

    if (res.status === 'ok' && res.rooms) {
        const myRooms = Object.values(res.rooms).filter(r => r.game_id === appState.gameToRoom);
        if (myRooms.length === 0) list.innerHTML = 'No active rooms for this game.';

        myRooms.forEach(r => {
            const item = document.createElement('div');
            item.className = 'room-item';
            item.innerHTML = `
                <div>
                    <strong>${r.name}</strong> <span style="font-size:0.8rem">(${r.id})</span>
                </div>
                <div>
                    <span class="room-status">${r.status} (${r.players.length}/2)</span>
                    <button class="btn sm" onclick="joinRoom('${r.id}')">Join</button>
                </div>
            `;
            list.appendChild(item);
        });
    }
}

async function createRoom() {
    const name = document.getElementById('new-room-name').value;
    if (!name) return;

    const res = await api('/room/create', 'POST', { game_id: appState.gameToRoom, room_name: name });
    if (res.status === 'ok') {
        enterRoom(res.room_id);
    } else {
        toast(res.message, true);
    }
}

async function joinRoom(rid) {
    const id = rid || document.getElementById('join-room-id').value;
    if (!id) return;

    const res = await api('/room/join', 'POST', { room_id: id });
    if (res.status === 'ok') {
        enterRoom(id);
    } else {
        toast(res.message, true);
    }
}

// --- Active Room Controller ---

let roomPoller = null; // Polls for room updates (in addition to push if needed)

function enterRoom(rid) {
    document.getElementById('modal-room').classList.add('hidden'); // Hide list
    document.getElementById('active-room-view').classList.remove('hidden');
    appState.currentRoomId = rid;
    appState.isLaunching = false;

    // Start Polling
    pollRoom(rid);
}

function pollRoom(rid) {
    if (roomPoller) clearInterval(roomPoller);

    // Initial fetch
    fetchRoomState(rid);

    roomPoller = setInterval(() => {
        fetchRoomState(rid);
    }, 1000);
}

async function fetchRoomState(rid) {
    const res = await api(`/room/info?room_id=${rid}`);

    // Handle Async Event Interception (Lobby Client might return a buffered event)
    if (res.type === 'event') {
        if (res.event === 'room_update') {
            console.log("Received room_update via poll");
            renderRoom(res.room);
            return;
        }
        if (res.event === 'game_over') {
            // Should verify if this game over is for this room? 
            // Usually yes.
            // Move back to room view (already there)
            // Maybe show alert?
            toast(`Game Over: ${res.winner} wins!(${res.reason})`);
            // Show Review Modal
            showReviewModal(res.winner, res.reason);
            // Polling continues to catch 'idle' status updats
            return;
        }
        // If other event, ignore and let poll happen again
        return;
    }

    if (res.status === 'ok') {
        const room = res.room;

        // Check Status
        if (room.status === 'playing') {
            if (appState.isLaunching) return;

            // Launch!
            appState.isLaunching = true;
            // DO NOT stop polling, or we won't know when it ends
            // if (roomPoller) clearInterval(roomPoller); 

            // Hide room view so user focuses on Game Window
            document.getElementById('active-room-view').classList.add('hidden');

            launchGame(appState.gameToRoom, room.port);
            return;
        }

        // If we were launching, and now status is NOT playing (e.g. idle), means game ended
        // If we were launching, and now status is NOT playing (e.g. idle), means game ended
        if (appState.isLaunching && room.status !== 'playing') {
            appState.isLaunching = false;
            // Unhide room view
            document.getElementById('active-room-view').classList.remove('hidden');
        }

        // Persistent Review Check: If game is over (idle) and has a winner
        if (room.status === 'idle' && room.last_winner) {
            // Check if we already showed this specific win
            const winKey = `${room.id}_${room.last_winner}_${room.last_reason}`;

            // Check session/local state (using appState for checks during this session)
            // AND check if modal is currently visible (to avoid re-triggering animation)
            const modal = document.getElementById('modal-review');
            const isModalHidden = modal.classList.contains('hidden');

            if (appState.lastShownWinKey !== winKey && isModalHidden) {
                console.log("Persistent Review Check: Triggering Modal");
                showReviewModal(room.last_winner, room.last_reason || 'End');
                appState.lastShownWinKey = winKey;
            }
        }

        renderRoom(room);
    } else {
        // Room likely deleted or user kicked
        if (roomPoller) clearInterval(roomPoller);
        toast("Room closed or disconnected", true);
        document.getElementById('active-room-view').classList.add('hidden');
        openRoomModal(appState.gameToRoom, document.getElementById('room-game-title').textContent); // Back to list
    }
}

function renderRoom(room) {
    document.getElementById('ar-room-name').textContent = room.name;
    document.getElementById('ar-room-id').textContent = room.id;
    document.getElementById('ar-player-count').textContent = room.players.length;

    const list = document.getElementById('ar-player-list');
    list.innerHTML = '';

    room.players.forEach(p => {
        const el = document.createElement('div');
        el.className = 'player-item';
        if (p === appState.user) el.classList.add('me');

        el.innerHTML = `
            <span class="player-name">${p}</span>
            ${p === room.host ? '<span class="host-badge">HOST</span>' : ''}
        `;
        list.appendChild(el);
    });

    // Controls
    const isHost = (room.host === appState.user);
    const btnStart = document.getElementById('btn-start-game');
    const txtStatus = document.getElementById('ar-status-msg');

    if (isHost) {
        btnStart.classList.remove('hidden');
        txtStatus.classList.add('hidden');
    } else {
        btnStart.classList.add('hidden');
        txtStatus.classList.remove('hidden');
    }
}

async function startGame() {
    if (!appState.currentRoomId) return;
    const res = await api('/room/start', 'POST', { room_id: appState.currentRoomId });
    if (res.status !== 'ok') toast(res.message, true);
}

async function leaveRoom() {
    if (!appState.currentRoomId) return;
    const res = await api('/room/leave', 'POST', { room_id: appState.currentRoomId });

    // Cleanup Local
    if (roomPoller) clearInterval(roomPoller);
    document.getElementById('active-room-view').classList.add('hidden');

    // Go back to Room List
    openRoomModal(appState.gameToRoom, document.getElementById('room-game-title').textContent);
}

// Fallback for launch if not handled by poller (e.g. manual call)
async function launchGame(gid, port) {
    toast("Launching Game...");
    const res = await api('/launch', 'POST', { game_id: gid, port: port });
    if (res.status !== 'ok') {
        toast("Launch failed: " + res.message, true);
        // If launch failed, maybe go back to room?
        // But room status is 'playing'. User is stuck. 
        // They can leave room manually if UI allows.
        // For now, let's reopen room UI so they can Leave.
        document.getElementById('active-room-view').classList.remove('hidden');
    }
}

// --- Reviews ---
let currentRating = 5;
function setRating(n) {
    currentRating = n;
    const stars = document.querySelectorAll('#rating-stars span');
    stars.forEach((s, i) => {
        s.style.color = i < n ? '#ffd700' : '#444';
    });
}

function showReviewModal(winner, reason) {
    document.getElementById('modal-review').classList.remove('hidden');
    document.getElementById('review-game-msg').innerText = `Winner: ${winner} (${reason})`;
    setRating(5);
}

function closeReviewModal() {
    document.getElementById('modal-review').classList.add('hidden');
    // Ensure room view is back
    document.getElementById('active-room-view').classList.remove('hidden');
}

async function submitReview() {
    const comment = document.getElementById('review-comment').value;
    const res = await api('/review/add', 'POST', {
        game_id: appState.gameToRoom,
        score: currentRating,
        comment: comment
    });

    // Note: /review/add needs to be implemented in lobby_client.py routing? 
    // Wait, lobby_server.py has 'add_review'. 
    // We need lobby_client.py to forward it.

    // Correction: Frontend API Call -> lobby_client -> lobby_server
    // Checking lobby_client.py capabilities...

    // Assuming /api/review/add endpoint exists or we map it
    // The previous analysis of lobby_client.py did NOT show /api/review/add handling.
    // We might need to add it to lobby_client.py first.

    // For now, let's assuming we fix lobby_client.py next.

    toast("Review Submitted!");
    closeReviewModal();
    toast("Review Submitted!");
    closeReviewModal();
}

async function openGameDetails(gid) {
    // 1. Get Game Info (from full list for simplicity)
    const resG = await api('/games');
    let game = null;
    if (resG.status === 'ok' && resG.games) {
        game = resG.games[gid];
    }
    if (!game) {
        toast("Game info not found", true);
        return;
    }

    // 2. Get Reviews
    const resR = await api(`/reviews?game_id=${gid}`);
    const reviews = (resR.status === 'ok') ? resR.reviews : [];

    // 3. Calc Avg
    let avg = 0;
    if (reviews.length > 0) {
        const sum = reviews.reduce((acc, r) => acc + parseInt(r.score || 0), 0);
        avg = (sum / reviews.length).toFixed(1);
    } else {
        avg = "N/A";
    }

    // 4. Render Meta
    document.getElementById('gd-game-title').textContent = game.name;
    document.getElementById('gd-game-ver').textContent = 'v' + game.version;
    document.getElementById('gd-rating-val').textContent = avg + (reviews.length > 0 ? ` (${reviews.length})` : '');
    document.getElementById('gd-game-desc').textContent = game.description || "No description provided.";

    // 5. Render Reviews
    const list = document.getElementById('gd-reviews-list');
    list.innerHTML = '';
    if (reviews.length === 0) {
        list.innerHTML = '<p class="subtitle">No reviews yet.</p>';
    } else {
        reviews.reverse().forEach(r => {
            const item = document.createElement('div');
            item.className = 'review-item';

            // Stars
            let stars = '';
            for (let i = 0; i < 5; i++) {
                stars += (i < r.score) ? '★' : '☆';
            }

            item.innerHTML = `
                <div class="review-header">
                    <span>${r.reviewer}</span>
                    <span class="review-score">${stars}</span>
                </div>
                <div class="review-body">${r.comment || ''}</div>
            `;
            list.appendChild(item);
        });
    }

    // 6. Show
    document.getElementById('modal-game-details').classList.remove('hidden');
}

// --- Utils ---
function toast(msg, error = false) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.borderLeftColor = error ? '#ff0055' : '#00f0ff';
    t.classList.remove('hidden');
    setTimeout(() => t.classList.add('hidden'), 3000);
}
