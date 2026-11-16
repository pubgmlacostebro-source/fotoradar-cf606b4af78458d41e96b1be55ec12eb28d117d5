(() => {
  'use strict';
  const repo = 'pubgmlacostebro-source/fotoradar-cf606b4af78458d41e96b1be55ec12eb28d117d5';
  const api = `https://api.github.com/repos/${repo}`;
  const old = document.getElementById('manualRunBtn');
  const button = document.createElement('button');
  button.className = old.className; button.id = old.id; button.textContent = 'Найти сейчас'; old.replaceWith(button);
  const note = document.getElementById('refreshNote');
  const description = button.parentElement.parentElement.querySelector('p.sub');
  if (description) description.textContent = 'Запускает новый сбор на GitHub и ждёт публикации результатов. При первом запуске подключите GitHub.';
  const settings = document.createElement('button'); settings.className = 'btn ghost'; settings.textContent = 'Подключение GitHub';
  button.insertAdjacentElement('afterend', settings);
  const dialog = document.createElement('dialog');
  dialog.innerHTML = `<h2>Запуск поиска</h2><p>Создайте Fine-grained token: Only select repositories → этот Фоторадар; Repository permissions → Actions: Read and write. Остальные права не добавляйте. Доступ Actions позволяет также управлять запусками этого репозитория.</p><p><a href="https://github.com/settings/personal-access-tokens/new?name=Fotoradar-run&target_name=pubgmlacostebro-source&expires_in=30&actions=write" target="_blank" rel="noopener noreferrer">Создать ключ на GitHub ↗</a></p><label>Ключ GitHub <input id="runToken" type="password" autocomplete="off" spellcheck="false" style="width:100%"></label><p>Ключ сохраняется в этом браузере и отправляется только api.github.com. После закрытия вкладки вводить его повторно не нужно. Для удаления нажмите «Забыть ключ». Когда срок ключа истечёт, подключите новый. Не присылайте ключ в чат.</p><p id="runSetupError" role="status"></p><button id="runConnect" class="btn">Подключить</button> <button id="runDisconnect" class="btn ghost">Отключить</button> <button id="runClose" class="btn ghost">Закрыть</button>`;
  document.body.append(dialog);
  const tokenStorageKey = 'fotoradar:github-token:' + repo;
  let token = '', busy = false;
  try { token = localStorage.getItem(tokenStorageKey) || ''; } catch (_) {}
  function updateConnection() { settings.textContent = token ? 'GitHub подключён' : 'Подключение GitHub'; }
  function forgetToken() {
    token = '';
    updateConnection();
    try { localStorage.removeItem(tokenStorageKey); return true; } catch (_) { return false; }
  }
  dialog.querySelector('#runDisconnect').textContent = 'Забыть ключ';
  // Keep storage scoped to this project. Never put credentials in URLs or repository files.
  updateConnection();
  settings.onclick = () => dialog.showModal();
  dialog.querySelector('#runClose').onclick = () => dialog.close();
  dialog.querySelector('#runDisconnect').onclick = () => {
    const removed = forgetToken();
    dialog.querySelector('#runToken').value = ''; dialog.close();
    note.textContent = removed ? 'Ключ удалён из этого браузера.' : 'Доступ отключён в этой вкладке. Браузер не разрешил удалить сохранённый ключ — очистите данные сайта в его настройках.';
  };
  async function request(path, options = {}) {
    const r = await fetch(api + path, { ...options, headers: { Accept:'application/vnd.github+json', Authorization:'Bearer ' + token, 'X-GitHub-Api-Version':'2022-11-28', ...(options.body ? {'Content-Type':'application/json'} : {}) }});
    if (r.status === 401) forgetToken();
    if (!r.ok) throw new Error(r.status === 401 ? 'Ключ недействителен или истёк. Подключите новый ключ.' : r.status === 403 || r.status === 404 ? 'Нет доступа. Проверьте выбранный репозиторий и право Actions: Read and write.' : `GitHub вернул HTTP ${r.status}.`);
    return r.status === 204 ? null : r.json();
  }
  dialog.querySelector('#runConnect').onclick = async () => {
    token = dialog.querySelector('#runToken').value.trim();
    dialog.querySelector('#runToken').value = '';
    const error = dialog.querySelector('#runSetupError'); error.textContent = '';
    if (!token) { error.textContent = 'Введите ключ.'; return; }
    try {
      await request('/actions/workflows/collect.yml');
      let remembered = false;
      try { localStorage.setItem(tokenStorageKey, token); remembered = true; } catch (_) {}
      updateConnection(); dialog.close();
      note.textContent = remembered ? 'Ключ сохранён в этом браузере. Нажмите «Найти сейчас».' : 'Подключено на эту вкладку. Браузер запретил сохранение ключа; после закрытия потребуется ввести его снова.';
    }
    catch (e) { forgetToken(); error.textContent = e.message; }
  };
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  button.onclick = async () => {
    if (busy) return;
    if (!token) { dialog.showModal(); return; }
    busy = true; button.disabled = true;
    try {
      const baseline = await request('/actions/workflows/collect.yml/runs?event=workflow_dispatch&per_page=30');
      const oldIds = new Set(baseline.workflow_runs.map(r => r.id));
      const requested = Date.now();
      await request('/actions/workflows/collect.yml/dispatches', {method:'POST', body:JSON.stringify({ref:'main'})});
      note.textContent = 'Поиск запрошен. Ожидаем запуска GitHub…';
      let run;
      for (let i=0; i<36 && !run; i++) {
        await sleep(5000);
        const data = await request('/actions/workflows/collect.yml/runs?event=workflow_dispatch&per_page=30');
        run = data.workflow_runs.filter(r => !oldIds.has(r.id) && Date.parse(r.created_at) >= requested - 5000).sort((a,b) => a.id-b.id)[0];
      }
      if (!run) throw new Error('GitHub не показал запуск за 3 минуты. Он мог остаться в очереди; проверьте Actions перед повторным запуском.');
      let done = false;
      for (let i=0; i<120; i++) {
        const state = await request('/actions/runs/' + run.id);
        if (state.status === 'completed') {
          if (state.conclusion !== 'success') throw new Error('Сбор не завершился успешно (' + state.conclusion + '). Подробности: ' + state.html_url);
          done = true; break;
        }
        note.textContent = state.status === 'in_progress' ? 'Собираем объявления и публикуем ленту…' : 'Поиск в очереди GitHub…';
        await sleep(5000);
      }
      if (!done) throw new Error('Запуск ещё не завершён за 10 минут. Проверьте Actions.');
      note.textContent = 'Сбор завершён. Ожидаем обновления сайта…';
      for (let i=0; i<36; i++) {
        const response = await fetch('data/status.json?t=' + Date.now(), {cache:'no-store'});
        if (response.ok && (await response.json()).checked * 1000 >= requested - 5000) {
          if (typeof load === 'function') await load();
          note.textContent = 'Поиск завершён. Показаны новые результаты, включая отсутствие совпадений.';
          return;
        }
        await sleep(5000);
      }
      throw new Error('Сбор успешен, но новая лента пока не доступна на сайте. Обновите результаты позже.');
    } catch (e) { note.textContent = 'Ошибка: ' + e.message; }
    finally { busy = false; button.disabled = false; }
  };
})();
