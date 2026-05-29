#!/usr/bin/env python3
"""
Grupo Estrategika — Publicador Automático v4
Corre en GitHub Actions — sin iMac, sin internet del teléfono
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
    import base64

    token_b64 = os.environ.get('GOOGLE_TOKEN_B64', '')
    token_data = base64.b64decode(token_b64)
    
    import pickle, io
    creds = pickle.loads(token_data)
    
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    
    return build('drive', 'v3', credentials=creds)

def get_latest_report():
    service = get_drive_service()
    query = (
        "name contains 'Daily market report' or "
        "name contains 'Daily_Market_Report' or "
        "name contains 'daily_market_report' or "
        "name contains 'daily-market-report'"
    )
    results = service.files().list(
        q=query,
        orderBy='modifiedTime desc',
        pageSize=1,
        fields="files(id, name, mimeType, modifiedTime)"
    ).execute()

    files = results.get('files', [])
    if not files:
        print("❌ No se encontraron reportes en Google Drive")
        return None, None

    file = files[0]
    print(f"✅ Reporte encontrado: {file['name']}")
    mime = file.get('mimeType', '')

    if 'google-apps' in mime:
        content = service.files().export(fileId=file['id'], mimeType='text/plain').execute()
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

    print(f"✅ Contenido OK: {len(text)} caracteres")
    return text, file['name']

def build_html(report_text):
    today = datetime.now()
    dias  = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
    meses = ['enero','febrero','marzo','abril','mayo','junio','julio',
             'agosto','septiembre','octubre','noviembre','diciembre']
    fecha = f"{dias[today.weekday()]} {today.day} de {meses[today.month-1]} de {today.year}"

    lines = report_text.split('\n')
    body  = ''
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith('# '):
            body += f'<h1>{line[2:]}</h1>\n'
        elif line.startswith('## '):
            body += f'<h2>{line[3:]}</h2>\n'
        elif line.startswith('### '):
            body += f'<h3>{line[4:]}</h3>\n'
        elif line.startswith('|') and not re.match(r'^[\s|:-]+$', line):
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if cells:
                body += f'<tr>{"".join(f"<td>{c}</td>" for c in cells)}</tr>\n'
        elif line.startswith('- ') or line.startswith('* '):
            body += f'<li>{line[2:]}</li>\n'
        else:
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            body += f'<p>{line}</p>\n'

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Reporte Diario de Mercados · Grupo Estrategika</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root{{--ink:#1A1814;--warm:#F7F3EE;--white:#FFFFFF;--gold:#B89A6A;--muted:#7A7063;--border:#E2D9CE;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'DM Sans',sans-serif;background:var(--warm);color:var(--ink);}}
nav{{position:fixed;top:0;left:0;right:0;z-index:100;display:flex;justify-content:space-between;align-items:center;padding:1.2rem 4rem;background:rgba(26,24,20,0.97);backdrop-filter:blur(12px);border-bottom:1px solid rgba(255,255,255,0.06);}}
.logo{{font-family:'Cormorant Garamond',serif;font-size:1.2rem;font-weight:500;color:#fff;text-decoration:none;}}
.logo span{{color:var(--gold);}}
.nav-date{{font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:rgba(255,255,255,0.4);}}
.nav-back{{font-size:0.72rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--gold);text-decoration:none;border:1px solid rgba(184,154,106,0.3);padding:0.4rem 0.9rem;}}
.hero{{background:#1A1814;padding:7rem 4rem 3rem;}}
.hero-tag{{font-size:0.68rem;letter-spacing:0.22em;text-transform:uppercase;color:var(--gold);display:block;margin-bottom:1rem;}}
.hero h1{{font-family:'Cormorant Garamond',serif;font-size:2.5rem;font-weight:300;color:#fff;margin-bottom:0.5rem;}}
.hero-sub{{font-size:0.82rem;color:rgba(255,255,255,0.4);}}
.content{{max-width:900px;margin:0 auto;padding:3rem 4rem;}}
.report{{background:#fff;border:1px solid var(--border);padding:3rem;line-height:1.8;}}
.report h1{{font-family:'Cormorant Garamond',serif;font-size:1.8rem;font-weight:400;border-bottom:1px solid var(--border);padding-bottom:0.5rem;margin:2rem 0 1rem;}}
.report h2{{font-family:'Cormorant Garamond',serif;font-size:1.3rem;font-weight:400;color:var(--gold);margin:1.5rem 0 0.5rem;}}
.report h3{{font-size:1rem;font-weight:500;margin:1.2rem 0 0.4rem;}}
.report p{{font-size:0.87rem;color:var(--muted);margin-bottom:0.6rem;}}
.report li{{font-size:0.85rem;color:var(--muted);margin-bottom:0.3rem;padding-left:1.2rem;}}
.report table{{width:100%;border-collapse:collapse;margin:1rem 0;font-size:0.82rem;}}
.report td{{padding:0.5rem 0.8rem;border-bottom:1px solid var(--border);}}
.report tr:hover td{{background:var(--warm);}}
footer{{background:#1A1814;padding:2rem 4rem;display:flex;justify-content:space-between;align-items:center;margin-top:3rem;}}
.footer-logo{{font-family:'Cormorant Garamond',serif;font-size:1rem;color:#fff;}}
.footer-logo span{{color:var(--gold);}}
.footer-copy{{font-size:0.68rem;color:rgba(255,255,255,0.25);}}
.disc{{background:#1A1814;padding:1.5rem 4rem;}}
.disc p{{font-size:0.7rem;color:rgba(255,255,255,0.2);line-height:1.7;max-width:800px;}}
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
  <div class="report">{body}</div>
</div>
<div class="disc"><p>Este reporte es de carácter informativo y elaborado exclusivamente para clientes de Grupo Estrategika. No constituye asesoría de inversión.</p></div>
<footer>
  <div class="footer-logo">Grupo <span>Estrategika</span></div>
  <div class="footer-copy">© 2026 · Exclusivo para clientes · grupoestrategika.com</div>
</footer>
</body>
</html>'''

def deploy(html):
    print("📤 Subiendo a Cloudflare con Wrangler...")
    import subprocess, os

    dist = '/tmp/dist'
    os.makedirs(dist, exist_ok=True)
    with open(f'{dist}/mercados.html', 'w', encoding='utf-8') as f:
        f.write(html)

    env = os.environ.copy()
    env['CLOUDFLARE_API_TOKEN'] = CF_TOKEN
    env['CLOUDFLARE_ACCOUNT_ID'] = CF_ACCOUNT_ID

    result = subprocess.run(
        ['npx', 'wrangler', 'pages', 'deploy', dist,
         f'--project-name={CF_PROJECT}', '--commit-dirty=true', '--branch=main'],
        env=env, capture_output=True, text=True
    )

    if result.returncode == 0:
        print("✅ Publicado: grupoestrategika.com/mercados.html")
        return True
    else:
        print(f"❌ Error: {result.stderr}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("🌐 Grupo Estrategika — Publicador v4 (GitHub Actions)")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)
    report, name = get_latest_report()
    if not report:
        sys.exit(1)
    html = build_html(report)
    print(f"✅ HTML generado: {len(html)//1024}KB")
    if deploy(html):
        print("\n✅ COMPLETADO")
    else:
        sys.exit(1)
