/* The server accepts bids and decides auction deadlines. */
document.querySelectorAll('.status-form').forEach(form => {
  const sync = () => {
    const [kind, value] = form.elements.outcome.value.split(':');
    form.elements.kind.value = kind;
    form.elements.value.value = value;
  };
  form.elements.outcome.addEventListener('change', sync);
  sync();
});

const page = document.querySelector('[data-auction]');
if (page) {
  const auction = page.dataset.auction;
  const endpoint = '/api/auctions/' + auction;
  const form = document.querySelector('#bid-form');
  const submit = document.querySelector('#bid-submit');
  const feedback = document.querySelector('#bid-feedback');
  const retry = document.querySelector('#retry-bid');
  const history = document.querySelector('#bid-history');
  const countdown = document.querySelector('#countdown');
  const closingTime = document.querySelector('#closing-time');
  const closingLabel = document.querySelector('#closing-label');
  const price = document.querySelector('#live-price');
  const priceLabel = document.querySelector('.bid-price small');
  const liveState = document.querySelector('#live-state');
  const stateLabel = liveState.querySelector('[data-state-label]');
  const minimum = document.querySelector('#minimum-value');
  const entry = document.querySelector('[data-bid-entry]');
  const syncStatus = document.querySelector('#sync-status');
  const mongolian = document.documentElement.lang === 'mn';
  const stateLabels = mongolian
    ? {open: 'Нээлттэй', closed: 'Хаагдсан', draft: 'Ноорог', cancelled: 'Цуцалсан', suspended: 'Түдгэлзүүлсэн'}
    : {open: 'Open', closed: 'Closed', draft: 'Draft', cancelled: 'Cancelled', suspended: 'Suspended'};
  const priceLabels = mongolian
    ? {open: 'Одоогийн үнэ', closed: 'Ялсан үнэ', last: 'Сүүлийн санал', start: 'Эхлэх үнэ'}
    : {open: 'Current bid', closed: 'Winning bid', last: 'Last bid', start: 'Starting price'};
  const number = new Intl.NumberFormat(mongolian ? 'mn-MN' : 'en-US');
  const money = value => number.format(value) + ' ₮';
  const date = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Ulaanbaatar', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
  });
  const localTime = seconds => {
    const parts = Object.fromEntries(date.formatToParts(new Date(seconds * 1000)).map(({type, value}) => [type, value]));
    return parts.year + '.' + parts.month + '.' + parts.day + ' · ' + parts.hour + ':' + parts.minute + ' UBT';
  };
  const writeText = (element, value) => {
    if (element && element.textContent !== value) element.textContent = value;
  };

  let close = Number(page.dataset.close);
  let serverTime = Number(page.dataset.serverTime);
  let syncedAt = performance.now();
  let auctionState = page.dataset.state;
  let historySignature = null;
  let pollNumber = 0;
  let appliedPoll = 0;
  // Keys are scoped to the tab, auction and public bidder alias.
  const storageKey = 'auction-house-pending-' + auction + '-' + page.dataset.bidder;
  let pending = null;
  let inFlight = false;

  if (form) {
    try {
      pending = JSON.parse(sessionStorage.getItem(storageKey));
    } catch (_) {
      // Private browsing may block storage.
    }
  }

  function savePending() {
    try {
      if (pending) sessionStorage.setItem(storageKey, JSON.stringify(pending));
      else sessionStorage.removeItem(storageKey);
    } catch (_) {
      // The in-memory request still permits retrying on this page.
    }
  }

  function setUncertain() {
    form.elements.amount.disabled = true;
    submit.disabled = true;
    retry.classList.remove('hidden');
    feedback.textContent = mongolian
      ? 'Сүүлийн саналыг баталгаажуулах шаардлагатай. Ижил хүсэлтийг дахин илгээхэд санал давхардахгүй.'
      : 'The last bid needs confirmation. Retry the same request to check its result without placing another bid.';
  }

  function tick() {
    if (auctionState !== 'open') {
      writeText(countdown, stateLabels[auctionState] || auctionState);
      return;
    }
    const remaining = Math.max(0, Math.ceil(close - (serverTime + (performance.now() - syncedAt) / 1000)));
    if (!remaining) {
      writeText(countdown, mongolian ? 'Хаагдахыг хүлээж байна' : 'Awaiting close');
      return;
    }
    const parts = [Math.floor(remaining / 3600), Math.floor(remaining % 3600 / 60), remaining % 60];
    writeText(countdown, parts.map(value => String(value).padStart(2, '0')).join(':'));
  }

  function showHistory(bids) {
    const signature = JSON.stringify(bids);
    if (signature === historySignature) return;
    historySignature = signature;
    const rows = document.createDocumentFragment();
    if (!bids.length) {
      const note = document.createElement('p');
      note.className = 'caption';
      note.textContent = mongolian ? 'Үнийн санал ирээгүй' : 'No bids yet';
      rows.append(note);
    }
    for (const bid of bids) {
      const row = document.createElement('div');
      row.className = 'bid-row';
      const alias = document.createElement('span');
      alias.textContent = bid.alias;
      const time = document.createElement('time');
      time.dateTime = new Date(bid.created_at * 1000).toISOString();
      time.textContent = localTime(bid.created_at);
      const amount = document.createElement('strong');
      amount.textContent = money(bid.amount);
      row.append(alias, time, amount);
      rows.append(row);
    }
    if (bids.length === 50) {
      const note = document.createElement('p');
      note.className = 'caption';
      note.textContent = mongolian ? 'Сүүлийн 50 үнийн санал' : 'Latest 50 bids';
      rows.append(note);
    }
    history.replaceChildren(rows);
  }

  async function refresh() {
    const poll = ++pollNumber;
    try {
      const response = await fetch(endpoint, {cache: 'no-store'});
      if (!response.ok) throw new Error('Unavailable');
      const state = await response.json();
      if (poll < appliedPoll) return;
      appliedPoll = poll;
      auctionState = state.state;
      close = state.closes_at;
      serverTime = state.server_time;
      syncedAt = performance.now();
      writeText(price, money(state.price));
      writeText(priceLabel, state.bids.length ? (priceLabels[auctionState] || priceLabels.last) : priceLabels.start);
      liveState.className = 'status ' + auctionState;
      writeText(stateLabel, stateLabels[auctionState] || auctionState);
      writeText(closingLabel, auctionState === 'closed'
        ? stateLabels.closed : (mongolian ? 'Хаагдах хугацаа' : 'Closes'));
      writeText(closingTime, localTime(close));
      closingTime.dateTime = new Date(close * 1000).toISOString();
      writeText(minimum, money(state.minimum));
      showHistory(state.bids);

      if (entry) entry.hidden = auctionState !== 'open';
      if (form && !pending && !inFlight) {
        form.elements.amount.min = state.minimum;
        if (Number(form.elements.amount.value) < state.minimum) form.elements.amount.value = state.minimum;
        submit.disabled = auctionState !== 'open';
      }
      writeText(syncStatus, auctionState === 'open'
        ? (mongolian ? 'Үнэ 5 секунд тутам шинэчлэгдэнэ.' : 'Prices update every 5 seconds.')
        : (mongolian ? 'Үнийн санал авахгүй.' : 'Bidding has ended.'));
    } catch (_) {
      if (poll >= appliedPoll) {
        writeText(syncStatus, mongolian ? 'Холболт тасарлаа. Үнэ шинэчлэгдээгүй байж болно.' : 'Connection interrupted. Prices may be out of date.');
      }
    }
    tick();
  }

  async function send() {
    if (inFlight || !pending) return;
    let acceptedBid = false;
    inFlight = true;
    retry.disabled = true;
    submit.disabled = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(endpoint + '/bids', {
        method: 'POST',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': document.querySelector('meta[name=csrf-token]').content
        },
        body: JSON.stringify(pending)
      });
      const result = await response.json();
      if (response.status >= 500 || (!response.ok && !result.error)) throw new Error('Uncertain result');
      pending = null;
      savePending();
      form.elements.amount.disabled = false;
      retry.classList.add('hidden');
      form.elements.request_key.value = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('');
      document.querySelector('#accept-bid').checked = false;
      const accepted = mongolian ? 'Санал бүртгэгдлээ · ' : 'Bid recorded · ';
      feedback.textContent = response.ok ? accepted + money(result.amount) : result.error;
      acceptedBid = response.ok;
    } catch (_) {
      setUncertain();
    } finally {
      clearTimeout(timeout);
      inFlight = false;
      retry.disabled = false;
    }
    await refresh();
    if (acceptedBid) document.dispatchEvent(new Event('auction:bid-recorded'));
  }

  if (form) {
    if (pending) {
      form.elements.amount.value = pending.amount;
      setUncertain();
    }
    form.addEventListener('submit', event => {
      event.preventDefault();
      if (inFlight || pending) return;
      pending = {amount: Number(form.elements.amount.value), request_key: form.elements.request_key.value};
      savePending();
      form.elements.amount.disabled = true;
      send();
    });
    retry.addEventListener('click', send);
  }
  tick();
  if (auctionState === 'open') {
    refresh();
    setInterval(tick, 1000);
    setInterval(refresh, 5000);
  }
}
