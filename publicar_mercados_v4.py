#!/usr/bin/env python3
"""
Grupo Estrategika — Publicador Automático v4.1
- Busca en TODOS los drives (personal + compartidos)
- Encuentra el reporte más reciente sin importar nombre exacto
- Deploy correcto a Cloudflare
"""

import os, re, sys, json, requests, pickle
from datetime import datetime
import tempfile, zipfile

CF_TOKEN      = os.environ.get('CF_TOKEN', '')
CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID', '')
CF_PROJECT    = "grupoestrategika"

def get_drive_service():
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    import base64, pickle, io

    token_b64 = os.environ.get('GOOGLE_TOKEN_B64', '')
    token_data = base64.b64decode(token_b64)
    creds = pickle.loads(token_data)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build('drive', 'v3', credentials=creds)


def get_latest_report():
    service = get_drive_service()

    # Buscar en TODOS los drives — personal y compartidos
    # Estrategia 1: buscar por nombre
    query = (
        "name contains 'Daily market report' or "
        "name contains 'Daily_Market_Report' or "
        "name contains 'daily_market_report' or "
        "name contains 'daily-market-report'"
    )

    results = service.files().list(
        q=query,
        orderBy='modifiedTime desc',
        pageSize=3,
        fields="files(id, name, mimeType, modifiedTime)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        corpora='allDrives'
    ).execute()

    files = results.get('files', [])

    # Si no encuentra por nombre, buscar el MD más reciente de cualquier tipo
    if not files:
        print("⚠️  No encontrado por nombre — buscando archivos MD recientes...")
        results2 = service.files().list(
            q="name contains 'market' or name contains 'report'",
            orderBy='modifiedTime desc',
            pageSize=5,
            fields="files(id, name, mimeType, modifiedTime)",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            corpora='allDrives'
        ).execute()
        files = results2.get('files', [])

    if not files:
        print("❌ No se encontraron reportes en ningún Drive")
        return None, None

    # Mostrar todos los encontrados para diagnóstico
    print(f"📋 Reportes encontrados ({len(files)}):")
    for f in files:
        print(f"   - {f['name']} | {f['modifiedTime']}")

    # Tomar el más reciente
    file = files[0]
    print(f"\n✅ Usando: {file['name']}")
    mime = file.get('mimeType', '')

    if 'google-apps' in mime:
        content = service.files().export(
            fileId=file['id'], mimeType='text/plain'
        ).execute()
    else:
        from googleapiclient.http import MediaIoBaseDownload
        import io
        request = service.files().get_media(fileId=file['id'])
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        content = buf.getvalue()

    text = content.decode('utf-8') if isinstance(content, bytes) else content
    if not text or len(text.strip()) == 0:
        print("❌ Contenido vacío")
        return None, None

    print(f"✅ Contenido: {len(text):,} caracteres")
    return text, file['name']


def md_to_html(text):
    def bold(t): return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    def italic(t): return re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', t)
    def clean(t): return italic(bold(t))

    lines = text.split('\n')
    html = ''
    in_table = False
    in_list  = False

    for line in lines:
        line = line.rstrip()
        if not line.strip():
            if in_table: html += '</table>\n'; in_table = False
            if in_list:  html += '</ul>\n';    in_list  = False
            continue
        if line.startswith('### '):
            if in_table: html += '</table>\n'; in_table = False
            if in_list:  html += '</ul>\n';    in_list  = False
            html += f'<h3>{clean(line[4:])}</h3>\n'
        elif line.startswith('## '):
            if in_table: html += '</table>\n'; in_table = False
            if in_list:  html += '</ul>\n';    in_list  = False
            html += f'<h2>{clean(line[3:])}</h2>\n'
        elif line.startswith('# '):
            if in_table: html += '</table>\n'; in_table = False
            if in_list:  html += '</ul>\n';    in_list  = False
            html += f'<h1>{clean(line[2:])}</h1>\n'
        elif re.match(r'^[\s|:\-]+$', line) and '|' in line:
            continue
        elif line.startswith('|'):
            if not in_table: html += '<table>\n'; in_table = True
            cells = [c.strip() for c in line.split('|') if c.strip()]
            html += '<tr>' + ''.join(f'<td>{clean(c)}</td>' for c in cells) + '</tr>\n'
        elif line.startswith('- ') or line.startswith('* '):
            if in_table: html += '</table>\n'; in_table = False
            if not in_list: html += '<ul>\n'; in_list = True
            html += f'<li>{clean(line[2:])}</li>\n'
        elif re.match(r'^[-_]{3,}$', line.strip()):
            if in_table: html += '</table>\n'; in_table = False
            if in_list:  html += '</ul>\n';    in_list  = False
            html += '<hr/>\n'
        else:
            if in_table: html += '</table>\n'; in_table = False
            if in_list:  html += '</ul>\n';    in_list  = False
            c = clean(line)
            if c.strip(): html += f'<p>{c}</p>\n'

    if in_table: html += '</table>\n'
    if in_list:  html += '</ul>\n'
    return html


def build_html(report_text):
    today = datetime.now()
    dias  = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
    meses = ['enero','febrero','marzo','abril','mayo','junio','julio',
             'agosto','septiembre','octubre','noviembre','diciembre']
    fecha = f"{dias[today.weekday()]} {today.day} de {meses[today.month-1]} de {today.year}"
    body  = md_to_html(report_text)

    summary_lines = []
    for line in report_text.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('|') or line.startswith('-'): 
            if summary_lines: break
            continue
        if len(line) > 40:
            summary_lines.append(re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line))
            if len(summary_lines) >= 3: break

    summary_html = ''
    if summary_lines:
        summary_html = f"""<div class="exec-summary">
  <div class="exec-label">Quick Read — {fecha}</div>
  {''.join(f'<p>{l}</p>' for l in summary_lines)}
</div>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Reporte Diario de Mercados · Grupo Estrategika</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root{{--ink:#1A1814;--warm:#F7F3EE;--gold:#B89A6A;--gold-light:#D4B896;--muted:#7A7063;--border:#E2D9CE;--white:#FFFFFF;--accent:#2C4A3E;--green:#1a6b3c;--red:#c0392b;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'DM Sans',sans-serif;background:var(--warm);color:var(--ink);}}
nav{{position:fixed;top:0;left:0;right:0;z-index:100;display:flex;justify-content:space-between;align-items:center;padding:1.2rem 4rem;background:rgba(26,24,20,.97);backdrop-filter:blur(12px);border-bottom:1px solid rgba(255,255,255,.06);}}
.logo{{font-family:'Cormorant Garamond',serif;font-size:1.2rem;font-weight:500;color:#fff;text-decoration:none;letter-spacing:.04em;}}
.logo span{{color:var(--gold);}}
.nav-date{{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,.4);}}
.nav-back{{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:var(--gold);text-decoration:none;border:1px solid rgba(184,154,106,.3);padding:.4rem .9rem;}}
.hero{{background:var(--ink);padding:7rem 4rem 3rem;position:relative;overflow:hidden;}}
.hero::before{{content:'';position:absolute;right:-4rem;top:-4rem;width:20rem;height:20rem;border:1px solid rgba(184,154,106,.08);border-radius:50%;}}
.hero-tag{{font-size:.68rem;letter-spacing:.22em;text-transform:uppercase;color:var(--gold);display:block;margin-bottom:1rem;position:relative;z-index:1;}}
.hero h1{{font-family:'Cormorant Garamond',serif;font-size:2.5rem;font-weight:300;color:#fff;margin-bottom:.5rem;position:relative;z-index:1;}}
.hero-sub{{font-size:.82rem;color:rgba(255,255,255,.4);position:relative;z-index:1;}}
.exec-summary{{background:linear-gradient(135deg,var(--ink),#2a2420);border-left:3px solid var(--gold);padding:2rem 2.5rem;margin-bottom:2rem;}}
.exec-label{{font-size:.68rem;letter-spacing:.2em;text-transform:uppercase;color:var(--gold);margin-bottom:1rem;font-weight:500;}}
.exec-summary p{{font-size:.9rem;color:rgba(255,255,255,.78);line-height:1.75;margin-bottom:.5rem;}}
.exec-summary strong{{color:#fff;}}
.content{{max-width:960px;margin:0 auto;padding:3rem 4rem;}}
.report{{background:#fff;border:1px solid var(--border);padding:3rem;line-height:1.85;}}
.report h1{{font-family:'Cormorant Garamond',serif;font-size:1.9rem;font-weight:400;border-bottom:2px solid var(--border);padding-bottom:.6rem;margin:2.5rem 0 1.2rem;}}
.report h1:first-child{{margin-top:0;}}
.report h2{{font-family:'Cormorant Garamond',serif;font-size:1.25rem;font-weight:500;color:var(--gold);margin:2rem 0 .8rem;}}
.report h3{{font-size:.88rem;font-weight:600;margin:1.5rem 0 .5rem;text-transform:uppercase;letter-spacing:.08em;}}
.report p{{font-size:.88rem;color:var(--muted);margin-bottom:.8rem;line-height:1.8;}}
.report ul{{margin:.5rem 0 1.2rem 1.8rem;}}
.report li{{font-size:.86rem;color:var(--muted);margin-bottom:.4rem;line-height:1.6;}}
.report table{{width:100%;border-collapse:collapse;margin:1.2rem 0 2rem;font-size:.82rem;border:1px solid var(--border);}}
.report thead tr td{{font-weight:600;background:var(--ink);color:#fff;padding:.7rem 1rem;}}
.report tbody td{{padding:.6rem 1rem;border-bottom:1px solid var(--border);}}
.report tbody tr:hover td{{background:var(--warm);}}
.report hr{{border:none;border-top:1px solid var(--border);margin:2rem 0;}}
.report strong{{color:var(--ink);font-weight:600;}}
.positive{{color:var(--green);font-weight:600;}}
.negative{{color:var(--red);font-weight:600;}}
footer{{background:var(--ink);padding:2rem 4rem;display:flex;justify-content:space-between;align-items:center;margin-top:3rem;}}
.footer-logo{{font-family:'Cormorant Garamond',serif;font-size:1rem;color:#fff;}}
.footer-logo span{{color:var(--gold);}}
.footer-copy{{font-size:.68rem;color:rgba(255,255,255,.25);}}
.disc{{background:var(--ink);padding:1.5rem 4rem;border-top:1px solid rgba(255,255,255,.05);}}
.disc p{{font-size:.7rem;color:rgba(255,255,255,.2);line-height:1.7;max-width:800px;}}
@media(max-width:768px){{nav,footer,.disc,.hero{{padding-left:1.5rem;padding-right:1.5rem;}}.hero{{padding-top:6rem;}}.content{{padding:2rem 1.5rem;}}.report{{padding:1.5rem;}}}}
</style>
</head>
<body>
<nav>
  <a href="index.html" class="logo">Grupo <span>Estrategika</span></a>
  <span class="nav-date">{fecha.upper()}</span>
  <a href="index.html" class="nav-back">← Inicio</a>
</nav>
<div class="hero">
  <span class="hero-tag">Reporte Diario de Mercados · Exclusivo para Clientes</span>
  <h1>Daily Market Report</h1>
  <p class="hero-sub">{fecha} · Preparado por Grupo Estrategika</p>
</div>
<div class="content">
  {summary_html}
  <div class="report">{body}</div>
</div>
<div class="disc"><p>Reporte de carácter informativo elaborado exclusivamente para clientes de Grupo Estrategika. No constituye asesoría de inversión.</p></div>
<footer>
  <div class="footer-logo">Grupo <span>Estrategika</span></div>
  <div class="footer-copy">© 2026 · Exclusivo para clientes · grupoestrategika.com</div>
</footer>
<script>
document.querySelectorAll('.report table').forEach(function(tbl){{
  var rows=Array.from(tbl.querySelectorAll('tr'));
  if(rows.length>1){{
    var thead=document.createElement('thead'),tbody=document.createElement('tbody');
    tbl.innerHTML='';thead.appendChild(rows[0]);
    rows.slice(1).forEach(function(r){{tbody.appendChild(r);}});
    tbl.appendChild(thead);tbl.appendChild(tbody);
  }}
  tbl.querySelectorAll('td').forEach(function(td){{
    var t=td.textContent.trim();
    if(/^\+[\d.]/.test(t))td.classList.add('positive');
    else if(/^-[\d.]/.test(t)||/^−[\d.]/.test(t))td.classList.add('negative');
  }});
}});
</script>
</body>
</html>"""


def deploy(html):
    print("📤 Subiendo a Cloudflare Pages...")
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
        tmp_path = tmp.name
    with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('mercados.html', html)
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/pages/projects/{CF_PROJECT}/deployments"
    headers = {"Authorization": f"Bearer {CF_TOKEN}"}
    with open(tmp_path, 'rb') as f:
        r = requests.post(url, headers=headers, files={{'file': ('deployment.zip', f, 'application/zip')}})
    os.unlink(tmp_path)
    try:
        data = r.json()
        if data.get('success'):
            print("✅ Publicado: grupoestrategika.com/mercados.html")
            return True
        else:
            print(f"❌ Error: {data.get('errors')}")
            return False
    except:
        print(f"❌ HTTP {r.status_code}: {r.text[:300]}")
        return False


if __name__ == "__main__":
    print("=" * 55)
    print("🌐 Grupo Estrategika — Publicador v4.1")
    print(f"📅 {datetime.now().strftime('%A %d %B %Y — %H:%M UTC')}")
    print("=" * 55)
    report, name = get_latest_report()
    if not report: sys.exit(1)
    html = build_html(report)
    print(f"✅ HTML: {len(html)//1024}KB")
    if deploy(html):
        print("\n✅ COMPLETADO")
    else:
        sys.exit(1)
