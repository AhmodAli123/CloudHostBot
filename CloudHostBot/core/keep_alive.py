"""
╔══════════════════════════════════════════════════════════════╗
║               FLASK KEEP-ALIVE SERVER                        ║
║    Keeps the bot alive on Replit / Render / Railway          ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
import threading
from flask import Flask, jsonify, render_template_string
from database.db_manager import get_global_stats, is_maintenance
from utils.keyboards import fmt_size, fmt_duration, fmt_system_stats
from config.settings import FLASK_HOST, FLASK_PORT, BOT_NAME, VERSION

app = Flask(__name__)

# ══════════════════════════════════════════════════════════════
#  HTML DASHBOARD TEMPLATE
# ══════════════════════════════════════════════════════════════

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="bn">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ bot_name }} — Dashboard</title>
  <meta http-equiv="refresh" content="30">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Segoe UI', sans-serif;
      background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
      color: #eee; min-height: 100vh; padding: 30px 20px;
    }
    .container { max-width: 900px; margin: auto; }
    h1 { text-align: center; font-size: 2rem; margin-bottom: 5px; }
    h1 span { color: #7ee8fa; }
    .subtitle { text-align: center; color: #aaa; margin-bottom: 30px; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 20px; margin-bottom: 30px; }
    .card {
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.15);
      border-radius: 16px; padding: 20px; text-align: center;
      backdrop-filter: blur(10px);
      transition: transform 0.2s;
    }
    .card:hover { transform: translateY(-4px); }
    .card .icon { font-size: 2.2rem; margin-bottom: 10px; }
    .card .value { font-size: 2rem; font-weight: bold; color: #7ee8fa; }
    .card .label { color: #aaa; font-size: 0.85rem; margin-top: 4px; }
    .status-bar {
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.15);
      border-radius: 12px; padding: 16px 24px;
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 20px; flex-wrap: wrap; gap: 10px;
    }
    .badge {
      padding: 5px 14px; border-radius: 20px; font-size: 0.85rem; font-weight: bold;
    }
    .badge.online { background: #00c853; color: #000; }
    .badge.maintenance { background: #ff6d00; color: #000; }
    .resource-bar { margin: 8px 0; }
    .resource-bar .bar-label { display: flex; justify-content: space-between; font-size: 0.85rem; color: #aaa; }
    .bar-track { background: rgba(255,255,255,0.1); border-radius: 10px; height: 10px; overflow: hidden; margin-top: 4px; }
    .bar-fill { height: 100%; border-radius: 10px; transition: width 0.5s; }
    .bar-fill.cpu { background: linear-gradient(90deg, #7ee8fa, #80ff72); }
    .bar-fill.ram { background: linear-gradient(90deg, #f953c6, #b91d73); }
    .bar-fill.disk { background: linear-gradient(90deg, #f7971e, #ffd200); }
    .section { background: rgba(255,255,255,0.06); border-radius: 12px; padding: 20px; margin-bottom: 20px; }
    .section h3 { color: #7ee8fa; margin-bottom: 14px; }
    footer { text-align: center; color: #555; font-size: 0.8rem; margin-top: 30px; }
  </style>
</head>
<body>
<div class="container">
  <h1>☁️ <span>{{ bot_name }}</span></h1>
  <p class="subtitle">v{{ version }} — Telegram Cloud Hosting Platform</p>

  <div class="status-bar">
    <div>
      <strong>বট স্ট্যাটাস:</strong>
      <span class="badge {{ 'maintenance' if maintenance else 'online' }}">
        {{ '🔧 মেইনটেন্যান্স' if maintenance else '🟢 অনলাইন' }}
      </span>
    </div>
    <div style="color:#aaa; font-size:0.85rem;">⏱️ আপটাইম: <strong style="color:#7ee8fa">{{ uptime }}</strong></div>
    <div style="color:#aaa; font-size:0.85rem;">🕐 {{ current_time }}</div>
  </div>

  <div class="cards">
    <div class="card">
      <div class="icon">👥</div>
      <div class="value">{{ stats.total_users }}</div>
      <div class="label">মোট ইউজার</div>
    </div>
    <div class="card">
      <div class="icon">📁</div>
      <div class="value">{{ stats.total_files }}</div>
      <div class="label">মোট ফাইল</div>
    </div>
    <div class="card">
      <div class="icon">⚙️</div>
      <div class="value">{{ stats.running_processes }}</div>
      <div class="label">চলমান প্রসেস</div>
    </div>
    <div class="card">
      <div class="icon">⚡</div>
      <div class="value">{{ cpu }}%</div>
      <div class="label">CPU ব্যবহার</div>
    </div>
    <div class="card">
      <div class="icon">💾</div>
      <div class="value">{{ ram_pct }}%</div>
      <div class="label">RAM ব্যবহার</div>
    </div>
  </div>

  <div class="section">
    <h3>📊 রিসোর্স মনিটর</h3>
    <div class="resource-bar">
      <div class="bar-label"><span>⚡ CPU</span><span>{{ cpu }}%</span></div>
      <div class="bar-track"><div class="bar-fill cpu" style="width:{{ cpu }}%"></div></div>
    </div>
    <div class="resource-bar" style="margin-top:12px;">
      <div class="bar-label"><span>💾 RAM ({{ ram_used }} / {{ ram_total }})</span><span>{{ ram_pct }}%</span></div>
      <div class="bar-track"><div class="bar-fill ram" style="width:{{ ram_pct }}%"></div></div>
    </div>
    <div class="resource-bar" style="margin-top:12px;">
      <div class="bar-label"><span>💿 Disk ({{ disk_used }} / {{ disk_total }})</span><span>{{ disk_pct }}%</span></div>
      <div class="bar-track"><div class="bar-fill disk" style="width:{{ disk_pct }}%"></div></div>
    </div>
  </div>

  <footer>
    🤖 {{ bot_name }} | পৃষ্ঠা প্রতি ৩০ সেকেন্ডে রিফ্রেশ হয়
  </footer>
</div>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/")
def dashboard():
    import psutil
    from datetime import datetime
    stats = get_global_stats()
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return render_template_string(
        DASHBOARD_HTML,
        bot_name=BOT_NAME,
        version=VERSION,
        stats=stats,
        maintenance=is_maintenance(),
        uptime=fmt_duration(stats["uptime_seconds"]),
        current_time=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        cpu=round(cpu, 1),
        ram_pct=round(ram.percent, 1),
        ram_used=fmt_size(ram.used),
        ram_total=fmt_size(ram.total),
        disk_pct=round(disk.percent, 1),
        disk_used=fmt_size(disk.used),
        disk_total=fmt_size(disk.total),
    )


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "bot": BOT_NAME,
        "version": VERSION,
        "maintenance": is_maintenance(),
        "timestamp": time.time()
    })


@app.route("/stats")
def api_stats():
    import psutil
    stats = get_global_stats()
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return jsonify({
        "users": stats["total_users"],
        "files": stats["total_files"],
        "processes": stats["running_processes"],
        "uptime": stats["uptime_seconds"],
        "cpu_percent": cpu,
        "ram_percent": ram.percent,
        "disk_percent": disk.percent,
    })


# ══════════════════════════════════════════════════════════════
#  SERVER RUNNER
# ══════════════════════════════════════════════════════════════

def run_flask():
    """Run Flask in a background thread."""
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)


def start_keep_alive():
    """Start the Flask keep-alive server in background."""
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    print(f"🌐 Keep-alive server started on port {FLASK_PORT}")
