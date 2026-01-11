# ui/webapp.py

import threading
import time
from typing import Callable, Dict, Any

from flask import Flask, request, jsonify, render_template_string

import config


DASHBOARD_HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Disaster Rover Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 16px; }
    .row { display: flex; gap: 16px; flex-wrap: wrap; }
    .card { border: 1px solid #ddd; border-radius: 8px; padding: 12px; min-width: 320px; }
    button { padding: 12px 16px; margin: 6px; font-size: 14px; }
    .danger { color: #b00020; font-weight: bold; }
    .ok { color: #0a7a0a; font-weight: bold; }
    img { border: 1px solid #ccc; border-radius: 8px; max-width: 100%; }
    .devices { font-family: monospace; white-space: pre; font-size: 12px; }
    .toggle { display: flex; align-items: center; gap: 8px; }
  </style>
</head>
<body>
  <h2>Disaster-Response Rover</h2>

  <div class="row">
    <div class="card">
      <h3>Teleop</h3>
      <div>
        <button onclick="sendCmd('forward')">Forward</button><br/>
        <button onclick="sendCmd('left')">Left</button>
        <button onclick="sendCmd('stop')">Stop</button>
        <button onclick="sendCmd('right')">Right</button><br/>
        <button onclick="sendCmd('back')">Back</button>
      </div>

      <hr/>
      <div class="toggle">
        <input type="checkbox" id="autoToggle" onchange="toggleAuto()"/>
        <label for="autoToggle">Autonomous mapping mode (stop-scan-move)</label>
      </div>

      <p><b>Status:</b> <span id="statusText">...</span></p>
      <p><b>Last command:</b> <span id="lastCmd">...</span></p>
      <p><b>Forward safety:</b> <span id="safetyText">...</span></p>
      <p><b>Pose:</b> <span id="poseText">...</span></p>
    </div>

    <div class="card">
      <h3>Map</h3>
      <img id="mapImg" src="/static/map.png" alt="map"/>
      <p style="font-size:12px;color:#555;">Auto-refreshes every 2 seconds.</p>
    </div>

    <div class="card">
      <h3>Wi-Fi presence</h3>
      <p><b>Possible human nearby score:</b> <span id="wifiScore">...</span>/100</p>
      <p style="margin-top:8px;"><b>Top 5 strongest devices:</b></p>
      <div class="devices" id="wifiDevices">...</div>
      <p style="font-size:12px;color:#555;">Uses iw scan RSSI + device activity.</p>
    </div>
  </div>

<script>
async function sendCmd(cmd) {
  const res = await fetch('/cmd/' + cmd, {method:'POST'});
  const js = await res.json();
  if (!js.ok) alert(js.error || 'Command failed');
  await refreshStatus();
}

async function toggleAuto() {
  const enabled = document.getElementById('autoToggle').checked;
  const res = await fetch('/toggle_auto', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({enabled})
  });
  const js = await res.json();
  if (!js.ok) alert(js.error || 'Toggle failed');
  await refreshStatus();
}

function formatDevices(devs) {
  if (!devs || devs.length === 0) return "(none)";
  let lines = [];
  for (const d of devs) {
    lines.push(
      `${d.rssi_dbm} dBm  age=${d.age_s}s  BSSID=${d.bssid}  SSID=${d.ssid}`
    );
  }
  return lines.join("\n");
}

async function refreshStatus() {
  const res = await fetch('/status');
  const s = await res.json();

  document.getElementById('statusText').textContent = s.status || 'n/a';
  document.getElementById('lastCmd').textContent = s.last_cmd || 'n/a';
  document.getElementById('autoToggle').checked = !!s.auto_enabled;

  document.getElementById('wifiScore').textContent = s.wifi_score ?? 'n/a';
  document.getElementById('wifiDevices').textContent = formatDevices(s.wifi_top || []);

  document.getElementById('poseText').textContent = `x=${s.pose?.x_cm?.toFixed(1)}cm, y=${s.pose?.y_cm?.toFixed(1)}cm, theta=${s.pose?.theta_deg?.toFixed(1)}°`;

  if (s.forward_blocked) {
    document.getElementById('safetyText').innerHTML = `<span class="danger">BLOCKED</span> (front min=${s.front_min_cm?.toFixed(1)} cm)`;
  } else {
    document.getElementById('safetyText').innerHTML = `<span class="ok">OK</span> (front min=${s.front_min_cm?.toFixed(1)} cm)`;
  }

  // cache-bust map
  const img = document.getElementById('mapImg');
  img.src = '/static/map.png?t=' + Date.now();
}

setInterval(refreshStatus, 2000);
refreshStatus();
</script>

</body>
</html>
"""


class WebServer:
    """
    Flask app wrapper. The rover loops run in background threads; this server stays responsive.
    """
    def __init__(self, state_provider: Callable[[], Dict[str, Any]],
                 command_handler: Callable[[str], Dict[str, Any]],
                 toggle_handler: Callable[[bool], Dict[str, Any]]):
        self.app = Flask(__name__, static_folder=config.STATIC_DIR, static_url_path="/static")
        self._state_provider = state_provider
        self._command_handler = command_handler
        self._toggle_handler = toggle_handler

        self._configure_routes()

    def _configure_routes(self):
        app = self.app

        @app.get("/")
        def index():
            return render_template_string(DASHBOARD_HTML)

        @app.post("/cmd/<cmd>")
        def cmd(cmd: str):
            out = self._command_handler(cmd)
            return jsonify(out)

        @app.post("/toggle_auto")
        def toggle_auto():
            js = request.get_json(force=True, silent=True) or {}
            enabled = bool(js.get("enabled", False))
            out = self._toggle_handler(enabled)
            return jsonify(out)

        @app.get("/status")
        def status():
            return jsonify(self._state_provider())
