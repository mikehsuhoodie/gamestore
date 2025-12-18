
const API_BASE = '/api';
let currentUser = null;
let currentView = 'login';

// --- Auth Utils ---
async function apiCall(endpoint, data = null) {
    const opts = {
        method: data ? 'POST' : 'GET',
        headers: { 'Content-Type': 'application/json' },
    };
    if (data) opts.body = JSON.stringify(data);

    try {
        const res = await fetch(`${API_BASE}${endpoint}`, opts);
        return await res.json();
    } catch (e) {
        return { status: 'error', message: 'Network error' };
    }
}

function showToast(msg) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerText = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// --- Auth Flow ---
function switchAuth(type) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('auth-form').dataset.mode = type;
}

document.getElementById('auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const mode = e.target.dataset.mode || 'login';
    const user = document.getElementById('username').value;
    const pass = document.getElementById('password').value;
    const role = document.querySelector('input[name="role"]:checked').value;

    const res = await apiCall(`/${mode}`, { username: user, password: pass, role: role });

    if (res.status === 'ok') {
        if (mode === 'register') {
            showToast('Registered! Logging in...');
            // Auto login
            const lRes = await apiCall('/login', { username: user, password: pass, role: role });
            if (lRes.status === 'ok') enterApp(user, role);
        } else {
            enterApp(user, role);
        }
    } else {
        showToast(res.message);
    }
});

function enterApp(user, role) {
    currentUser = { user, role };
    document.getElementById('display-username').innerText = user;
    document.getElementById('display-role').innerText = role.toUpperCase();

    document.getElementById('view-login').classList.add('hidden');
    document.getElementById('view-dashboard').classList.remove('hidden');
    navTo('store');
}

function logout() {
    location.reload();
}

// --- Navigation ---
function navTo(page) {
    // Nav UI
    document.querySelectorAll('.nav-links li').forEach(l => l.classList.remove('active'));
    let activeLink = Array.from(document.querySelectorAll('.nav-links li')).find(l => l.innerText.toLowerCase().includes(page));
    if (activeLink) activeLink.classList.add('active');

    // Section UI
    ['store', 'library', 'rooms'].forEach(s => {
        document.getElementById(`section-${s}`).classList.add('hidden');
    });
    document.getElementById(`section-${page}`).classList.remove('hidden');

    // Load Data
    if (page === 'store') loadStore();
    if (page === 'library') loadLibrary();
    if (page === 'rooms') loadRooms();
}

// --- Store ---
async function loadStore() {
    const grid = document.getElementById('store-grid');
    grid.innerHTML = '<p>Loading...</p>';

    const res = await apiCall('/games');
    grid.innerHTML = '';

    if (res.status === 'error' || !res.games) {
        grid.innerHTML = '<p>Offline or Empty.</p>';
        return;
    }

    Object.keys(res.games).forEach(gid => {
        const g = res.games[gid];
        const card = document.createElement('div');
        card.className = 'game-card';
        card.innerHTML = `
            <div class="game-thumbnail">GAME</div>
            <div class="game-title">${g.name}</div>
            <div class="game-author">by ${g.author}</div>
            <button class="action-btn" onclick="installGame('${gid}')">INSTALL</button>
        `;
        grid.appendChild(card);
    });
}

async function installGame(gid) {
    showToast('Installing...');
    const res = await apiCall('/install', { game_id: gid });
    showToast(res.message);
}

// --- Library ---
async function loadLibrary() {
    const grid = document.getElementById('library-grid');
    grid.innerHTML = '<p>Loading...</p>';

    const res = await apiCall('/library');
    grid.innerHTML = '';

    if (!res.games || res.games.length === 0) {
        grid.innerHTML = '<p>No games installed.</p>';
        return;
    }

    res.games.forEach(g => {
        const card = document.createElement('div');
        card.className = 'game-card';
        card.innerHTML = `
            <div class="game-thumbnail" style="border-color: var(--primary)">MY GAME</div>
            <div class="game-title">${g.name || g.id}</div>
            <button class="action-btn" onclick="goToRooms('${g.id}')">PLAY</button>
        `;
        grid.appendChild(card);
    });
}

function goToRooms(gid) {
    // We strictly play via rooms in this architecture
    sessionStorage.setItem('activeGameId', gid);
    navTo('rooms');
}

// --- Rooms ---
async function loadRooms() {
    const grid = document.getElementById('room-list');
    grid.innerHTML = '<p>Scanning frequencies...</p>';

    // In a real app we might filter by activeGameId if set
    const res = await apiCall('/rooms');
    grid.innerHTML = '';

    const activeGameId = sessionStorage.getItem('activeGameId');

    if (!res.rooms || Object.keys(res.rooms).length === 0) {
        grid.innerHTML = '<p>No active sectors found.</p>';
        return;
    }

    Object.values(res.rooms).forEach(r => {
        // Filter if we came from library
        /* if(activeGameId && r.game_id !== activeGameId) return; */

        const row = document.createElement('div');
        row.className = 'glass-panel';
        row.style.padding = '15px';
        row.style.marginBottom = '10px';
        row.style.display = 'flex';
        row.style.justifyContent = 'space-between';
        row.style.alignItems = 'center';

        row.innerHTML = `
            <div>
                <strong>${r.name}</strong> <span style="font-size:0.8em; color:#888">(${r.game_id})</span>
                <div>Players: ${r.players.length}/2 | Status: ${r.status}</div>
            </div>
            <button class="cyber-btn small" style="width: auto; margin:0" onclick="joinRoom('${r.id}')">JOIN</button>
        `;
        grid.appendChild(row);
    });
}

async function showCreateRoom() {
    const gid = activeGameId = sessionStorage.getItem('activeGameId');
    if (!gid) {
        showToast("Select a game from Library first!");
        navTo('library');
        return;
    }
    const name = prompt("Sector Name:");
    if (name) {
        const res = await apiCall('/create_room', { game_id: gid, room_name: name });
        showToast(res.message);
        loadRooms();
    }
}

async function joinRoom(rid) {
    const res = await apiCall('/join_room', { room_id: rid });
    showToast(res.message);
    if (res.status === 'ok') {
        // Here we would enter the "Lobby/Waiting" state
        // For simplicity, just toast success.
    }
}
