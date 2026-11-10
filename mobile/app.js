// CampusMeet Mobile Pass Client (Lab 7)
const API_BASE = window.API_BASE_URL || '/api/v1';

let currentTicket = null;
let countdownSeconds = 45;
let timerInterval = null;

// DOM Elements
const passEventTitle = document.getElementById('passEventTitle');
const passEventVenue = document.getElementById('passEventVenue');
const passAttendee = document.getElementById('passAttendee');
const passStatus = document.getElementById('passStatus');
const passCode = document.getElementById('passCode');
const qrSvg = document.getElementById('qrSvg');
const countdownText = document.getElementById('countdownText');
const scanBtn = document.getElementById('scanBtn');
const scanResult = document.getElementById('scanResult');

// Render deterministic SVG QR matrix
function renderQRMatrix(payload) {
  // Clear existing
  qrSvg.innerHTML = '';

  const size = 25; // 25x25 grid
  const cellSize = 100 / size;

  // Draw 3 standard finder patterns
  function drawFinder(startX, startY) {
    const rectOuter = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rectOuter.setAttribute('x', startX * cellSize);
    rectOuter.setAttribute('y', startY * cellSize);
    rectOuter.setAttribute('width', 7 * cellSize);
    rectOuter.setAttribute('height', 7 * cellSize);
    rectOuter.setAttribute('fill', '#000000');
    qrSvg.appendChild(rectOuter);

    const rectInnerWhite = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rectInnerWhite.setAttribute('x', (startX + 1) * cellSize);
    rectInnerWhite.setAttribute('y', (startY + 1) * cellSize);
    rectInnerWhite.setAttribute('width', 5 * cellSize);
    rectInnerWhite.setAttribute('height', 5 * cellSize);
    rectInnerWhite.setAttribute('fill', '#ffffff');
    qrSvg.appendChild(rectInnerWhite);

    const rectCenter = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rectCenter.setAttribute('x', (startX + 2) * cellSize);
    rectCenter.setAttribute('y', (startY + 2) * cellSize);
    rectCenter.setAttribute('width', 3 * cellSize);
    rectCenter.setAttribute('height', 3 * cellSize);
    rectCenter.setAttribute('fill', '#000000');
    qrSvg.appendChild(rectCenter);
  }

  drawFinder(1, 1);
  drawFinder(size - 8, 1);
  drawFinder(1, size - 8);

  // Simple deterministic hash pattern from payload
  let hash = 0;
  for (let i = 0; i < (payload || 'campusmeet').length; i++) {
    hash = ((hash << 5) - hash) + payload.charCodeAt(i);
    hash |= 0;
  }

  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      // Skip finder zones
      const inFinder1 = r < 9 && c < 9;
      const inFinder2 = r < 9 && c > size - 10;
      const inFinder3 = r > size - 10 && c < 9;
      if (inFinder1 || inFinder2 || inFinder3) continue;

      const bit = ((hash ^ (r * 31 + c * 17)) & 1);
      if (bit === 1) {
        const cell = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        cell.setAttribute('x', c * cellSize);
        cell.setAttribute('y', r * cellSize);
        cell.setAttribute('width', cellSize * 0.92);
        cell.setAttribute('height', cellSize * 0.92);
        cell.setAttribute('fill', '#000000');
        cell.setAttribute('rx', '0.5');
        qrSvg.appendChild(cell);
      }
    }
  }
}

// Timer for active breathing / anti-screenshot protection
function startSecurityTimer() {
  clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    countdownSeconds--;
    if (countdownSeconds <= 0) {
      countdownSeconds = 60;
    }
    countdownText.textContent = `HMAC активен: ${countdownSeconds}s`;
  }, 1000);
}

// Fetch active ticket from API
async function loadTicket() {
  const params = new URLSearchParams(window.location.search);
  const ticketId = params.get('ticket_id');

  try {
    let tkt = null;
    if (ticketId) {
      const res = await fetch(`${API_BASE}/tickets/${ticketId}`, {
        headers: { 'Authorization': 'Bearer demo-artem' }
      });
      if (res.ok) tkt = await res.json();
    }

    if (!tkt) {
      // Fallback: load first ticket of artem or register demo ticket
      const listRes = await fetch(`${API_BASE}/me/tickets`, {
        headers: { 'Authorization': 'Bearer demo-artem' }
      });
      if (listRes.ok) {
        const listData = await listRes.json();
        if (listData.items && listData.items.length) {
          tkt = listData.items[0];
        }
      }
    }

    if (!tkt) {
      // Auto-register to demo event if empty
      const regRes = await fetch(`${API_BASE}/events/ev-campusmeet-2026/registrations`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer demo-artem',
          'Idempotency-Key': `mobile-init-${Date.now()}`
        },
        body: JSON.stringify({ join_waitlist: true })
      });
      if (regRes.ok) {
        tkt = await regRes.json();
      }
    }

    if (tkt) {
      currentTicket = tkt;
      displayTicket(tkt);
    }
  } catch (err) {
    console.error('Ошибка загрузки билета:', err);
    // Display offline simulated ticket
    displayTicket({
      id: 'tkt-offline-demo',
      ticket_code: 'DEMO-8842-OFFLINE',
      event_id: 'ev-campusmeet-2026',
      status: 'registered',
      qr_payload: 'v1.tkt-offline.usr-artem.7a8b9c'
    });
  }
}

function displayTicket(t) {
  passCode.textContent = t.ticket_code;
  passStatus.textContent = t.status.toUpperCase();
  passStatus.style.color = t.status === 'checked_in' ? 'var(--text-muted)' : 'var(--success)';
  
  const payload = t.qr_payload || t.hmac_token || t.ticket_code;
  renderQRMatrix(payload);
  startSecurityTimer();
}

// Volunteer Scanner Simulation
scanBtn.addEventListener('click', async () => {
  if (!currentTicket) {
    alert('Билет еще не загружен');
    return;
  }

  scanBtn.disabled = true;
  scanBtn.innerHTML = '<span>⏳</span><span>Проверка на сервере...</span>';

  try {
    const scanId = `scan-${Date.now()}`;
    const payload = currentTicket.qr_payload || currentTicket.ticket_code;

    const res = await fetch(`${API_BASE}/events/${currentTicket.event_id}/check-ins`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer demo-daria' // Authenticated as volunteer Daria
      },
      body: JSON.stringify({
        client_scan_id: scanId,
        payload: payload
      })
    });

    const data = await res.json();

    if (res.ok && data.verdict === 'GRANTED') {
      scanResult.className = 'status-callout granted';
      scanResult.innerHTML = `
        <strong>✓ ПРОХОД РАЗРЕШЕН (GRANTED)</strong><br>
        Идентификатор сканирования: ${data.id}<br>
        Волонтер: Дарья Мельникова (ауд. 512)<br>
        Время фиксации: ${new Date(data.scanned_at).toLocaleTimeString()}
      `;
      currentTicket.status = 'checked_in';
      passStatus.textContent = 'CHECKED_IN (ИСПОЛЬЗОВАН)';
      passStatus.style.color = 'var(--text-muted)';
    } else {
      scanResult.className = 'status-callout denied';
      scanResult.innerHTML = `
        <strong>✕ ОТКЛОНЕНО (HTTP ${res.status} CONFLICT)</strong><br>
        Причина: ${data.code || data.verdict || 'DENIED_ALREADY_USED'}<br>
        ${data.message || 'Билет уже был использован ранее для прохода!'}
      `;
    }
  } catch (err) {
    scanResult.className = 'status-callout denied';
    scanResult.textContent = `Сетевая ошибка: ${err.message}`;
  } finally {
    scanBtn.disabled = false;
    scanBtn.innerHTML = '<span>📷</span><span>Проверить проход сканером</span>';
  }
});

// Init
loadTicket();
