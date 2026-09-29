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
    dialog.addEventListener('click', event => {
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

  document.querySelectorAll('[data-user-analyst]').forEach(select => {
    const form = select.closest('[data-user-form]') || select.closest('form');
    if (!form) return;
    const nameInput = form.querySelector('[data-user-name]');
    const emailInput = form.querySelector('[data-user-email]');
    const usernameInput = form.querySelector('[data-user-username]');

    select.addEventListener('change', () => {
      const option = select.options[select.selectedIndex];
      if (!option || !option.value) return;
      const analystName = option.dataset.analystName || '';
      const analystEmail = option.dataset.analystEmail || '';
      if (nameInput) nameInput.value = analystName;
      if (emailInput) emailInput.value = analystEmail;
      if (usernameInput && !usernameInput.value.trim() && analystEmail.includes('@')) {
        usernameInput.value = analystEmail.split('@')[0];
      }
    });
  });

  const isoToUTC = value => {
    if (!value) return null;
    const [year, month, day] = value.split('-').map(Number);
    if (!year || !month || !day) return null;
    return Date.UTC(year, month - 1, day);
  };

  const todayUTC = () => {
    const now = new Date();
    return Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  };

  const pocProgress = (startValue, endValue) => {
    const start = isoToUTC(startValue);
    const end = isoToUTC(endValue);
    if (start === null || end === null || end < start) {
      return { percent: 0, label: 'sem período', day: 0, total: 0 };
    }

    const oneDay = 86400000;
    const total = Math.floor((end - start) / oneDay) + 1;
    const today = todayUTC();

    if (today < start) return { percent: 0, label: `Dia 0 de ${total}`, day: 0, total };
    if (today >= end) return { percent: 100, label: `Dia ${total} de ${total}`, day: total, total };

    const day = Math.floor((today - start) / oneDay) + 1;
    const percent = Math.max(0, Math.min(100, Math.round((day / total) * 100)));
    return { percent, label: `Dia ${day} de ${total}`, day, total };
  };

  const renderPocProgress = container => {
    const info = pocProgress(container.dataset.pocStart, container.dataset.pocEnd);
    container.dataset.progressComputed = String(info.percent);
    container.style.setProperty('--value', info.percent);

    container.querySelectorAll('[data-progress-value]').forEach(el => {
      el.textContent = `${info.percent}%`;
    });
    container.querySelectorAll('[data-progress-bar]').forEach(el => {
      el.style.width = `${info.percent}%`;
    });
    container.querySelectorAll('[data-progress-label]').forEach(el => {
      el.textContent = info.label;
    });
    return info;
  };

  document.querySelectorAll('[data-poc-progress]').forEach(renderPocProgress);

  document.querySelectorAll('[data-poc-progress-input]').forEach(input => {
    const info = pocProgress(input.dataset.pocStart, input.dataset.pocEnd);
    input.value = `${info.percent}% · ${info.label}`;
  });

  document.querySelectorAll('[data-team-progress-panel]').forEach(panel => {
    const projectRows = [...panel.querySelectorAll('[data-team-project-progress]')];
    const badge = panel.querySelector('[data-team-average]');
    if (!badge || !projectRows.length) return;
    const values = projectRows.map(row => Number(row.dataset.progressComputed || 0));
    const avg = Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
    badge.textContent = `${avg}%`;
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
    const start = form.querySelector('input[data-poc-start]');
    const days = form.querySelector('input[data-poc-days]');
    const end = form.querySelector('input[data-poc-end]');
    if (!start || !days || !end) return;

    const refreshEnd = () => {
      end.value = addCalendarDaysInclusive(start.value, days.value);
      const progressInput = form.querySelector('[data-poc-progress-input]');
      if (progressInput) {
        const info = pocProgress(start.value, end.value);
        progressInput.dataset.pocStart = start.value;
        progressInput.dataset.pocEnd = end.value;
        progressInput.value = `${info.percent}% · ${info.label}`;
      }
    };

    start.addEventListener('input', refreshEnd);
    start.addEventListener('change', refreshEnd);
    days.addEventListener('input', refreshEnd);
    days.addEventListener('change', refreshEnd);

    product?.addEventListener('change', () => {
      const option = product.options[product.selectedIndex];
      if (option?.dataset.pocDays) days.value = option.dataset.pocDays;
      refreshEnd();
    });

    refreshEnd();
  });

  document.querySelectorAll('[data-result-lab-form]').forEach(form => {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const projectId = form.dataset.projectId;
      const submit = form.querySelector('button[type="submit"]');
      const originalText = submit?.textContent || 'Salvar resultados';
      if (submit) {
        submit.disabled = true;
        submit.textContent = 'Salvando...';
      }

      const referenceDate = form.querySelector('[name="reference_date"]')?.value || '';
      const metrics = [
        ['Tentativas', 'tentativas'],
        ['Atendidas', 'atendidas'],
        ['CPC', 'cpc'],
        ['Acordo', 'acordo'],
      ];

      try {
        for (const [metricName, fieldName] of metrics) {
          const payload = new FormData();
          payload.append('name', metricName);
          payload.append('current_value', form.querySelector(`[name="${fieldName}"]`)?.value || '0');
          payload.append('target_value', '');
          payload.append('unit', '');
          payload.append('reference_date', referenceDate);
          const response = await fetch(`/projects/${projectId}/metrics`, {
            method: 'POST',
            body: payload,
            credentials: 'same-origin',
          });
          if (!response.ok) throw new Error(`Falha ao salvar ${metricName}`);
        }
        window.location.reload();
      } catch (error) {
        console.error(error);
        alert('Não foi possível salvar todos os indicadores. Tente novamente.');
        if (submit) {
          submit.disabled = false;
          submit.textContent = originalText;
        }
      }
    });
  });
})();
