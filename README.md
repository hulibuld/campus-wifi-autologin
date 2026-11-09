# campus-wifi-autologin

晚上跑长任务，宿舍里只有校园网能通。每次开机都要点 WiFi、等认证页弹出来、填账号密码、点登录，做完才能开始跑。这个脚本把这几步串起来，定时自动做掉。

只做两件事：把 WiFi 切到学校那个 SSID，再用浏览器把登录表单填好并提交。

## 依赖

- macOS
- Google Chrome
- Chrome 菜单里打开「视图 → 开发者 → 允许 Apple 事件中的 JavaScript」。不开这个，脚本没法在页面里填表。
- Python 3，系统自带的 `/usr/bin/python3` 够用

## 装

1. 把两个脚本放到 `~/campus-wifi/`：

```
campus_auto.sh
browser_login.py
```

2. 改脚本头部的配置块。

`campus_auto.sh`：

```bash
IFACE="en0"                     # 无线网卡接口名，用 networksetup -listallhardwareports 查
SSID_PRIMARY="CampusWiFi-5G"    # 首选 SSID
SSID_FALLBACK="CampusWiFi"      # 备选 SSID
CAMPUS_IP_PREFIX="10."          # 校园网内网 IP 前缀
```

`browser_login.py`：

```python
PORTAL_URL = "http://10.0.0.1/"       # 认证页地址，末尾带斜杠
PORTAL_HOST = "10.0.0.1"              # 同上，用来识别门户标签
USERNAME = "YOUR_STUDENT_ID"
KEYCHAIN_SERVICE = "campus-portal"
CAMPUS_IP_PREFIX = "10."
```

接口名找 `Hardware Port: Wi-Fi` 下面那行 `Device:` 就是。

3. 密码存进钥匙串：

```bash
security add-generic-password -a "$USER" -s campus-portal -U -w
```

回车后会提示输入密码，屏幕不显示字符是正常的。脚本运行时用 `security find-generic-password` 取，不会出现在任何文件里。

4. 加执行权限：

```bash
chmod +x ~/campus-wifi/campus_auto.sh ~/campus-wifi/browser_login.py
```

## 用

手动跑一次：

```bash
bash ~/campus-wifi/campus_auto.sh --now
```

看日志：

```bash
tail -20 ~/campus-wifi/logs/auto.log
```

成功时日志最后一行是 `成功：<SSID>`，同时屏幕上弹一条「校园网已就绪」。

## 定时

`com.example.campuswifi.plist` 是定时任务模板。把里面的 `/Users/YOURUSER/...` 改成你自己的路径，放到 `~/Library/LaunchAgents/`，然后加载：

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.campuswifi.plist
```

停掉：

```bash
launchctl bootout gui/$(id -u)/com.example.campuswifi
```

## 它怎么判断成功

只看一条：提交登录之后，脚本每 3 秒探一次 `generate_204`，最多 45 秒，回 204 才算通。

不靠页面有没有跳转。认证页的登录请求走 AJAX，提交后页面通常停在原地，跳不跳和成不成没关系。这一点是踩过坑之后定下来的。

另外，开浏览器之前会先探一次外网：如果本来就是通的，直接判成功并跳过，不碰网卡也不开标签页。没有这一步，网络本来好的时候会被误判成失败，然后去电源循环，把好好的连接断掉。

## 已知限制

- 只支持 macOS，靠 AppleScript 驱动 Chrome，Safari 不行
- 认证页改版后，`browser_login.py` 里 `fill_js` 的选择器可能要跟着改
- 登录失败不会自动切回原来的网络，得手动处理
- 5GHz 覆盖范围小，扫不到时会退到 2.4GHz，每次多花几十秒

## 说明

用自己的账号、在自己的设备上，把本来就要做一遍的手动操作交给脚本。不涉及抓包、逆向或绕过认证。

MIT License.
