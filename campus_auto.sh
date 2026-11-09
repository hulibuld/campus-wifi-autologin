#!/bin/bash
# 校园网定时切换 + 自动登录（macOS）
#
#   ./campus_auto.sh --auto   定时任务用（当天已成功则跳过）
#   ./campus_auto.sh --now    立刻跑一次
#
# 用法见 README.md。下面四个常量改成你自己学校的值。
set -u

BASE="$HOME/campus-wifi"
LOG="$BASE/logs/auto.log"
STAMP="$BASE/logs/.last-success"
PY="/usr/bin/python3"

# ==== 改这里 ====
IFACE="en0"                     # 无线网卡接口名，用 networksetup -listallhardwareports 查
SSID_PRIMARY="CampusWiFi-5G"    # 首选 SSID（一般是 5GHz）
SSID_FALLBACK="CampusWiFi"      # 备选 SSID（一般是 2.4GHz）
CAMPUS_IP_PREFIX="10."          # 校园网内网 IP 前缀
# ================

WAIT_IP=25
MODE="${1:---auto}"

mkdir -p "$BASE/logs"

log()    { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }
notify() { /usr/bin/osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1; }

ip_now()       { /usr/sbin/ipconfig getifaddr "$IFACE" 2>/dev/null; }
is_campus_ip() { case "$1" in ${CAMPUS_IP_PREFIX}*) return 0 ;; *) return 1 ;; esac; }

wait_ip() {
  local i ip
  for i in $(seq 1 "$WAIT_IP"); do
    ip="$(ip_now)"
    if [ -n "$ip" ] && is_campus_ip "$ip"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

switch_ssid() {
  # 已经在校园网段就不碰网卡，避免把好连接自己断掉
  if is_campus_ip "$(ip_now)"; then
    log "已在校园网段 $(ip_now)，跳过切网"
    return 0
  fi
  local attempt
  for attempt in 1 2 3; do
    log "连接 $1（第 $attempt 次）"
    /usr/sbin/networksetup -setairportnetwork "$IFACE" "$1" >> "$LOG" 2>&1
    if wait_ip; then
      log "$1 已获得校园网 IP $(ip_now)"
      return 0
    fi
    log "$1 第 $attempt 次未拿到校园网 IP（当前: $(ip_now)）"
    if [ "$attempt" -lt 3 ]; then
      # 关卡再开，逼系统重新扫描；也把失败留下的半砖状态复位
      /usr/sbin/networksetup -setairportpower "$IFACE" off >> "$LOG" 2>&1
      sleep 3
      /usr/sbin/networksetup -setairportpower "$IFACE" on >> "$LOG" 2>&1
      sleep 4
    fi
  done
  log "$1 三次尝试均失败"
  return 1
}

do_login() {
  local out
  out=$("$PY" "$BASE/browser_login.py" 2>&1)
  log "登录结果: $out"
  printf '%s' "$out" | grep -q '"ok": true'
}

log "===== 开始（$MODE）====="
TODAY=$(date '+%Y-%m-%d')

if [ "$MODE" = "--auto" ] && [ -f "$STAMP" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$TODAY" ]; then
  log "今天已经成功过，跳过"
  exit 0
fi

for ssid in "$SSID_PRIMARY" "$SSID_FALLBACK"; do
  if switch_ssid "$ssid"; then
    if do_login; then
      log "成功：$ssid"
      echo "$TODAY" > "$STAMP"
      # 登录成功后关掉系统可能残留的登录小窗
      /usr/bin/killall captiveagent >/dev/null 2>&1 || true
      notify "校园网已就绪" "$ssid 已连接并登录"
      exit 0
    fi
    log "$ssid 切网成功但登录失败"
  fi
done

log "失败：两个 SSID 都没能登录成功"
notify "校园网切换失败" "见 $LOG"
exit 1
