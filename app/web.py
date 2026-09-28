"""Minimal operator UI so a stranger can enqueue the demo job after deploy."""

from __future__ import annotations

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FastAPI + Procrastinate</title>
  <style>
    :root {
      --bg: #12140f;
      --panel: #1c1f17;
      --ink: #f3efe4;
      --muted: #b7b1a3;
      --line: #32362b;
      --accent: #c6f54e;
      --danger: #ff8a6a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 16px/1.5 ui-sans-serif, system-ui, sans-serif;
      background: radial-gradient(1200px 500px at 10% -10%, #2a311c, transparent), var(--bg);
      color: var(--ink);
    }
    main { max-width: 840px; margin: 0 auto; padding: 32px 20px 64px; }
    h1 { font-size: 1.6rem; margin: 0 0 8px; letter-spacing: -0.03em; }
    p, label, th, td, code { color: var(--muted); }
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      color: var(--ink);
      background: #00000033;
      padding: 0.1em 0.35em;
      border-radius: 4px;
    }
    .row { display: flex; gap: 16px; flex-wrap: wrap; margin: 24px 0; }
    section {
      flex: 1 1 280px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px;
    }
    .status { font-weight: 650; color: var(--accent); }
    .status.bad { color: var(--danger); }
    form { display: grid; gap: 12px; }
    input {
      width: 100%;
      padding: 10px 12px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: #0e100c;
      color: var(--ink);
    }
    button {
      border: 0;
      border-radius: 8px;
      padding: 10px 14px;
      font-weight: 650;
      cursor: pointer;
      background: var(--accent);
      color: #1a1e12;
    }
    button:disabled { opacity: 0.5; cursor: wait; }
    table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
    th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); }
    .err { color: var(--danger); min-height: 1.4em; }
    footer { margin-top: 28px; font-size: 0.9rem; }
  </style>
</head>
<body>
  <main>
    <h1>FastAPI + Procrastinate</h1>
    <p>Postgres-native job queue. The API enqueues; the worker drains. No Redis.</p>
    <div class="row">
      <section>
        <p>API <span id="api-status" class="status">checking…</span></p>
        <p>Database <span id="db-status" class="status">checking…</span></p>
        <form id="demo-form">
          <label>Message <input name="message" value="hello from Railway" maxlength="200" /></label>
          <label>Seconds <input name="seconds" type="number" min="0" max="30" step="0.5" value="2" /></label>
          <label>Bearer token (if <code>JOB_API_TOKEN</code> is set)
            <input name="token" placeholder="optional" autocomplete="off" />
          </label>
          <button type="submit">Enqueue demo job</button>
          <div id="form-error" class="err"></div>
        </form>
      </section>
      <section>
        <p>Recent jobs</p>
        <table>
          <thead><tr><th>ID</th><th>Status</th><th>Task</th></tr></thead>
          <tbody id="jobs"><tr><td colspan="3">No jobs yet.</td></tr></tbody>
        </table>
      </section>
    </div>
    <footer>
      Healthcheck: <code>GET /healthz</code> (200 even with an empty queue).
      Worker start: <code>python -m app.worker</code>.
    </footer>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const headers = () => {
      const token = document.querySelector('[name=token]').value.trim();
      return token ? { Authorization: 'Bearer ' + token } : {};
    };
    async function refresh() {
      try {
        const h = await fetch('/healthz');
        $('api-status').textContent = h.ok ? 'up' : 'down';
        $('api-status').className = 'status' + (h.ok ? '' : ' bad');
      } catch {
        $('api-status').textContent = 'down';
        $('api-status').className = 'status bad';
      }
      try {
        const r = await fetch('/readyz');
        $('db-status').textContent = r.ok ? 'reachable' : 'not ready';
        $('db-status').className = 'status' + (r.ok ? '' : ' bad');
      } catch {
        $('db-status').textContent = 'not ready';
        $('db-status').className = 'status bad';
      }
      try {
        const res = await fetch('/jobs', { headers: headers() });
        if (!res.ok) throw new Error(await res.text());
        const rows = await res.json();
        const body = $('jobs');
        if (!rows.length) {
          body.innerHTML = '<tr><td colspan="3">No jobs yet. Enqueue one.</td></tr>';
          return;
        }
        body.innerHTML = rows.map((j) =>
          `<tr><td>${j.id}</td><td>${j.status}</td><td>${j.task_name}</td></tr>`
        ).join('');
      } catch (err) {
        $('jobs').innerHTML = `<tr><td colspan="3">${err.message}</td></tr>`;
      }
    }
    $('demo-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.target;
      const button = form.querySelector('button');
      $('form-error').textContent = '';
      button.disabled = true;
      try {
        const res = await fetch('/jobs/demo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...headers() },
          body: JSON.stringify({
            message: form.message.value,
            seconds: Number(form.seconds.value),
          }),
        });
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.detail || res.statusText);
        await refresh();
      } catch (err) {
        $('form-error').textContent = err.message;
      } finally {
        button.disabled = false;
      }
    });
    refresh();
    setInterval(refresh, 2500);
  </script>
</body>
</html>
"""
