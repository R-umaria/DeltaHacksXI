# signals/wifi_scan.py

import re
import time
import subprocess
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import config


@dataclass
class WifiDevice:
    bssid: str
    ssid: str
    signal_dbm: float
    last_seen_ts: float
    first_seen_ts: float


class WifiScanner:
    """
    Uses standard Linux shell command:
      iw dev wlan0 scan
    Parses BSSID/SSID/signal.
    Never crashes the app on failure; returns best-effort results.
    """
    BSS_RE = re.compile(r"^BSS\s+([0-9a-fA-F:]{17})", re.IGNORECASE)
    SIGNAL_RE = re.compile(r"signal:\s*(-?\d+(?:\.\d+)?)\s*dBm", re.IGNORECASE)
    SSID_RE = re.compile(r"^\s*SSID:\s*(.*)$")

    def __init__(self, iface: str = None):
        self.iface = iface or config.WIFI_INTERFACE
        self._known: Dict[str, WifiDevice] = {}  # bssid -> device

        self._last_scan_ts = 0.0

    def _run_scan(self) -> str:
        cmd = ["iw", "dev", self.iface, "scan"]
        # Note: scanning often requires root. Run main with sudo.
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.WIFI_SCAN_CMD_TIMEOUT_S,
        )
        if proc.returncode != 0:
            # Some systems output errors in stderr; raise to be caught upstream
            raise RuntimeError(proc.stderr.strip() or f"iw scan failed (rc={proc.returncode})")
        return proc.stdout

    def scan(self) -> Tuple[int, List[Dict]]:
        """
        Returns: (presence_score_0_100, top5_devices_list)
        top5 list entries: {bssid, ssid, rssi_dbm, age_s}
        """
        now = time.time()
        try:
            out = self._run_scan()
        except Exception:
            # On failure: decay score slightly but keep last-known devices visible
            top = self._top_devices(now, limit=5)
            score = self._compute_score(now)
            return score, top

        devices = self._parse_iw_output(out, now)
        for d in devices:
            if d.bssid in self._known:
                k = self._known[d.bssid]
                k.last_seen_ts = now
                k.ssid = d.ssid or k.ssid
                # keep strongest signal as best indicator, but use latest as well
                k.signal_dbm = max(k.signal_dbm, d.signal_dbm)
            else:
                self._known[d.bssid] = d

        self._last_scan_ts = now

        score = self._compute_score(now)
        top = self._top_devices(now, limit=5)
        return score, top

    def _parse_iw_output(self, text: str, now: float) -> List[WifiDevice]:
        devices: List[WifiDevice] = []

        cur_bssid = None
        cur_signal = None
        cur_ssid = ""

        def flush():
            nonlocal cur_bssid, cur_signal, cur_ssid
            if cur_bssid and cur_signal is not None:
                devices.append(WifiDevice(
                    bssid=cur_bssid.lower(),
                    ssid=cur_ssid.strip(),
                    signal_dbm=float(cur_signal),
                    last_seen_ts=now,
                    first_seen_ts=now,
                ))
            cur_bssid = None
            cur_signal = None
            cur_ssid = ""

        for line in text.splitlines():
            m = self.BSS_RE.match(line.strip())
            if m:
                flush()
                cur_bssid = m.group(1)
                continue

            sm = self.SIGNAL_RE.search(line)
            if sm:
                cur_signal = float(sm.group(1))
                continue

            ss = self.SSID_RE.match(line)
            if ss:
                cur_ssid = ss.group(1) or ""
                continue

        flush()
        return devices

    def _top_devices(self, now: float, limit: int = 5) -> List[Dict]:
        # Sort by signal (higher/less negative is stronger), then recent
        items = list(self._known.values())
        items.sort(key=lambda d: (d.signal_dbm, d.last_seen_ts), reverse=True)
        top = []
        for d in items[:limit]:
            top.append({
                "bssid": d.bssid,
                "ssid": d.ssid if d.ssid else "(hidden)",
                "rssi_dbm": round(d.signal_dbm, 1),
                "age_s": int(max(0, now - d.last_seen_ts)),
            })
        return top

    def _compute_score(self, now: float) -> int:
        """
        Presence score 0..100 based on:
        - count of devices stronger than -70 dBm
        - strongest RSSI
        - new devices in last 30s (first seen recently)
        """
        items = list(self._known.values())
        if not items:
            return 0

        strong = [d for d in items if d.signal_dbm >= config.WIFI_STRONG_RSSI_DBM]
        strong_count = len(strong)

        strongest = max(d.signal_dbm for d in items)  # e.g., -35 is very strong
        # Normalize strongest: (-100..-30) -> (0..70)
        strongest_norm = max(0.0, min(70.0, strongest + 100.0))

        new_recent = [d for d in items if (now - d.first_seen_ts) <= config.WIFI_NEW_DEVICE_WINDOW_S]
        new_count = len(new_recent)

        raw = (
            strong_count * config.WIFI_SCORE_STRONG_COUNT_WEIGHT +
            strongest_norm * config.WIFI_SCORE_STRONGEST_WEIGHT +
            new_count * config.WIFI_SCORE_NEW_DEVICE_WEIGHT
        )
        return int(max(0, min(100, raw)))
