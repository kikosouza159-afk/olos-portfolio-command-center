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

  const addCalendarDaysInclusive = (startValue, daysValue) => {
    if (!startValue) return '';
    const days = Math.max(1, parseInt(daysValue || '15', 10) || 15);
    const [year, month, day] = startValue.split('-').map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));
    date.setUTCDate(date.getUTCDate() + days - 1);
    return date.toISOString().slice(0, 10);
  };

  document.querySelectorAll('form').forEach(form => {
    const product = form.querySelector('[data-poc-product]');
    const start = form.querySelector('[data-poc-start]');
    const days = form.querySelector('[data-poc-days]');
    const end = form.querySelector('[data-poc-end]');
    if (!start || !days || !end) return;

    const refreshEnd = () => {
      end.value = addCalendarDaysInclusive(start.value, days.value);
    };

    start.addEventListener('change', refreshEnd);
    days.addEventListener('input', refreshEnd);
    product?.addEventListener('change', () => {
      const option = product.options[product.selectedIndex];
      if (option?.dataset.pocDays) days.value = option.dataset.pocDays;
      refreshEnd();
    });

    refreshEnd();
  });
})();
