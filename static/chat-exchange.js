// ── Модалка обмена сменами ────────────────────────────────────────────────
function openExchangeModal() {
  const modal = document.getElementById('exchange-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  document.getElementById('exchange-error').classList.add('hidden');
  document.getElementById('exchange-error').textContent = '';
  document.getElementById('exchange-step-1').classList.remove('hidden');
  document.getElementById('exchange-step-2').classList.add('hidden');
  document.getElementById('exchange-their-booking').innerHTML = '';
  loadMyBookings();
}

function closeExchangeModal() {
  const modal = document.getElementById('exchange-modal');
  if (modal) modal.classList.add('hidden');
}

function showExchangeError(message) {
  const el = document.getElementById('exchange-error');
  el.textContent = message;
  el.classList.remove('hidden');
}

async function loadMyBookings() {
  const select = document.getElementById('exchange-my-booking');
  select.innerHTML = '';
  try {
    const res = await fetch('/api/my-upcoming-shifts');
    if (!res.ok) throw new Error('Не удалось загрузить ваши смены');
    const shifts = await res.json();
    if (!shifts || shifts.length === 0) {
      select.innerHTML = '<option value="">Нет доступных смен для обмена</option>';
      select.disabled = true;
      return;
    }
    select.disabled = false;
    shifts.forEach(function(s) {
      const opt = document.createElement('option');
      opt.value = s.booking_id;
      opt.textContent = s.direction + ', ' + s.date + ' ' + s.time;
      select.appendChild(opt);
    });
  } catch (e) {
    showExchangeError(e.message);
  }
}

async function loadReceiverBookings() {
  const mySelect = document.getElementById('exchange-my-booking');
  if (!mySelect.value || mySelect.disabled) {
    showExchangeError('Выберите свою смену');
    return;
  }

  const theirSelect = document.getElementById('exchange-their-booking');
  theirSelect.innerHTML = '';
  try {
    const res = await fetch('/api/users/' + WITH_ID + '/upcoming-shifts');
    if (!res.ok) throw new Error('Не удалось загрузить смены собеседника');
    const shifts = await res.json();
    if (!shifts || shifts.length === 0) {
      theirSelect.innerHTML = '<option value="">У собеседника нет доступных смен</option>';
      theirSelect.disabled = true;
    } else {
      theirSelect.disabled = false;
      shifts.forEach(function(s) {
        const opt = document.createElement('option');
        opt.value = s.booking_id;
        opt.textContent = s.direction + ', ' + s.date + ' ' + s.time;
        theirSelect.appendChild(opt);
      });
    }
    document.getElementById('exchange-step-1').classList.add('hidden');
    document.getElementById('exchange-step-2').classList.remove('hidden');
    document.getElementById('exchange-error').classList.add('hidden');
  } catch (e) {
    showExchangeError(e.message);
  }
}

async function submitExchange() {
  const senderBookingId = document.getElementById('exchange-my-booking').value;
  const receiverBookingId = document.getElementById('exchange-their-booking').value;
  if (!senderBookingId || !receiverBookingId) {
    showExchangeError('Выберите обе смены');
    return;
  }

  const form = new FormData();
  form.append('receiver_id', WITH_ID);
  form.append('sender_booking_id', senderBookingId);
  form.append('receiver_booking_id', receiverBookingId);

  try {
    const res = await fetch('/api/exchange-proposals', { method: 'POST', body: form });
    if (!res.ok) {
      const data = await res.json().catch(function() { return {}; });
      throw new Error(data.detail || 'Ошибка создания предложения');
    }
    closeExchangeModal();
    location.reload();
  } catch (e) {
    showExchangeError(e.message);
  }
}

function renderExchangeCard(msg) {
  const p = msg.payload;
  const isSender = msg.sender_id === ME;
  const mySlot = isSender ? p.sender_slot : p.receiver_slot;
  const theirSlot = isSender ? p.receiver_slot : p.sender_slot;
  const status = p.status;

  function formatSlot(slot) {
    return slot.direction + ', ' + slot.date + ' ' + slot.time;
  }

  const statusLabels = {
    accepted: 'Принято',
    declined: 'Отклонено',
    cancelled: 'Отменено',
    expired: 'Истекло'
  };

  let actionsHtml = '';
  if (status === 'pending') {
    if (isSender) {
      actionsHtml = '<button onclick="handleExchangeAction(' + p.proposal_id + ', \'cancel\')" class="px-3 py-1 rounded-lg text-xs bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-700 transition">Отменить</button>';
    } else {
      actionsHtml =
        '<button onclick="handleExchangeAction(' + p.proposal_id + ', \'accept\')" class="px-3 py-1 rounded-lg text-xs bg-green-600 hover:bg-green-700 text-white transition">Принять</button>' +
        '<button onclick="handleExchangeAction(' + p.proposal_id + ', \'decline\')" class="px-3 py-1 rounded-lg text-xs bg-red-100 hover:bg-red-200 text-red-700 transition">Отказаться</button>';
    }
  } else {
    actionsHtml = '<span class="text-xs font-medium text-gray-500 dark:text-gray-400">' + (statusLabels[status] || status) + '</span>';
  }

  return (
    '<div class="p-3 rounded-xl border border-indigo-200 bg-indigo-50 dark:bg-indigo-900/40 dark:border-indigo-700 min-w-[220px] text-gray-900 dark:text-gray-100">' +
      '<div class="text-xs font-bold text-indigo-700 dark:text-indigo-200 mb-2">🔄 Обмен сменами</div>' +
      '<div class="flex items-center justify-between gap-2 text-sm mb-1">' +
        '<div class="text-center flex-1 min-w-0">' +
          '<div class="text-xs text-gray-600 dark:text-gray-300">' + (isSender ? 'Вы' : 'Собеседник') + '</div>' +
          '<div class="font-medium text-gray-900 dark:text-gray-100 truncate">' + formatSlot(mySlot) + '</div>' +
        '</div>' +
        '<div class="text-gray-500 dark:text-gray-400 flex-shrink-0">→</div>' +
        '<div class="text-center flex-1 min-w-0">' +
          '<div class="text-xs text-gray-600 dark:text-gray-300">' + (isSender ? 'Собеседник' : 'Вы') + '</div>' +
          '<div class="font-medium text-gray-900 dark:text-gray-100 truncate">' + formatSlot(theirSlot) + '</div>' +
        '</div>' +
      '</div>' +
      '<div class="flex items-center gap-2 mt-2">' + actionsHtml + '</div>' +
      '<div class="text-[10px] text-gray-500 dark:text-gray-400 mt-1 text-right">' + msg.time + '</div>' +
    '</div>'
  );
}

async function handleExchangeAction(proposalId, action) {
  if (!confirm('Вы уверены?')) return;
  try {
    const res = await fetch('/api/exchange-proposals/' + proposalId + '/' + action, { method: 'POST' });
    if (!res.ok) {
      const data = await res.json().catch(function() { return {}; });
      throw new Error(data.detail || 'Ошибка обработки предложения');
    }
    location.reload();
  } catch (e) {
    alert(e.message);
  }
}
