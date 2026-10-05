(() => {
  const toggle = document.querySelector('[data-menu-toggle]');
  const nav = document.querySelector('[data-nav]');
  if (toggle && nav) {
    const close = () => { toggle.setAttribute('aria-expanded', 'false'); nav.classList.remove('is-open'); };
    toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') !== 'true';
      toggle.setAttribute('aria-expanded', String(open));
      nav.classList.toggle('is-open', open);
    });
    nav.addEventListener('click', event => { if (event.target.closest('a')) close(); });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
        close(); toggle.focus();
      }
    });
    matchMedia('(min-width: 801px)').addEventListener('change', close);
  }

  document.querySelectorAll('[data-copy]').forEach(button => {
    button.addEventListener('click', async () => {
      const source = document.getElementById(button.dataset.copy);
      if (!source) return;
      if (!navigator.clipboard) { button.textContent = 'Select commands to copy'; return; }
      try {
        await navigator.clipboard.writeText(source.tagName === 'PRE' ? source.textContent : source.innerText);
        const old = button.textContent;
        button.textContent = 'Copied';
        setTimeout(() => { button.textContent = old; }, 1800);
      } catch { button.textContent = 'Select commands to copy'; }
    });
  });

  const examples = [
    ['01 / ASK — plain language', 'show me the five largest folders here', 'Your request stays in the session until you ask for a draft.'],
    ['02 / DRAFT — Ctrl+G', 'du -h --max-depth=1 . | sort -hr | head -5', 'A suggestion appears in the editable Bash buffer. Nothing has run.'],
    ['03 / DECIDE — your Enter key', 'du -h --max-depth=1 . | sort -hr | head -5', 'Review the command, change it, or discard it. Only you execute.']
  ];
  const buttons = document.querySelectorAll('[data-demo]');
  const label = document.getElementById('demo-label');
  const command = document.getElementById('demo-command');
  const result = document.getElementById('demo-result');
  if (label && command && result) buttons.forEach(button => button.addEventListener('click', () => {
    const example = examples[Number(button.dataset.demo)];
    if (!example) return;
    buttons.forEach(item => { item.classList.toggle('is-active', item === button); item.setAttribute('aria-pressed', String(item === button)); });
    label.textContent = example[0];
    command.textContent = `❯ ${example[1]}`;
    result.textContent = example[2];
  }));
  // Animate entry, not visibility: content is readable even if JS or IO fails.
  if ('IntersectionObserver' in window && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('entered');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: .15 });
    document.querySelectorAll('.section-heading, .mode-grid article, .providers > div').forEach(el => observer.observe(el));
  }
})();
