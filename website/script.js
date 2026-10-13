const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const year = document.getElementById('year');
if (year) year.textContent = new Date().getFullYear();

const revealNodes = document.querySelectorAll('[data-reveal]');
if (prefersReducedMotion || !('IntersectionObserver' in window)) {
  revealNodes.forEach((node) => node.classList.add('is-visible'));
} else {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
  revealNodes.forEach((node) => observer.observe(node));
}

const counters = document.querySelectorAll('[data-counter]');
if (!prefersReducedMotion && 'IntersectionObserver' in window) {
  const counterObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const node = entry.target;
      const target = Number(node.dataset.counter || 0);
      const suffix = node.dataset.suffix || '';
      const prefix = node.dataset.prefix || '';
      const duration = 900;
      const start = performance.now();
      const tick = (now) => {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        node.textContent = `${prefix}${Math.round(target * eased)}${suffix}`;
        if (progress < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
      counterObserver.unobserve(node);
    });
  }, { threshold: 0.65 });
  counters.forEach((node) => counterObserver.observe(node));
}

const hero = document.querySelector('.hero');
const core = document.querySelector('.ai-core-wrap');
const glows = document.querySelectorAll('.ambient-glow');
if (!prefersReducedMotion && hero && core && window.matchMedia('(pointer:fine)').matches) {
  hero.addEventListener('pointermove', (event) => {
    const rect = hero.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - 0.5;
    const y = (event.clientY - rect.top) / rect.height - 0.5;
    core.style.transform = `translate3d(${x * 16}px, ${y * 12}px, 0)`;
    glows.forEach((glow, index) => {
      const scale = index === 0 ? 28 : -18;
      glow.style.transform = `translate3d(${x * scale}px, ${y * scale}px, 0)`;
    });
  });
  hero.addEventListener('pointerleave', () => {
    core.style.transform = '';
    glows.forEach((glow) => { glow.style.transform = ''; });
  });
}

const cards = document.querySelectorAll('.tilt-card');
if (!prefersReducedMotion && window.matchMedia('(pointer:fine)').matches) {
  cards.forEach((card) => {
    card.addEventListener('pointermove', (event) => {
      const rect = card.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      card.style.setProperty('--rx', `${-y * 3}deg`);
      card.style.setProperty('--ry', `${x * 4}deg`);
    });
    card.addEventListener('pointerleave', () => {
      card.style.removeProperty('--rx');
      card.style.removeProperty('--ry');
    });
  });
}

const form = document.getElementById('interest-form');
const formNote = document.getElementById('form-note');
if (form && formNote) {
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const name = String(data.get('name') || '').trim();
    const email = String(data.get('email') || '').trim();
    const company = String(data.get('company') || '').trim();
    const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    formNote.classList.remove('success', 'error');
    if (!name || !company || !validEmail) {
      formNote.textContent = 'Enter your name, company, and a valid work email.';
      formNote.classList.add('error');
      return;
    }
    formNote.textContent = 'Preview only — lead capture will be connected before launch.';
    formNote.classList.add('success');
  });
}
