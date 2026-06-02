#!/usr/bin/env python3
"""
Grupo Estrategika — Publicador Automático v4.2
GitHub Actions — Lee de Drive, despliega via Cloudflare Pages API con manifest
"""

import os, re, sys, json, requests, pickle, hashlib, mimetypes
from datetime import datetime

CF_TOKEN      = os.environ.get('CF_TOKEN', '')
CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID', '')
CF_PROJECT    = "grupoestrategika"

SITE_FILES = ['index.html', 'institucional-bancos.html', 'institucional-colegios.html',
              'como-trabajamos.html', 'globalcare.html', 'life.html', 'simulador.html',
              'simulador-educacion.html', 'simulador-jubilacion.html', 'wealth.html',
              'wealth-affluent.html']

def get_drive_service():
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    import base64, pickle as pkl

    token_b64 = os.environ.get('GOOGLE_TOKEN_B64', '')
    token_data = base64.b64decode(token_b64)
    creds = pkl.loads(token_data)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('drive', 'v3', credentials=creds)

def get_latest_report():
    service = get_drive_service()
    results = service.files().list(
        q="name contains 'daily-market-report' or name contains 'daily_market_report' or name contains 'Daily market report'",
        orderBy='modifiedTime desc',
        pageSize=3,
        fields="files(id, name, mimeType, modifiedTime)"
    ).execute()
    files = results.get('files', [])
    if not files:
        print("❌ No se encontraron reportes")
        return None, None
    for f in files:
        print(f"  - {f['name']} | {f['modifiedTime']}")
    file = files[0]
    print(f"Usando: {file['name']}")
    mime = file.get('mimeType', '')
    if 'google-apps' in mime:
        content = service.files().export(fileId=file['id'], mimeType='text/markdown').execute()
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
    print(f"Contenido: {len(text)} chars")
    return text, file['name']

def md_to_html(text):
    def clean(t):
        t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
        t = re.sub(r'\*(.+?)\*', r'<em>\1</em>', t)
        t = re.sub(r'\\([|&])', r'\1', t)  # unescape Google Docs escapes
        t = t.replace('\\+', '+').replace('\\-', '-')
        return t

    lines = text.split('\n')
    html = ''; in_table = False; in_list = False
    table_rows = []

    def flush_table():
        if not table_rows: return ''
        out = '<table>\n'
        # Find first non-empty row as header
        header_idx = 0
        for i, row in enumerate(table_rows):
            cells = [c.strip() for c in row.split('|') if c.strip()]
            # Skip separator rows and empty rows
            if cells and not all(re.match(r'^[:\-\s]+$', c) for c in cells):
                header_idx = i
                break
        for i, row in enumerate(table_rows):
            cells = [c.strip() for c in row.split('|') if c.strip()]
            if not cells: continue
            # Skip separator rows
            if all(re.match(r'^[:\-\s]+$', c) for c in cells): continue
            if i == header_idx:
                out += '<thead><tr>' + ''.join(f'<td>{clean(c)}</td>' for c in cells) + '</tr></thead>\n<tbody>\n'
            else:
                out += '<tr>' + ''.join(f'<td>{clean(c)}</td>' for c in cells) + '</tr>\n'
        out += '</tbody></table>\n'
        return out

    for line in lines:
        line = line.rstrip()
        if not line.strip():
            if in_table:
                html += flush_table(); table_rows = []; in_table = False
            if in_list: html += '</ul>\n'; in_list = False
            continue
        if line.startswith('### '):
            if in_table: html += flush_table(); table_rows = []; in_table = False
            if in_list: html += '</ul>\n'; in_list = False
            html += f'<h3>{clean(line[4:])}</h3>\n'
        elif line.startswith('## '):
            if in_table: html += flush_table(); table_rows = []; in_table = False
            if in_list: html += '</ul>\n'; in_list = False
            html += f'<h2>{clean(line[3:])}</h2>\n'
        elif line.startswith('# '):
            if in_table: html += flush_table(); table_rows = []; in_table = False
            if in_list: html += '</ul>\n'; in_list = False
            html += f'<h1>{clean(line[2:])}</h1>\n'
        elif line.startswith('|'):
            if in_list: html += '</ul>\n'; in_list = False
            in_table = True
            table_rows.append(line)
        elif line.startswith('- ') or line.startswith('* ') or line.startswith('  - '):
            if in_table: html += flush_table(); table_rows = []; in_table = False
            if not in_list: html += '<ul>\n'; in_list = True
            clean_line = line.lstrip('- *').lstrip()
            html += f'<li>{clean(clean_line)}</li>\n'
        elif re.match(r'^[-_]{3,}$', line.strip()):
            if in_table: html += flush_table(); table_rows = []; in_table = False
            if in_list: html += '</ul>\n'; in_list = False
            html += '<hr/>\n'
        else:
            if in_table: html += flush_table(); table_rows = []; in_table = False
            if in_list: html += '</ul>\n'; in_list = False
            cleaned = clean(line)
            if cleaned.strip(): html += f'<p>{cleaned}</p>\n'

    if in_table: html += flush_table()
    if in_list: html += '</ul>\n'
    return html


def build_html(report_text):
    today = datetime.now()
    dias  = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
    meses = ['enero','febrero','marzo','abril','mayo','junio','julio',
             'agosto','septiembre','octubre','noviembre','diciembre']
    fecha = f"{dias[today.weekday()]} {today.day} de {meses[today.month-1]} de {today.year}"
    body  = md_to_html(report_text)

    # Executive summary
    summary_lines = []
    for line in report_text.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('|') or line.startswith('-'):
            if summary_lines: break
            continue
        if len(line) > 30:
            summary_lines.append(re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line))
            if len(summary_lines) >= 2: break

    summary_html = ''
    if summary_lines:
        summary_html = f'''<div class="exec-summary">
  <div class="exec-label">📊 Quick Read</div>
  {chr(10).join(f'<p>{l}</p>' for l in summary_lines)}
</div>'''

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Reporte Diario de Mercados · Grupo Estrategika</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root{{--ink:#1A1814;--warm:#F7F3EE;--gold:#B89A6A;--muted:#7A7063;--border:#E2D9CE;--green:#1a6b3c;--red:#c0392b;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'DM Sans',sans-serif;background:var(--warm);color:var(--ink);}}
nav{{position:fixed;top:0;left:0;right:0;z-index:100;display:flex;justify-content:space-between;align-items:center;padding:1.2rem 4rem;background:rgba(26,24,20,0.97);backdrop-filter:blur(12px);border-bottom:1px solid rgba(255,255,255,0.06);}}
.logo{{font-family:'Cormorant Garamond',serif;font-size:1.2rem;font-weight:500;color:#fff;text-decoration:none;}}.logo span{{color:var(--gold);}}
.nav-date{{font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:rgba(255,255,255,0.4);}}
.nav-back{{font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--gold);text-decoration:none;border:1px solid rgba(184,154,106,0.3);padding:0.4rem 0.9rem;}}
.hero{{background:#1A1814;padding:7rem 4rem 3rem;}}.hero-tag{{font-size:0.68rem;letter-spacing:0.22em;text-transform:uppercase;color:var(--gold);display:block;margin-bottom:1rem;}}
.hero h1{{font-family:'Cormorant Garamond',serif;font-size:2.5rem;font-weight:300;color:#fff;margin-bottom:0.5rem;}}
.hero-sub{{font-size:0.82rem;color:rgba(255,255,255,0.4);}}
.exec-summary{{background:linear-gradient(135deg,#1A1814,#2a2420);border-left:3px solid var(--gold);padding:2rem 2.5rem;margin-bottom:2rem;}}
.exec-label{{font-size:0.68rem;letter-spacing:0.2em;text-transform:uppercase;color:var(--gold);margin-bottom:1rem;font-weight:500;}}
.exec-summary p{{font-size:0.9rem;color:rgba(255,255,255,0.78);line-height:1.75;margin-bottom:0.5rem;}}
.exec-summary strong{{color:#fff;}}
.content{{max-width:960px;margin:0 auto;padding:3rem 4rem;}}
.report{{background:#fff;border:1px solid var(--border);padding:3rem;line-height:1.85;}}
.report h1{{font-family:'Cormorant Garamond',serif;font-size:1.9rem;font-weight:400;border-bottom:2px solid var(--border);padding-bottom:0.6rem;margin:2.5rem 0 1.2rem;}}
.report h1:first-child{{margin-top:0;}}
.report h2{{font-family:'Cormorant Garamond',serif;font-size:1.25rem;font-weight:500;color:var(--gold);margin:2rem 0 0.8rem;}}
.report h3{{font-size:0.88rem;font-weight:600;margin:1.5rem 0 0.5rem;text-transform:uppercase;letter-spacing:0.08em;}}
.report p{{font-size:0.88rem;color:var(--muted);margin-bottom:0.8rem;line-height:1.8;}}
.report ul{{margin:0.5rem 0 1.2rem 1.8rem;}}.report li{{font-size:0.86rem;color:var(--muted);margin-bottom:0.4rem;}}
.report table{{width:100%;border-collapse:collapse;margin:1.2rem 0 2rem;font-size:0.83rem;border:1px solid var(--border);}}
.report thead tr td{{font-weight:600;background:var(--ink);color:#fff;padding:0.7rem 1rem;}}
.report tbody td{{padding:0.6rem 1rem;border-bottom:1px solid var(--border);}}
.report tbody tr:hover td{{background:#faf8f5;}}.report strong{{color:var(--ink);font-weight:600;}}
.positive{{color:var(--green);font-weight:600;}}.negative{{color:var(--red);font-weight:600;}}
footer{{background:#1A1814;padding:2rem 4rem;display:flex;justify-content:space-between;align-items:center;margin-top:3rem;}}
.footer-logo{{font-family:'Cormorant Garamond',serif;font-size:1rem;color:#fff;}}.footer-logo span{{color:var(--gold);}}
.footer-copy{{font-size:0.68rem;color:rgba(255,255,255,0.25);}}
.disc{{background:#1A1814;padding:1.5rem 4rem;}}.disc p{{font-size:0.7rem;color:rgba(255,255,255,0.2);line-height:1.7;max-width:800px;}}
@media(max-width:768px){{nav,footer,.disc{{padding-left:1.5rem;padding-right:1.5rem;}}.hero{{padding:6rem 1.5rem 2rem;}}.content{{padding:2rem 1.5rem;}}.report{{padding:1.5rem;}}}}
</style>
</head>
<body>
<nav>
  <a href="index.html" class="logo">Grupo <span>Estrategika</span></a>
  <span class="nav-date">{fecha}</span>
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
<div class="disc"><p>Este reporte es de carácter informativo y elaborado exclusivamente para clientes de Grupo Estrategika. No constituye asesoría de inversión.</p></div>
<footer>
  <div class="footer-logo">Grupo <span>Estrategika</span></div>
  <div class="footer-copy">© 2026 · Exclusivo para clientes · grupoestrategika.com</div>
</footer>
<script>
document.querySelectorAll('.report table').forEach(function(tbl){{
  var rows=Array.from(tbl.querySelectorAll('tr'));
  if(rows.length>1){{var thead=document.createElement('thead');var tbody=document.createElement('tbody');tbl.innerHTML='';thead.appendChild(rows[0]);rows.slice(1).forEach(function(r){{tbody.appendChild(r);}});tbl.appendChild(thead);tbl.appendChild(tbody);}}
  tbl.querySelectorAll('tbody td').forEach(function(td){{var t=td.textContent.trim();if(/^\+[\d]/.test(t))td.classList.add('positive');else if(/^-[\d]/.test(t))td.classList.add('negative');}});
}});
</script>
</body>
</html>'''

def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def deploy(files_dict):
    """Deploy via Wrangler — metodo oficial Cloudflare"""
    import subprocess, tempfile, os, shutil
    
    print("📤 Desplegando sitio completo con Wrangler...")
    print(f"Archivos del sitio: {len(files_dict)}")
    
    # Create temp folder with all files
    dist = tempfile.mkdtemp()
    try:
        for filename, content in files_dict.items():
            if isinstance(content, str):
                content = content.encode('utf-8')
            filepath = os.path.join(dist, filename)
            with open(filepath, 'wb') as f:
                f.write(content)
            print(f"  + {filename}")
        
        env = os.environ.copy()
        env['CLOUDFLARE_API_TOKEN'] = CF_TOKEN
        env['CLOUDFLARE_ACCOUNT_ID'] = CF_ACCOUNT_ID
        
        result = subprocess.run(
            ['npx', 'wrangler', 'pages', 'deploy', dist,
             f'--project-name={CF_PROJECT}',
             '--branch=main',
             '--commit-dirty=true'],
            env=env, capture_output=True, text=True, timeout=120
        )
        
        if result.returncode == 0:
            print("✅ Publicado: grupoestrategika.com")
            return True
        else:
            print(f"❌ Error Wrangler: {result.stderr[-500:]}")
            return False
    finally:
        shutil.rmtree(dist, ignore_errors=True)

if __name__ == "__main__":
    print("=" * 50)
    print("🌐 Grupo Estrategika — Publicador v4.2")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
    print("=" * 50)

    report, name = get_latest_report()
    if not report:
        sys.exit(1)

    mercados_html = build_html(report)
    print(f"HTML: {len(mercados_html)//1024}KB")

    # Build files dict — site files from repo + generated mercados.html
    files_dict = {}
    print("Desplegando sitio completo...")
    print(f"Archivos del sitio: {len(SITE_FILES) + 1}")
    
    for fname in SITE_FILES:
        site_path = os.path.join('site', fname)
        if os.path.exists(site_path):
            with open(site_path, 'rb') as f:
                files_dict[fname] = f.read()
            print(f"  + {fname}")
        else:
            print(f"  ⚠️ No encontrado: site/{fname}")

    files_dict['mercados.html'] = mercados_html.encode('utf-8')
    print(f"  + mercados.html (generado)")

    if deploy(files_dict):
        print("\n✅ COMPLETADO")
    else:
        sys.exit(1)
