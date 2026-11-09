/* Progressive enhancement only: acceptance and deadlines always belong to the server. */
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
  const form = document.querySelector('#bid-form');
  const submit = document.querySelector('#bid-submit');
  const feedback = document.querySelector('#bid-feedback');
  const retry = document.querySelector('#retry-bid');
  const money = value => new Intl.NumberFormat(document.documentElement.lang === 'mn' ? 'mn-MN' : 'en-US').format(value) + ' ₮';
  const localTime = seconds => new Intl.DateTimeFormat('en-GB', {timeZone: 'Asia/Ulaanbaatar', dateStyle:'medium', timeStyle:'short'}).format(new Date(seconds*1000)) + ' UBT';
  let close = Number(page.dataset.close), serverTime = Number(page.dataset.serverTime), syncedAt = performance.now(), auctionState = null;
  // The key contains no private information. Storage is per browser tab and auction.
  const storageKey = 'auction-house-pending-' + auction + '-' + page.dataset.bidder;
  let pending = null, inFlight = false;
  try { pending = JSON.parse(sessionStorage.getItem(storageKey)); } catch (_) { /* Private browsing may block storage. */ }
  const savePending = () => { try { if (pending) sessionStorage.setItem(storageKey, JSON.stringify(pending)); else sessionStorage.removeItem(storageKey); } catch (_) {} };
  const setUncertain = () => {
    if (!form || !submit) return;
    form.elements.amount.disabled = true;
    submit.disabled = true;
    retry.classList.remove('hidden');
    feedback.textContent = 'The last request needs confirmation. Retry the same request to learn its result; it will not create a duplicate bid.';
  };
  if (pending && submit) { form.elements.amount.value = pending.amount; setUncertain(); }
  function tick() {
    if (auctionState && auctionState !== 'open') {
      document.querySelector('#countdown').textContent = 'Bidding ' + auctionState;
      return;
    }
    const remaining = Math.max(0, Math.ceil(close - (serverTime + (performance.now()-syncedAt)/1000)));
    const hours = Math.floor(remaining/3600), minutes = Math.floor(remaining%3600/60), seconds = remaining%60;
    document.querySelector('#countdown').textContent = remaining ? `${hours}h ${minutes}m ${seconds}s` : 'Awaiting server close';
  }
  async function refresh() {
    try {
      const response = await fetch('/api/auctions/' + auction, {cache:'no-store'});
      if (!response.ok) throw new Error('Unavailable');
      const state = await response.json();
      auctionState = state.state;
      close = state.closes_at; serverTime = state.server_time; syncedAt = performance.now();
      document.querySelector('#live-price').textContent = money(state.price);
      document.querySelector('.bid-price small').textContent = document.documentElement.lang === 'mn'
        ? (state.bids.length ? 'Одоогийн үнэ' : 'Эхлэх үнэ')
        : (state.bids.length ? 'Current bid' : 'Starting price');
      document.querySelector('#live-state').textContent = state.state;
      document.querySelector('#closing-time').textContent = localTime(state.closes_at);
      const history = document.querySelector('#bid-history');
      history.replaceChildren();
      if (!state.bids.length) history.textContent = 'No bids yet';
      state.bids.forEach(bid => {
        const row = document.createElement('div'); row.className = 'bid-row';
        for (const [tag, text] of [['span',bid.alias],['time',localTime(bid.created_at)],['strong',money(bid.amount)]]) {
          const node = document.createElement(tag); node.textContent = text; row.append(node);
        }
        history.append(row);
      });
      if (state.bids.length === 50) {
        const note = document.createElement('p'); note.className='caption'; note.textContent='Showing the latest 50 bids. Reload the page for the full history.'; history.append(note);
      }
      if (form) {
        form.elements.amount.min = state.minimum;
        if (!pending && Number(form.elements.amount.value) < state.minimum) form.elements.amount.value = state.minimum;
        if (submit && !pending) submit.disabled = state.state !== 'open';
        document.querySelector('#sync-status').textContent = state.state === 'open' ? 'Synced with server. Prices refresh every 5 seconds.' : 'Server status: ' + state.state + '. Reload for the final page.';
      }
    } catch (_) {
      const status = document.querySelector('#sync-status');
      if (status) status.textContent = 'Connection interrupted. Display may be stale. Only the server can accept a bid.';
    }
    tick();
  }
  async function send() {
    if (inFlight || !pending) return;
    inFlight = true; retry.disabled = true; submit.disabled = true;
    const controller = new AbortController(); const timeout = setTimeout(()=>controller.abort(), 12000);
    try {
      const response = await fetch('/api/auctions/' + auction + '/bids', {method:'POST', signal:controller.signal,
        headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name=csrf-token]').content}, body:JSON.stringify(pending)});
      const result = await response.json();
      if (response.status >= 500) throw new Error('Uncertain result');
      if (!response.ok && !result.error) throw new Error('Uncertain result');
      pending = null; savePending();
      form.elements.amount.disabled = false; retry.classList.add('hidden');
      form.elements.request_key.value = crypto.randomUUID();
      feedback.textContent = response.ok ? (result.replay ? 'This bid was already accepted. No duplicate was created.' : 'Bid accepted and recorded: ' + money(result.amount)) : result.error;
      document.querySelector('#accept-bid').checked = false;
      await refresh();
    } catch (_) { setUncertain(); }
    finally {clearTimeout(timeout); inFlight=false;retry.disabled=false;}
  }
  if (submit) {
    form.addEventListener('submit', event => {
      event.preventDefault();
      if (inFlight || pending) return;
      pending = {amount:Number(form.elements.amount.value), request_key:form.elements.request_key.value}; savePending();
      form.elements.amount.disabled=true; send();
    });
    retry.addEventListener('click', send);
  }
  tick(); refresh(); setInterval(tick,1000); setInterval(refresh,5000);
}
