const year = document.getElementById('year');
if (year) year.textContent = new Date().getFullYear();

const reveals = document.querySelectorAll('.reveal');
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

if (prefersReducedMotion || !('IntersectionObserver' in window)) {
  reveals.forEach((el) => el.classList.add('visible'));
} else {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });

  reveals.forEach((el) => observer.observe(el));
}

const form = document.getElementById('interest-form');
const note = document.getElementById('form-note');

if (form && note) {
  form.addEventListener('submit', (event) => {
    event.preventDefault();

    const data = new FormData(form);
    const name = String(data.get('name') || '').trim();
    const email = String(data.get('email') || '').trim();
    const company = String(data.get('company') || '').trim();
    const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

    note.classList.remove('success', 'error');

    if (!name || !company || !validEmail) {
      note.textContent = 'Please enter your name, company, and a valid work email.';
      note.classList.add('error');
      return;
    }

    note.textContent = 'Preview received locally. Lead capture will be connected before launch.';
    note.classList.add('success');
  });
}
