(() => {
  document.querySelectorAll('[data-open]').forEach(btn => {
    btn.addEventListener('click', () => {
      const dialog = document.getElementById(btn.dataset.open);
      if (dialog) dialog.showModal();
    });
  });
  document.querySelectorAll('[data-close]').forEach(btn => {
    btn.addEventListener('click', () => btn.closest('dialog')?.close());
  });
  document.querySelectorAll('dialog').forEach(dialog => {
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });
  });

  document.querySelectorAll('[data-photo-input]').forEach(input => {
    input.addEventListener('change', () => {
      const file = input.files?.[0];
      if (!file) return;
      const target = document.getElementById(input.dataset.photoTarget);
      const fallback = document.getElementById(input.dataset.fallbackTarget || '');
      if (!target) return;
      target.src = URL.createObjectURL(file);
      target.classList.remove('hidden');
      fallback?.classList.add('hidden');
    });
  });
})();
