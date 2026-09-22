/* Presentation only. The server validates commands and resolves every outcome. */
(() => {
  const body = document.body;
  const loadedAt = Date.now();
  const serverNow = Number(body.dataset.now);
  let dirty = false;
  const selections = [...document.querySelectorAll('input[name="aircraft"]')];
  const missions = [...document.querySelectorAll('input[name="mission"]')];
  const dispatch = document.getElementById('dispatch-button');
  function estimate() {
    if (!dispatch) return;
    const mission = missions.find(input => input.checked);
    const chosen = selections.filter(input => input.checked);
    const cost = chosen.length * Number(mission.dataset.cost);
    const strength = chosen.reduce((sum, input) => sum + Number(input.dataset['power' + mission.value[0].toUpperCase() + mission.value.slice(1)]), 0);
    const coverage = strength / Number(mission.dataset.required);
    document.getElementById('selection-summary').textContent = chosen.length
      ? `${chosen.length} aircraft · ${cost} supplies committed`
      : 'Select aircraft above';
    document.getElementById('strength-summary').textContent = chosen.length
      ? `${coverage >= 1.25 ? 'Strong' : coverage >= 1 ? 'Adequate' : 'Light'} projected formation. ${Math.round(coverage * 100)}% of target requirement before combat losses.`
      : 'Your operations officer will estimate target strength.';
    const warning = document.getElementById('selection-warning');
    const overBudget = cost > Number(body.dataset.supplies);
    warning.hidden = !chosen.length || (coverage >= 1 && !overBudget);
    warning.textContent = overBudget ? 'Not enough supplies for this formation. Select fewer aircraft or choose the supporting operation.' : 'Likely partial target effect. More aircraft add strength, cost, and exposure.';
    dispatch.disabled = chosen.length === 0 || overBudget;
  }
  const draftKey = `formation:${body.dataset.tour}:${body.dataset.operation}`;
  // Preserve a draft when the commander starts a repair or recovery assignment.
  try {
    const draft = JSON.parse(sessionStorage.getItem(draftKey) || 'null');
    if (draft && dispatch) {
      missions.forEach(input => { input.checked = input.value === draft.mission; });
      if (!missions.some(input => input.checked)) missions[0].checked = true;
      selections.forEach(input => { input.checked = draft.aircraft.includes(input.value); });
      dirty = selections.some(input => input.checked);
    }
  } catch (_) { /* Storage is optional; commands still work without it. */ }
  [...selections, ...missions].forEach(input => input.addEventListener('change', () => {
    dirty = true;
    try {
      sessionStorage.setItem(draftKey, JSON.stringify({
        mission: missions.find(input => input.checked).value,
        aircraft: selections.filter(input => input.checked).map(input => input.value)
      }));
    } catch (_) { /* Private browsing may disallow storage. */ }
    estimate();
  }));
  estimate();
  document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  }));
  function clocks() {
    const now = serverNow + (Date.now() - loadedAt) / 1000;
    document.querySelectorAll('[data-countdown]').forEach(node => {
      const seconds = Math.max(0, Math.ceil(Number(node.dataset.countdown) - now));
      const minutes = Math.ceil(seconds / 60);
      node.textContent = seconds < 60 ? `${seconds}s` : minutes < 60 ? `${minutes}m` : `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`;
    });
  }
  clocks();
  if (body.dataset.poll === 'true') {
    setInterval(clocks, 1000);
    setInterval(async () => {
      if (document.hidden) return;
      try {
        const response = await fetch('/status', {cache: 'no-store'});
        if (!response.ok) return;
        const status = await response.json();
        if (status.revision !== Number(body.dataset.revision)) {
          if (dirty || document.querySelector('details[open]')) document.getElementById('update-notice').hidden = false;
          else location.reload();
        }
      } catch (_) { /* The next refresh will catch up without losing the mission. */ }
    }, 10000);
  }
})();
