#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 macOS 自带的 AppleScript 驱动 Chrome，在校园网认证页自动填账号密码并点登录。

前提：
  1. Chrome 菜单「视图 → 开发者 → 允许 Apple 事件中的 JavaScript」已开启
  2. 账号密码按 README 存进 macOS 钥匙串
  3. 当前已经在校园网内网（切网由 campus_auto.sh 负责）

成功判据：提交之后外网从不通变成通。不靠页面跳不跳转 ——
认证页的登录请求走 AJAX，提交后页面通常停在原地，跳不跳和成不成没关系。

输出一行 JSON：{"ok": true/false, ...}
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

APP = "Google Chrome"

# ==== 改这里 ====
PORTAL_URL = "http://10.0.0.1/"       # 认证页地址，末尾带斜杠
PORTAL_HOST = "10.0.0.1"              # 同上，用来识别门户标签
USERNAME = "YOUR_STUDENT_ID"
KEYCHAIN_SERVICE = "campus-portal"
CAMPUS_IP_PREFIX = "10."              # 校园网内网 IP 前缀
PROBE_URL = "http://connect.rom.miui.com/generate_204"
# ================


def osa(script, timeout=40):
    try:
        p = subprocess.run(["/usr/bin/osascript", "-"], input=script, text=True,
                           capture_output=True, timeout=timeout)
        return (p.stdout or "").strip(), (p.stderr or "").strip(), p.returncode
    except subprocess.TimeoutExpired:
        return "", "osascript timeout", 124


def keychain_password():
    try:
        return subprocess.check_output(
            ["/usr/bin/security", "find-generic-password",
             "-s", KEYCHAIN_SERVICE, "-w"],
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def local_ip():
    try:
        return subprocess.check_output(
            ["/usr/sbin/ipconfig", "getifaddr", "en0"], text=True).strip()
    except Exception:
        return ""


def list_tabs():
    script = (
        'tell application "' + APP + '"\n'
        '  set out to ""\n'
        '  repeat with wi from 1 to (count of windows)\n'
        '    repeat with ti from 1 to (count of tabs of window wi)\n'
        '      set out to out & wi & "|" & ti & "|" & (URL of tab ti of window wi) & "|" & (title of tab ti of window wi) & linefeed\n'
        '    end repeat\n'
        '  end repeat\n'
        '  return out\n'
        'end tell\n'
    )
    out, err, rc = osa(script, timeout=25)
    if rc != 0:
        return [], err
    tabs = []
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) >= 4:
            try:
                tabs.append((int(parts[0]), int(parts[1]), parts[2], parts[3]))
            except ValueError:
                pass
    return tabs, ""


def close_cna():
    """关掉系统弹出的登录小窗。它会独占门户页面，不关掉浏览器就打不开。"""
    try:
        subprocess.run(["/usr/bin/osascript", "-e",
                        'tell application "Captive Network Assistant" to quit'],
                       capture_output=True, timeout=15)
    except Exception:
        pass
    try:
        subprocess.run(["/usr/bin/killall", "captiveagent"],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    time.sleep(1.5)


def close_portal_tabs():
    """关掉旧的门户标签，避免复用到过期的错误页或已在线状态页。"""
    tabs, _ = list_tabs()
    n = 0
    for wi, ti, url, _t in sorted(tabs, key=lambda x: (x[0], x[1]), reverse=True):
        if PORTAL_HOST in url:
            osa('tell application "' + APP + '"\n  try\n    close tab %d of window %d\n  end try\nend tell\n'
                % (ti, wi), timeout=10)
            n += 1
    time.sleep(0.8)
    return n


def open_portal():
    script = (
        'tell application "' + APP + '"\n'
        '  activate\n'
        '  if (count of windows) = 0 then\n'
        '    make new window\n'
        '    delay 0.8\n'
        '  end if\n'
        '  make new tab at end of tabs of front window with properties {URL:"' + PORTAL_URL + '"}\n'
        '  set active tab index of front window to (count of tabs of front window)\n'
        'end tell\n'
    )
    return osa(script, timeout=25)


def find_portal_tab():
    tabs, _ = list_tabs()
    for wi, ti, url, title in tabs:
        if PORTAL_HOST in url:
            return (wi, ti, url, title)
    return None


def exec_js(wi, ti, js, timeout=45):
    fd, path = tempfile.mkstemp(suffix=".js")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(js)
    script = (
        'set jsCode to (read POSIX file "' + path + '" as «class utf8»)\n'
        'tell application "' + APP + '"\n'
        '  execute tab ' + str(ti) + ' of window ' + str(wi) + ' javascript jsCode\n'
        'end tell\n'
    )
    try:
        return osa(script, timeout=timeout)
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def fill_js(pw):
    return """
(function(u, p) {
  function vis(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    var st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none';
  }
  function setv(el, v) {
    if (!el) return false;
    el.focus();
    el.value = v;
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    return true;
  }
  function pick(l) {
    for (var i = 0; i < l.length; i++) { if (vis(l[i])) return l[i]; }
    return null;
  }
  function fire(el) {
    if (!el) return false;
    try {
      el.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
      el.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
      el.click();
      return true;
    } catch (e) { return false; }
  }
  var uEl = pick(document.querySelectorAll('#username, input[name=username], input[name=user_name], input[type=text]'));
  var pEl = pick(document.querySelectorAll('#password, input[type=password], input[name=password]'));
  var okU = setv(uEl, u), okP = setv(pEl, p), clicked = false;

  var btn = document.querySelector('.btn-login, #login, button[type=submit], input[type=submit]');
  if (btn) clicked = fire(btn);

  if (!clicked) {
    var all = document.querySelectorAll('button,a,span,div');
    for (var n = 0; n < all.length; n++) {
      var t = ((all[n].innerText || '') + '').split(' ').join('');
      if (t.indexOf('登录') >= 0 && t.length <= 12 && vis(all[n]) && !all[n].querySelector('input,button,a')) {
        clicked = fire(all[n]);
        if (clicked) break;
      }
    }
  }
  return JSON.stringify({url: location.href, user: okU, pass: okP, clicked: clicked});
})(%s, %s);
""" % (json.dumps(USERNAME), json.dumps(pw))


def probe_internet():
    try:
        req = urllib.request.Request(PROBE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status == 204
    except Exception:
        return False


def main():
    ip = local_ip()
    if not ip.startswith(CAMPUS_IP_PREFIX):
        print(json.dumps({"ok": False, "error": "not_on_campus_network", "ip": ip}))
        return 5

    # 本来就在线：直接算成功，不折腾网卡也不开标签页
    if probe_internet():
        print(json.dumps({"ok": True, "already_online": True, "ip": ip}))
        return 0

    pw = keychain_password()
    if not pw:
        print(json.dumps({"ok": False, "error": "no_password_in_keychain"}))
        return 2

    steps = []
    close_cna()
    steps.append({"step": "close_cna"})
    steps.append({"step": "close_old_tabs", "closed": close_portal_tabs()})
    _, err, rc = open_portal()
    steps.append({"step": "open_tab", "rc": rc, "err": err[:200]})
    time.sleep(7)

    target = find_portal_tab()
    if not target:
        print(json.dumps({"ok": False, "error": "portal_tab_not_found", "steps": steps}))
        return 1

    wi, ti, _url, _title = target
    out, err, rc = exec_js(wi, ti, fill_js(pw))
    steps.append({"step": "fill_and_click", "rc": rc, "out": out, "err": err[:200]})

    ok = False
    for i in range(15):
        time.sleep(3)
        if probe_internet():
            ok = True
            steps.append({"step": "internet_up", "poll": i + 1})
            break

    if ok:
        subprocess.run(["/usr/bin/killall", "captiveagent"], capture_output=True)

    print(json.dumps({"ok": ok, "steps": steps}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
