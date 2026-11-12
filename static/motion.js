(() => {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  if (reduced.matches) return;

  const gallery = document.querySelector('.auction-hero');
  const photo = gallery?.querySelector('.gallery-interior');
  if (photo) {
    const reveal = () => gallery.classList.add('gallery-ready');
    if (photo.complete && photo.naturalWidth) reveal();
    else photo.addEventListener('load', reveal, {once: true});

    if (matchMedia('(hover: hover) and (pointer: fine)').matches) {
      let frame = 0;
      let x = 0;
      let y = 0;
      const paint = () => {
        frame = 0;
        gallery.style.setProperty('--gallery-x', x + 'px');
        gallery.style.setProperty('--gallery-y', y + 'px');
      };
      const schedule = () => {
        if (!frame) frame = requestAnimationFrame(paint);
      };
      gallery.addEventListener('pointermove', event => {
        if (reduced.matches || event.pointerType !== 'mouse') return;
        const bounds = gallery.getBoundingClientRect();
        x = 12 * ((event.clientX - bounds.left) / bounds.width - .5);
        y = 8 * ((event.clientY - bounds.top) / bounds.height - .5);
        schedule();
      }, {passive: true});
      gallery.addEventListener('pointerleave', () => {
        x = 0;
        y = 0;
        schedule();
      });
    }
  }

  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      for (const {target, isIntersecting} of entries) {
        if (!isIntersecting) continue;
        target.classList.remove('motion-pending');
        observer.unobserve(target);
      }
    }, {rootMargin: '0px 0px -24px 0px'});
    for (const target of document.querySelectorAll('.auction-card, .pilot-copy, .pilot-form, .detail-lower')) {
      if (target.getBoundingClientRect().top < innerHeight - 24) continue;
      target.classList.add('motion-reveal', 'motion-pending');
      observer.observe(target);
    }
  }

  document.addEventListener('auction:bid-recorded', () => {
    if (reduced.matches) return;
    const price = document.querySelector('#live-price');
    const panel = document.querySelector('.bid-console');
    price?.animate([
      {transform: 'translateY(5px)', opacity: .55},
      {transform: 'translateY(0)', opacity: 1},
    ], {duration: 360, easing: 'ease-out'});
    panel?.animate([
      {borderColor: '#f0ce8b'},
      {borderColor: getComputedStyle(panel).borderColor},
    ], {duration: 800, easing: 'ease-out'});
  });
})();
