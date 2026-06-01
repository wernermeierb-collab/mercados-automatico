#!/usr/bin/env python3
"""
Grupo Estrategika — Publicador v4.2
- Lee reporte de Google Drive
- Genera mercados.html
- Despliega TODOS los archivos del sitio (carpeta site/) + mercados.html via Wrangler
"""

import os, re, sys, json, pickle, shutil, subprocess
from datetime import datetime

CF_TOKEN      = os.environ.get('CF_TOKEN', '')
CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID', '')
CF_PROJECT    = "grupoestrategika"
SITE_DIR      = "site"    # carpeta con todos los HTML del sitio
DIST_DIR      = "dist"    # carpeta de deploy

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
    query = (
        "name contains 'Daily market report' or "
        "name contains 'Daily_Market_Report' or "
        "name contains 'daily_market_report' or "
        "name contains 'daily-market-report'"
    )
    results = service.files().list(
        q=query, orderBy='modifiedTime desc', pageSize=3,
        fields="files(id, name, mimeType, modifiedTime)",
        includeItemsFromAllDrives=True, supportsAllDrives=True, corpora='allDrives'
    ).execute()
    files = results.get('files', [])
    if not files:
        print("❌ No se encontraron reportes")
        return None, None
    file = files[0]
    print(f"✅ Reporte: {file['name']} | {file['modifiedTime']}")
    mime = file.get('mimeType', '')
    if 'google-apps' in mime:
        content = service.files().export(fileId=file['id'], mimeType='text/plain').execute()
    else:
        from googleapiclient.http import MediaIoBaseDownload
        import io
        req = service.files().get_media(fileId=file['id'])
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, req)
        done = False
        while not done: _, done = dl.next_chunk()
        content = buf.getvalue()
    text = content.decode('utf-8') if isinstance(content, bytes) else content
    if not text.strip():
        print("❌ Contenido vacío")
        return None, None
    print(f"✅ {len(text):,} chars")
    return text, file['name']


def md_to_html(text):
    def bold(t): return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    def clean(t): return bold(t)
    lines = text.split("\n"); html = ""; in_table = False; in_list = False
    for line in lines:
        line = line.rstrip()
        if not line.strip():
            if in_table: html += "</table>\n"; in_table = False
            if in_list:  html += "</ul>\n";    in_list  = False
            continue
        if line.startswith("### "): html += f"<h3>{clean(line[4:])}</h3>\n"
        elif line.startswith("## "): html += f"<h2>{clean(line[3:])}</h2>\n"
        elif line.startswith("# "):  html += f"<h1>{clean(line[2:])}</h1>\n"
        elif re.match(r"^[\s|:\-]+$", line) and "|" in line: pass
        elif line.startswith("|"):
            if not in_table: html += "<table>\n"; in_table = True
            cells = [c.strip() for c in line.split("|") if c.strip()]
            html += "<tr>" + "".join(f"<td>{clean(c)}</td>" for c in cells) + "</tr>\n"
        elif line.startswith("- ") or line.startswith("* "):
            if in_table: html += "</table>\n"; in_table = False
            if not in_list: html += "<ul>\n"; in_list = True
            html += f"<li>{clean(line[2:])}</li>\n"
        elif re.match(r"^[-_]{3,}$", line.strip()):
            if in_table: html += "</table>\n"; in_table = False
            if in_list:  html += "</ul>\n";    in_list  = False
            html += "<hr/>\n"
        else:
            if in_table: html += "</table>\n"; in_table = False
            if in_list:  html += "</ul>\n";    in_list  = False
            c = clean(line)
            if c.strip(): html += f"<p>{c}</p>\n"
    if in_table: html += "</table>\n"
    if in_list:  html += "</ul>\n"
    return html


def build_html(report_text):
    today = datetime.now()
    dias  = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    meses = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
    fecha = f"{dias[today.weekday()]} {today.day} de {meses[today.month-1]} de {today.year}"
    body  = md_to_html(report_text)
    return f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Reporte Diario · Grupo Estrategika</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root{{--ink:#1A1814;--warm:#F7F3EE;--gold:#B89A6A;--muted:#7A7063;--border:#E2D9CE;--white:#FFFFFF;--accent:#2C4A3E;--green:#1a6b3c;--red:#c0392b;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:"DM Sans",sans-serif;background:var(--warm);color:var(--ink);}}
nav{{position:fixed;top:0;left:0;right:0;z-index:100;display:flex;justify-content:space-between;align-items:center;padding:1.2rem 4rem;background:rgba(26,24,20,.97);backdrop-filter:blur(12px);border-bottom:1px solid rgba(255,255,255,.06);}}
.logo{{font-family:"Cormorant Garamond",serif;font-size:1.2rem;font-weight:500;color:#fff;text-decoration:none;letter-spacing:.04em;}}
.logo span{{color:var(--gold);}}
.nav-date{{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,.4);}}
.nav-back{{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:var(--gold);text-decoration:none;border:1px solid rgba(184,154,106,.3);padding:.4rem .9rem;}}
.hero{{background:var(--ink);padding:7rem 4rem 3rem;position:relative;overflow:hidden;}}
.hero::before{{content:"";position:absolute;right:-4rem;top:-4rem;width:20rem;height:20rem;border:1px solid rgba(184,154,106,.08);border-radius:50%;}}
.hero-tag{{font-size:.68rem;letter-spacing:.22em;text-transform:uppercase;color:var(--gold);display:block;margin-bottom:1rem;}}
.hero h1{{font-family:"Cormorant Garamond",serif;font-size:2.5rem;font-weight:300;color:#fff;margin-bottom:.5rem;}}
.hero-sub{{font-size:.82rem;color:rgba(255,255,255,.4);}}
.content{{max-width:960px;margin:0 auto;padding:3rem 4rem;}}
.report{{background:#fff;border:1px solid var(--border);padding:3rem;line-height:1.85;}}
.report h1{{font-family:"Cormorant Garamond",serif;font-size:1.9rem;font-weight:400;border-bottom:2px solid var(--border);padding-bottom:.6rem;margin:2.5rem 0 1.2rem;}}
.report h1:first-child{{margin-top:0;}}
.report h2{{font-family:"Cormorant Garamond",serif;font-size:1.25rem;font-weight:500;color:var(--gold);margin:2rem 0 .8rem;}}
.report h3{{font-size:.88rem;font-weight:600;margin:1.5rem 0 .5rem;text-transform:uppercase;letter-spacing:.08em;}}
.report p{{font-size:.88rem;color:var(--muted);margin-bottom:.8rem;line-height:1.8;}}
.report ul{{margin:.5rem 0 1.2rem 1.8rem;}}
.report li{{font-size:.86rem;color:var(--muted);margin-bottom:.4rem;}}
.report table{{width:100%;border-collapse:collapse;margin:1.2rem 0 2rem;font-size:.82rem;border:1px solid var(--border);}}
.report thead td{{font-weight:600;background:var(--ink);color:#fff;padding:.7rem 1rem;}}
.report tbody td{{padding:.6rem 1rem;border-bottom:1px solid var(--border);}}
.report tbody tr:hover td{{background:var(--warm);}}
.report hr{{border:none;border-top:1px solid var(--border);margin:2rem 0;}}
.positive{{color:var(--green);font-weight:600;}}
.negative{{color:var(--red);font-weight:600;}}
footer{{background:var(--ink);padding:2rem 4rem;display:flex;justify-content:space-between;align-items:center;margin-top:3rem;}}
.footer-logo{{font-family:"Cormorant Garamond",serif;font-size:1rem;color:#fff;}}
.footer-logo span{{color:var(--gold);}}
.footer-copy{{font-size:.68rem;color:rgba(255,255,255,.25);}}
.disc{{background:var(--ink);padding:1.5rem 4rem;border-top:1px solid rgba(255,255,255,.05);}}
.disc p{{font-size:.7rem;color:rgba(255,255,255,.2);line-height:1.7;max-width:800px;}}
@media(max-width:768px){{nav,footer,.disc,.hero{{padding-left:1.5rem;padding-right:1.5rem;}}.hero{{padding-top:6rem;}}.content{{padding:2rem 1.5rem;}}.report{{padding:1.5rem;}}}}
</style></head>
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
<div class="content"><div class="report">{body}</div></div>
<div class="disc"><p>Reporte de carácter informativo elaborado exclusivamente para clientes de Grupo Estrategika. No constituye asesoría de inversión.</p></div>
<footer>
  <div class="footer-logo">Grupo <span>Estrategika</span></div>
  <div class="footer-copy">© 2026 · grupoestrategika.com</div>
</footer>
<script>
document.querySelectorAll(".report table").forEach(function(t){{
  var rows=Array.from(t.querySelectorAll("tr"));
  if(rows.length>1){{
    var thead=document.createElement("thead"),tbody=document.createElement("tbody");
    t.innerHTML="";thead.appendChild(rows[0]);rows.slice(1).forEach(function(r){{tbody.appendChild(r);}});
    t.appendChild(thead);t.appendChild(tbody);
  }}
  t.querySelectorAll("td").forEach(function(td){{
    var v=td.textContent.trim();
    if(/^\+[\d.]/.test(v))td.classList.add("positive");
    else if(/^-[\d.]/.test(v))td.classList.add("negative");
  }});
}});
</script>
</body></html>"""


def deploy(mercados_html):
    """Deploy: copia site/ a dist/, agrega mercados.html, despliega con Wrangler"""
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    shutil.copytree(SITE_DIR, DIST_DIR)
    with open(os.path.join(DIST_DIR, 'mercados.html'), 'w', encoding='utf-8') as f:
        f.write(mercados_html)
    files = os.listdir(DIST_DIR)
    print(f"✅ dist/ tiene {len(files)} archivos: {files}")
    env = os.environ.copy()
    result = subprocess.run(
        ['npx', 'wrangler', 'pages', 'deploy', DIST_DIR,
         f'--project-name={CF_PROJECT}', '--branch=main', '--commit-dirty=true'],
        env=env, capture_output=True, text=True
    )
    if result.returncode == 0:
        print("✅ Publicado en grupoestrategika.com")
        return True
    else:
        print(f"❌ Error Wrangler:\n{result.stderr[-800:]}")
        return False


if __name__ == "__main__":
    print("="*55)
    print("🌐 Grupo Estrategika — Publicador v4.2")
    print(f"📅 {datetime.now().strftime('%A %d %B %Y — %H:%M UTC')}")
    print("="*55)
    report, name = get_latest_report()
    if not report: sys.exit(1)
    html = build_html(report)
    print(f"✅ HTML: {len(html)//1024}KB")
    if deploy(html):
        print("\n✅ COMPLETADO — sitio completo + mercados.html publicados")
    else:
        sys.exit(1)
