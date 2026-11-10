// CampusMeet Web Client (Lab 7)
const API_BASE = window.API_BASE_URL || '/api/v1';

let currentRole = 'artem';
let currentToken = 'demo-artem';
let currentType = '';
let searchQuery = '';
let activeEvent = null;

// DOM Elements
const eventsContainer = document.getElementById('eventsContainer');
const userSelector = document.getElementById('userSelector');
const searchInput = document.getElementById('searchInput');
const tabButtons = document.querySelectorAll('.tab-btn');
const regModal = document.getElementById('regModal');
const closeModal = document.getElementById('closeModal');
const submitRegBtn = document.getElementById('submitRegBtn');
const modalEventTitle = document.getElementById('modalEventTitle');
const modalEventDetails = document.getElementById('modalEventDetails');
const modalUserName = document.getElementById('modalUserName');
const modalWaitlist = document.getElementById('modalWaitlist');
const modalForm = document.getElementById('modalForm');
const modalResult = document.getElementById('modalResult');

// Update Token on Role Change
userSelector.addEventListener('change', async (e) => {
  currentRole = e.target.value;
  try {
    const res = await fetch(`${API_BASE}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: currentRole })
    });
    if (res.ok) {
      const data = await res.json();
      currentToken = data.access_token;
    } else {
      currentToken = `demo-${currentRole}`;
    }
  } catch (err) {
    currentToken = `demo-${currentRole}`;
  }
  loadEvents();
});

// Category Tabs
tabButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    tabButtons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentType = btn.dataset.type;
    loadEvents();
  });
});

// Search Input
let debounceTimer;
searchInput.addEventListener('input', (e) => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    searchQuery = e.target.value.trim();
    loadEvents();
  }, 250);
});

// Fetch and render events
async function loadEvents() {
  eventsContainer.innerHTML = '<div style="color: var(--text-muted); font-size: 14px;">Загрузка каталога мероприятий...</div>';
  try {
    const url = new URL(`${window.location.origin}${API_BASE}/events`);
    if (currentType) url.searchParams.set('event_type', currentType);
    if (searchQuery) url.searchParams.set('q', searchQuery);

    const res = await fetch(url.toString(), {
      headers: { 'Authorization': `Bearer ${currentToken}` }
    });
    const data = await res.json();
    renderEvents(data.items || []);
  } catch (err) {
    eventsContainer.innerHTML = `<div style="color: var(--danger); font-size: 14px;">Ошибка подключения к API: ${err.message}</div>`;
  }
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString('ru-RU', {
      day: 'numeric',
      month: 'long',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return iso;
  }
}

function renderEvents(events) {
  if (!events.length) {
    eventsContainer.innerHTML = '<div style="color: var(--text-muted); font-size: 14px; grid-column: 1/-1;">События по заданным фильтрам не найдены.</div>';
    return;
  }

  eventsContainer.innerHTML = events.map(ev => {
    const total = ev.capacity_limit || 1;
    const free = ev.free_spots !== undefined ? ev.free_spots : total;
    const occupied = Math.max(0, total - free);
    const percent = Math.min(100, Math.round((occupied / total) * 100));
    const isFull = free === 0;

    return `
      <div class="event-card">
        <div>
          <div class="card-header-line">
            <span class="event-type-badge badge-${ev.event_type}">${ev.event_type}</span>
            <span style="font-size: 12px; color: ${isFull ? 'var(--accent-orange)' : 'var(--success)'}; font-family: var(--font-mono);">
              ${isFull ? '● Лист ожидания' : '● Регистрация открыта'}
            </span>
          </div>
          <h3 class="card-title" style="margin-top: 10px;">${ev.title}</h3>
          
          <div class="card-meta" style="margin-top: 12px;">
            <div class="meta-row">
              <span>📅</span>
              <span>${formatDate(ev.start_time)}</span>
            </div>
            <div class="meta-row">
              <span>📍</span>
              <span>ФПМИ БГУ, ауд. 512</span>
            </div>
          </div>
        </div>

        <div>
          <div class="quota-area" style="margin-bottom: 14px;">
            <div class="quota-labels">
              <span>Места: ${occupied} / ${total}</span>
              <span style="color: ${isFull ? 'var(--accent-orange)' : 'var(--text-secondary)'}; font-weight: 700;">
                ${isFull ? 'Заполнено' : `Свободно: ${free}`}
              </span>
            </div>
            <div class="progress-track">
              <div class="progress-fill ${isFull ? 'full' : ''}" style="width: ${percent}%;"></div>
            </div>
          </div>

          <button class="btn-primary" style="width: 100%; justify-content: center;" onclick="openRegister('${ev.id}', '${encodeURIComponent(ev.title)}')">
            ${isFull ? 'Встать в Waitlist' : 'Забронировать билет'}
          </button>
        </div>
      </div>
    `;
  }).join('');
}

// Modal handling
window.openRegister = (eventId, encodedTitle) => {
  activeEvent = { id: eventId, title: decodeURIComponent(encodedTitle) };
  modalEventTitle.textContent = activeEvent.title;
  modalEventDetails.textContent = `Идентификатор события: ${activeEvent.id}`;
  modalUserName.value = userSelector.options[userSelector.selectedIndex].text;
  modalForm.style.display = 'block';
  modalResult.style.display = 'none';
  regModal.classList.add('active');
};

closeModal.addEventListener('click', () => {
  regModal.classList.remove('active');
  activeEvent = null;
});

submitRegBtn.addEventListener('click', async () => {
  if (!activeEvent) return;
  submitRegBtn.disabled = true;
  submitRegBtn.textContent = 'Обработка запроса...';

  try {
    const res = await fetch(`${API_BASE}/events/${activeEvent.id}/registrations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${currentToken}`,
        'Idempotency-Key': `web-${Date.now()}`
      },
      body: JSON.stringify({
        join_waitlist: modalWaitlist.checked
      })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.message || 'Ошибка бронирования');
    }

    // Success View
    modalForm.style.display = 'none';
    modalResult.style.display = 'block';
    modalResult.innerHTML = `
      <div style="text-align: center; color: var(--success); font-size: 28px; margin-bottom: 8px;">✓</div>
      <h4 style="text-align: center; font-size: 16px; margin-bottom: 4px;">
        ${data.status === 'registered' ? 'Билет успешно оформлен!' : 'Вы добавлены в лист ожидания!'}
      </h4>
      <p style="text-align: center; font-size: 13px; color: var(--text-muted); margin-bottom: 14px;">
        Статус бронирования: <strong>${data.status}</strong>
      </p>

      <div class="ticket-preview">
        <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Билет участника</div>
        <div class="ticket-code">${data.ticket_code}</div>
        <div style="font-size: 11px; color: var(--text-secondary); word-break: break-all; margin-top: 6px;">
          Токен: ${data.qr_payload || data.ticket_code}
        </div>
      </div>

      <div style="margin-top: 18px; display: flex; gap: 8px;">
        <a href="/mobile/?ticket_id=${data.id}" target="_blank" class="btn-primary" style="flex: 1; justify-content: center; text-decoration: none;">
          Открыть в приложении
        </a>
        <button class="btn-secondary" onclick="regModal.classList.remove('active'); loadEvents();" style="flex: 1; justify-content: center;">
          Готово
        </button>
      </div>
    `;
  } catch (err) {
    alert(`Ошибка регистрации: ${err.message}`);
  } finally {
    submitRegBtn.disabled = false;
    submitRegBtn.textContent = 'Подтвердить бронирование';
  }
});

// Initial Load
loadEvents();
