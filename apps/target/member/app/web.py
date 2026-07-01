"""member 최소 UI(§7 '최소 스킨') — 회원 목록 + 가입 폼.

타깃 앱은 사람이 쓰는 얼굴이 아니라 스캐너가 훑는 대상이라 UI는 최소.
'실제 쇼핑몰 회원 페이지처럼' 보이게만 하고, 데모 취약점 성격(PII가 공개 S3에 저장)을
배너로 노출한다. 데이터는 전부 가짜(faker).
"""

INDEX_HTML = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>shop · 회원 (데모 타깃 앱)</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui,'Malgun Gothic',sans-serif; background:#f8fafc; color:#0f172a; }
  header { background:#0f172a; color:#fff; padding:14px 20px; display:flex; align-items:center; gap:10px; }
  header b { font-size:16px; }
  header .tag { margin-left:auto; font-size:12px; background:#334155; padding:2px 8px; border-radius:999px; }
  .warn { background:#fef2f2; border:1px solid #fecaca; color:#b91c1c; margin:16px 20px; padding:10px 14px;
          border-radius:8px; font-size:13px; }
  main { max-width:960px; margin:0 auto; padding:0 20px 40px; }
  h2 { font-size:14px; color:#475569; text-transform:uppercase; letter-spacing:.05em; margin:20px 0 8px; }
  .card { background:#fff; border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { text-align:left; padding:8px 12px; border-bottom:1px solid #f1f5f9; }
  th { background:#f8fafc; color:#64748b; font-weight:600; font-size:11px; }
  td.rrn { font-family:ui-monospace,monospace; color:#b91c1c; }
  form { display:flex; flex-wrap:wrap; gap:8px; background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:14px; }
  input { flex:1; min-width:140px; padding:8px 10px; border:1px solid #cbd5e1; border-radius:8px; font-size:13px; }
  button { background:#0f172a; color:#fff; border:0; border-radius:8px; padding:8px 16px; font-size:13px; cursor:pointer; }
  button:hover { background:#334155; }
  .muted { color:#94a3b8; font-size:12px; }
</style>
</head>
<body>
<header>
  <b>🛍️ shop · member</b>
  <span class="muted" style="color:#94a3b8">회원 서비스 (타깃 앱)</span>
  <span class="tag">DEMO</span>
</header>

<div class="warn">
  ⚠️ <b>데모 취약 앱</b> — 이 회원 PII는 (의도적 결함) <b>공개 S3 버킷</b>에 저장됩니다.
  표시되는 이름·주민번호·주소는 <b>전부 가짜(faker 합성)</b>입니다.
</div>

<main>
  <h2>회원 가입</h2>
  <form id="signup">
    <input name="name" placeholder="이름" required />
    <input name="email" placeholder="이메일" required />
    <input name="phone" placeholder="전화" />
    <input name="address" placeholder="주소" />
    <button type="submit">가입</button>
  </form>

  <h2>회원 목록 <span id="count" class="muted"></span></h2>
  <div class="card">
    <table>
      <thead>
        <tr><th>ID</th><th>이름</th><th>이메일</th><th>전화</th><th>주민번호(합성)</th><th>주소</th></tr>
      </thead>
      <tbody id="rows"><tr><td colspan="6" class="muted">불러오는 중…</td></tr></tbody>
    </table>
  </div>
  <p class="muted" style="margin-top:12px">
    API: <a href="/docs">/docs</a> (Swagger) · <a href="/members">/members</a> (JSON)
  </p>
</main>

<script>
async function load() {
  const res = await fetch('/members?limit=100');
  const rows = await res.json();
  document.getElementById('count').textContent = '(' + rows.length + '명)';
  document.getElementById('rows').innerHTML = rows.map(function (m) {
    return '<tr><td>' + m.id + '</td><td>' + esc(m.name) + '</td><td>' + esc(m.email) +
      '</td><td>' + esc(m.phone) + '</td><td class="rrn">' + esc(m.rrn) +
      '</td><td>' + esc(m.address) + '</td></tr>';
  }).join('') || '<tr><td colspan="6" class="muted">회원 없음</td></tr>';
}
function esc(s) { return String(s).replace(/[&<>]/g, function (c) {
  return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); }
document.getElementById('signup').addEventListener('submit', async function (e) {
  e.preventDefault();
  const f = e.target;
  await fetch('/members', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: f.name.value, email: f.email.value, phone: f.phone.value, address: f.address.value }),
  });
  f.reset();
  load();
});
load();
</script>
</body>
</html>
"""
