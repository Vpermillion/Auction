(() => {
  const key = 'auction-house-pages-demo-v1';
  const mn = document.documentElement.lang === 'mn';
  const labels = mn ? {
    open: 'Нээлттэй', closed: 'Хаагдсан', closes: 'Хаагдах хугацаа',
    start: 'Эхлэх үнэ', current: 'Одоогийн үнэ', winner: 'Ялсан үнэ', you: 'Таны санал',
    empty: 'Үнийн санал ирээгүй', saved: 'Туршилтын санал хадгалагдлаа',
    storage: 'Санал өгөхийн тулд хөтчийн хадгалалтыг идэвхжүүлнэ үү.',
    ended: 'Туршилтын дуудлага худалдаа хаагдлаа.', minimum: 'Саналын доод үнэ',
  } : {
    open: 'Open', closed: 'Closed', closes: 'Closes',
    start: 'Starting price', current: 'Current bid', winner: 'Winning bid', you: 'Your bid',
    empty: 'No bids yet', saved: 'Demo bid saved',
    storage: 'Enable browser storage to place a demo bid.',
    ended: 'This demo auction has ended.', minimum: 'Minimum bid',
  };
  const number = new Intl.NumberFormat(mn ? 'mn-MN' : 'en-US');
  const date = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Ulaanbaatar', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  });

  function money(value) {
    return number.format(value) + ' ₮';
  }

  function setText(element, value) {
    if (element && element.textContent !== value) element.textContent = value;
  }

  function showTime(element, timestamp) {
    const stamp = new Date(timestamp);
    const parts = Object.fromEntries(date.formatToParts(stamp).map(({type, value}) => [type, value]));
    element.dateTime = stamp.toISOString();
    setText(element, parts.year + '.' + parts.month + '.' + parts.day + ' · ' + parts.hour + ':' + parts.minute + ' UBT');
  }

  function load() {
    try {
      const value = JSON.parse(localStorage.getItem(key));
      if (value && Number.isFinite(value.started) && value.bids && typeof value.bids === 'object') return value;
    } catch (_) {
      // The catalogue can still be browsed with storage disabled.
    }
    return {started: Date.now(), bids: {}};
  }

  function save(value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (_) {
      return false;
    }
  }

  let saved = load();
  let storageAvailable = save(saved);
  const catalogue = Array.from(document.querySelectorAll('[data-demo-card]'), element => ({
    element, lot: JSON.parse(element.dataset.demoCard),
  }));
  const list = document.querySelector('[data-demo-list]');
  const filters = Array.from(document.querySelectorAll('[data-demo-filter]'));
  const requestedScope = new URLSearchParams(location.search).get('status');
  const scope = filters.length && ['open', 'closed'].includes(requestedScope)
    ? requestedScope : (list?.dataset.demoList || 'all');
  const featured = document.querySelector('[data-demo-feature]');
  const featuredLot = featured ? JSON.parse(featured.dataset.demoFeature) : null;
  const detail = document.querySelector('[data-demo-detail]');
  const detailLot = detail ? JSON.parse(detail.dataset.demoDetail) : null;
  const form = document.querySelector('#demo-bid-form');
  const amount = form?.elements.amount;
  const submit = form?.querySelector('button');
  const feedback = document.querySelector('#demo-bid-feedback');
  const history = document.querySelector('#bid-history');
  let previousHistory = null;

  function view(lot, now) {
    if (lot.initialState === 'closed') return {state: 'closed'};
    const bids = saved.bids[lot.id] || [];
    let close = saved.started + lot.seconds * 1000;
    for (const bid of bids) close = Math.max(close, bid.time + lot.softClose * 1000);
    const latest = bids.at(-1);
    const price = latest ? latest.amount : lot.start;
    const state = now >= close ? 'closed' : 'open';
    return {
      bids, close, price, state,
      minimum: latest ? price + lot.increment : lot.start,
      priceLabel: latest ? (state === 'closed' ? labels.winner : labels.current) : labels.start,
    };
  }

  function showStatus(element, state) {
    element.classList.toggle('open', state === 'open');
    element.classList.toggle('closed', state === 'closed');
    setText(element.querySelector('[data-state-label]'), labels[state]);
  }

  function updateCatalogue(now) {
    let visible = 0;
    for (const {element, lot} of catalogue) {
      const current = view(lot, now);
      element.hidden = scope !== 'all' && current.state !== scope;
      if (!element.hidden) visible++;
      if (lot.initialState === 'closed') continue;
      showStatus(element.querySelector('.status'), current.state);
      setText(element.querySelector('.card-bottom small'), current.priceLabel);
      setText(element.querySelector('.card-bottom strong'), money(current.price));
      const count = current.bids.length;
      setText(element.querySelector('.card-timing span'), count + (mn ? ' санал' : count === 1 ? ' bid' : ' bids'));
      showTime(element.querySelector('.card-timing time'), current.close);
    }
    const empty = list?.querySelector('[data-demo-empty]');
    if (empty) empty.hidden = visible !== 0;
    setText(document.querySelector('[data-demo-count]'), visible + (mn ? ' бараа' : visible === 1 ? ' lot' : ' lots') + ' · MNT');
    if (featuredLot) {
      const current = view(featuredLot, now);
      featured.hidden = current.state !== 'open';
      setText(featured.querySelector('.feature-value small'), current.priceLabel);
      setText(featured.querySelector('.feature-value strong'), money(current.price));
    }
  }

  function updateHistory(bids) {
    const signature = JSON.stringify(bids);
    if (signature === previousHistory) return;
    previousHistory = signature;
    const rows = document.createDocumentFragment();
    if (!bids.length) {
      const empty = document.createElement('p');
      empty.className = 'caption';
      empty.textContent = labels.empty;
      rows.append(empty);
    }
    for (const bid of bids.slice().reverse()) {
      const row = document.createElement('div');
      row.className = 'bid-row';
      const bidder = document.createElement('span');
      bidder.textContent = labels.you;
      const time = document.createElement('time');
      showTime(time, bid.time);
      const price = document.createElement('strong');
      price.textContent = money(bid.amount);
      row.append(bidder, time, price);
      rows.append(row);
    }
    history.replaceChildren(rows);
  }

  function updateDetail(now) {
    if (!form) return;
    const current = view(detailLot, now);
    showStatus(document.querySelector('#live-state'), current.state);
    setText(document.querySelector('#live-price'), money(current.price));
    setText(document.querySelector('.bid-price small'), current.priceLabel);
    setText(document.querySelector('#closing-label'), current.state === 'open' ? labels.closes : labels.closed);
    showTime(document.querySelector('#closing-time'), current.close);
    const seconds = Math.max(0, Math.ceil((current.close - now) / 1000));
    const timeLeft = [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60];
    setText(document.querySelector('#countdown'), current.state === 'open'
      ? timeLeft.map(value => String(value).padStart(2, '0')).join(':') : labels.closed);
    setText(document.querySelector('#minimum-value'), money(current.minimum));
    if (Number(amount.min) !== current.minimum) {
      amount.min = current.minimum;
      if (amount.valueAsNumber < current.minimum) amount.value = current.minimum;
    }
    form.hidden = current.state === 'closed';
    submit.disabled = !storageAvailable || form.hidden;
    if (form.hidden) setText(feedback, labels.ended);
    else if (!storageAvailable) setText(feedback, labels.storage);
    updateHistory(current.bids);
  }

  function update() {
    const now = Date.now();
    updateCatalogue(now);
    updateDetail(now);
  }

  if (form) {
    form.addEventListener('submit', event => {
      event.preventDefault();
      if (!storageAvailable) return;
      saved = load();
      const now = Date.now();
      const current = view(detailLot, now);
      if (current.state !== 'open') {
        update();
        return;
      }
      const bid = amount.valueAsNumber;
      if (!Number.isSafeInteger(bid) || bid < current.minimum || bid > 1_000_000_000_000) {
        setText(feedback, labels.minimum + ' · ' + money(current.minimum));
        update();
        return;
      }
      const next = {...saved, bids: {...saved.bids, [detailLot.id]: [...current.bids, {amount: bid, time: now}]}};
      storageAvailable = save(next);
      if (storageAvailable) {
        saved = next;
        setText(feedback, labels.saved + ' · ' + money(bid));
      }
      update();
      if (storageAvailable) document.dispatchEvent(new Event('auction:bid-recorded'));
    });
  }

  for (const filter of filters) {
    if (filter.dataset.demoFilter === scope) filter.setAttribute('aria-current', 'page');
    else filter.removeAttribute('aria-current');
  }
  const language = document.querySelector('[data-demo-language]');
  if (language && filters.length && scope !== 'all') {
    const target = new URL(language.href);
    target.searchParams.set('status', scope);
    language.href = target.href;
  }
  const reset = document.querySelector('[data-demo-reset]');
  if (reset && storageAvailable) {
    reset.hidden = false;
    reset.addEventListener('click', () => {
      if (save({started: Date.now(), bids: {}})) location.reload();
    });
  }
  window.addEventListener('storage', event => {
    if (event.key === key) {
      saved = load();
      update();
    }
  });
  update();
  setInterval(update, 1000);
})();
