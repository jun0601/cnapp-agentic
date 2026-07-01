"""shop 데모 포털 UI(§7 '최소 스킨').

타깃 앱은 마이크로서비스 3개(product/order/member)지만 로컬에서 실제로 도는 건 member뿐이라,
member가 '데모 포털'로서 대표 페이지(/)와 각 서비스 소개 페이지를 서빙한다.
※ 실제 배포(EKS)에선 각 서비스가 분리되고, 이 포털은 로컬 확인/시연 편의용.
모든 데이터는 가짜(faker). 각 서비스의 '의도적 결함'을 화면에 노출해 데모 서사를 돕는다.
"""

# 타깃 앱 파비콘 — 쇼핑백(밝은 색). 관제 앱(방패)과 시각적으로 구분.
FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <path d="M6.5 11 h19 l-1.6 16.2 a2.4 2.4 0 0 1-2.4 2.2 H10.5 a2.4 2.4 0 0 1-2.4-2.2 Z" fill="#f59e0b"/>
  <path d="M6.5 11 h19 l-0.4 4 H6.9 Z" fill="#fbbf24"/>
  <path d="M11 12 V9 a5 5 0 0 1 10 0 v3" fill="none" stroke="#b45309" stroke-width="2.2" stroke-linecap="round"/>
</svg>"""

_CSS = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui,'Malgun Gothic',sans-serif; background:#f8fafc; color:#0f172a; }
  a { color: inherit; text-decoration: none; }
  header { background:#0f172a; color:#fff; padding:0 20px; display:flex; align-items:center; gap:4px; height:52px; }
  header .brand { display:flex; align-items:center; gap:8px; font-weight:700; margin-right:12px; }
  header nav { display:flex; gap:2px; }
  header nav a { padding:8px 14px; border-radius:8px; font-size:14px; color:#cbd5e1; }
  header nav a:hover { background:#1e293b; color:#fff; }
  header nav a.active { background:#334155; color:#fff; }
  header .tag { margin-left:auto; font-size:11px; background:#b91c1c; padding:3px 10px; border-radius:999px; }
  .warn { background:#fef2f2; border:1px solid #fecaca; color:#b91c1c; margin:16px 20px 0; padding:10px 14px; border-radius:8px; font-size:13px; }
  main { max-width:1000px; margin:0 auto; padding:20px; }
  h1 { font-size:22px; margin:0 0 6px; }
  h2 { font-size:13px; color:#64748b; text-transform:uppercase; letter-spacing:.05em; margin:24px 0 10px; }
  .lead { color:#475569; font-size:14px; line-height:1.6; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }
  .card { background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:18px; display:flex; flex-direction:column; gap:8px; }
  .card .ico { font-size:26px; }
  .card h3 { margin:0; font-size:16px; }
  .card p { margin:0; color:#64748b; font-size:13px; line-height:1.5; }
  .chip { display:inline-block; font-size:11px; padding:2px 8px; border-radius:999px; background:#f1f5f9; color:#475569; margin-right:4px; margin-top:4px; }
  .chip.bad { background:#fef2f2; color:#b91c1c; }
  .card .go { margin-top:auto; font-size:13px; font-weight:600; color:#2563eb; }
  .card.live { border-color:#bfdbfe; }
  table { width:100%; border-collapse:collapse; font-size:13px; background:#fff; }
  .tablewrap { border:1px solid #e2e8f0; border-radius:14px; overflow:hidden; }
  th,td { text-align:left; padding:9px 12px; border-bottom:1px solid #f1f5f9; }
  th { background:#f8fafc; color:#64748b; font-weight:600; font-size:11px; }
  td.rrn { font-family:ui-monospace,monospace; color:#b91c1c; }
  form { display:flex; flex-wrap:wrap; gap:8px; background:#fff; border:1px solid #e2e8f0; border-radius:14px; padding:14px; }
  input { flex:1; min-width:140px; padding:9px 11px; border:1px solid #cbd5e1; border-radius:8px; font-size:13px; }
  button { background:#0f172a; color:#fff; border:0; border-radius:8px; padding:9px 18px; font-size:13px; cursor:pointer; }
  button:hover { background:#334155; }
  .muted { color:#94a3b8; font-size:12px; }
  .deftable td:first-child { font-family:ui-monospace,monospace; color:#b91c1c; white-space:nowrap; }
"""


def _page(title, active, body):
    """공통 셸(헤더+네비+파비콘)로 감싼 전체 HTML."""
    nav_items = [("/", "홈"), ("/product", "상품"), ("/order", "주문"), ("/members", "회원")]
    nav = "".join(
        '<a href="{href}" class="{cls}">{label}</a>'.format(
            href=h, label=l, cls="active" if h == active else ""
        )
        for h, l in nav_items
    )
    return """<!doctype html><html lang="ko"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<link rel="icon" type="image/svg+xml" href="/favicon.svg"/>
<title>{title}</title><style>{css}</style></head><body>
<header>
  <span class="brand">🛍️ shop</span>
  <nav>{nav}</nav>
  <span class="tag">취약 데모 앱</span>
</header>
{body}
</body></html>""".format(title=title, css=_CSS, nav=nav, body=body)


def portal_html():
    body = """
<div class="warn">⚠️ <b>CNAPP 데모용 취약 타깃 앱</b> — 일부러 보안 결함을 심어둔 쇼핑몰입니다. 스캐너가 이 앱을 훑어 findings를 만들고, 그게 <b>관제 앱(console)</b>에 뜹니다. 모든 데이터·시크릿은 <b>가짜</b>입니다.</div>
<main>
  <h1>shop 데모 포털</h1>
  <p class="lead">이 쇼핑몰은 <b>마이크로서비스 3개</b>로 구성됩니다. 각 서비스에 서로 다른 <b>의도적 결함</b>을 심어, CNAPP의 6기둥(취약점·KSPM·CIEM·CSPM·데이터)이 골고루 발화하도록 했습니다. 아래에서 각 서비스로 들어가 보세요. (로컬에선 member만 실제 구동, product/order는 소개 페이지)</p>
  <h2>서비스</h2>
  <div class="grid">
    <a href="/product" class="card">
      <span class="ico">📦</span><h3>product · 상품</h3>
      <p>상품 카탈로그(retail-store fork). 골든 시나리오의 <b>진입점</b>.</p>
      <div><span class="chip bad">f1 KEV 취약 이미지</span><span class="chip bad">f2 privileged 파드</span></div>
      <span class="go">상세 보기 →</span>
    </a>
    <a href="/order" class="card">
      <span class="ico">🧾</span><h3>order · 주문</h3>
      <p>주문 서비스(retail-store fork). <b>측면이동 + 크로스클라우드 자격증명 탈취</b> 지점.</p>
      <div><span class="chip bad">f5 평문 Azure SP</span><span class="chip bad">f4 과도 IRSA</span></div>
      <span class="go">상세 보기 →</span>
    </a>
    <a href="/members" class="card live">
      <span class="ico">👤</span><h3>member · 회원</h3>
      <p>회원 서비스(신규·Python). <b>AWS 데이터 탈취 종착지</b>. 지금 실제로 동작합니다.</p>
      <div><span class="chip bad">f6 공개 S3</span><span class="chip bad">f7 PII 노출</span><span class="chip">LIVE</span></div>
      <span class="go">회원 관리 열기 →</span>
    </a>
  </div>
  <h2>공격 경로(골든 시나리오)</h2>
  <div class="card"><p class="lead">📦 product 취약 이미지로 침투 → 🧾 order 과도 권한으로 측면이동 + 평문 Azure 자격증명 탈취 → 👤 member 공개 S3에서 회원 PII 탈취 → ☁️ 탈취 자격증명으로 <b>Azure Entra ID 신원 장악</b>. 이 경로 시각화는 관제 앱의 attack-path 화면에서 봅니다.</p></div>
</main>"""
    return _page("shop · 데모 포털", "/", body)


def _service_page(active, icon, title, subtitle, desc, defects):
    rows = "".join(
        "<tr><td>{c}</td><td>{t}</td><td>{loc}</td></tr>".format(c=c, t=t, loc=loc) for c, t, loc in defects
    )
    body = """
<main>
  <h1>{icon} {title}</h1>
  <p class="lead">{subtitle}</p>
  <p class="muted">{desc}</p>
  <h2>심어진 결함</h2>
  <div class="tablewrap"><table class="deftable">
    <thead><tr><th>결함</th><th>내용</th><th>위치</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <p class="muted" style="margin-top:14px">이 서비스는 retail-store-sample-app fork라 로컬 단독 실행 대신 EKS 배포 시 구동됩니다. 여기선 결함 구성을 소개합니다.</p>
</main>""".format(icon=icon, title=title, subtitle=subtitle, desc=desc, rows=rows)
    return _page("shop · " + title, active, body)


def product_html():
    return _service_page(
        "/product", "📦", "product · 상품",
        "상품 카탈로그 서비스. 골든 attack-path의 진입점(노드 n1).",
        "retail-store catalog fork. 기능은 그대로, 이미지·파드에만 결함을 심음.",
        [
            ("f1 · INTERNAL-VULN-KEV-001", "KEV 등재 CVE가 있는 오래된 베이스 이미지", "product/Dockerfile"),
            ("f2 · INTERNAL-KSPM-PRIVILEGED-001", "privileged + hostPath(노드 루트 마운트)", "product/k8s/deployment.yaml"),
        ],
    )


def order_html():
    return _service_page(
        "/order", "🧾", "order · 주문",
        "주문 서비스. 측면이동 + 크로스클라우드 자격증명 탈취 지점.",
        "retail-store orders fork. product·member를 참조. 파드 env·IAM에 결함.",
        [
            ("f5 · INTERNAL-SECRET-PLAINTEXT-001", "Azure SP 자격증명을 파드 env에 평문 노출(가짜값)", "order/k8s/deployment.yaml"),
            ("f4 · INTERNAL-IAM-OVERPRIV-001", "order IRSA에 s3:* 과도권한", "infra/target"),
        ],
    )


# 회원 관리 페이지(실제 동작). /api/members를 호출.
def members_html():
    body = """
<div class="warn">⚠️ 이 회원 PII는 (의도적 결함 f6·f7) <b>공개 S3 버킷</b>에 저장됩니다. 표시되는 이름·주민번호·주소는 <b>전부 가짜(faker)</b>.</div>
<main>
  <h1>👤 member · 회원 관리</h1>
  <p class="lead">회원 가입/조회. 데이터는 가짜 합성이며, 원본은 member 기동 시 S3에 적재됩니다(Macie 탐지 대상).</p>
  <h2>회원 가입</h2>
  <form id="signup">
    <input name="name" placeholder="이름" required/>
    <input name="email" placeholder="이메일" required/>
    <input name="phone" placeholder="전화"/>
    <input name="address" placeholder="주소"/>
    <button type="submit">가입</button>
  </form>
  <h2>회원 목록 <span id="count" class="muted"></span></h2>
  <div class="tablewrap"><table>
    <thead><tr><th>ID</th><th>이름</th><th>이메일</th><th>전화</th><th>주민번호(합성)</th><th>주소</th></tr></thead>
    <tbody id="rows"><tr><td colspan="6" class="muted">불러오는 중…</td></tr></tbody>
  </table></div>
  <p class="muted" style="margin-top:12px">API: <a href="/docs">/docs</a> · <a href="/api/members">/api/members</a> (JSON)</p>
</main>
<script>
function esc(s){return String(s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
async function load(){
  const r=await fetch('/api/members?limit=100'); const rows=await r.json();
  document.getElementById('count').textContent='('+rows.length+'명)';
  document.getElementById('rows').innerHTML=rows.map(function(m){
    return '<tr><td>'+m.id+'</td><td>'+esc(m.name)+'</td><td>'+esc(m.email)+'</td><td>'+esc(m.phone)+
      '</td><td class="rrn">'+esc(m.rrn)+'</td><td>'+esc(m.address)+'</td></tr>';}).join('')
    || '<tr><td colspan="6" class="muted">회원 없음</td></tr>';
}
document.getElementById('signup').addEventListener('submit',async function(e){
  e.preventDefault(); const f=e.target;
  await fetch('/api/members',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:f.name.value,email:f.email.value,phone:f.phone.value,address:f.address.value})});
  f.reset(); load();
});
load();
</script>"""
    return _page("shop · 회원 관리", "/members", body)
