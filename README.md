# Unblock CHN

Unblock CHN 是一个帮助配置 Shadowsocks 回国代理分流的命令行小工具，实现通过路由器或 Surge 自动分流，将国内一些网站的访问通过 Shadowsocks 代理回国，用以解除这些网站的海外访问限制，其它流量则会正常直连不走回国代理。

当然前提是你需要有一台位于国内的 Shadowsocks 服务器，在国内的路由器上[部署 Shadowsocks 服务器端](https://github.com/gxfxyz/unblockchn/wiki/在华硕梅林固件（Asuswrt-Merlin）路由器上部署-Shadowsocks-服务器端（ss-server）)也是可行的。

分流规则提取自 [Unblock Youku](https://github.com/uku/Unblock-Youku)，Unblock Youku 的规则中一般只包含站点用于检测的地址 ，不包含实际音视频流的地址，因此大部分情况下音视频流可以直连不用走代理，这样可以避免音视频变慢，也可以有效节约代理服务器的流量。

### Unblock CHN 的功能分为两部分：

* [路由器](#%E8%B7%AF%E7%94%B1%E5%99%A8)
    + [原理](#%E5%8E%9F%E7%90%86)
    + [安装](#%E5%AE%89%E8%A3%85)
    + [使用](#%E4%BD%BF%E7%94%A8)
        - [一键配置路由器](#%E4%B8%80%E9%94%AE%E9%85%8D%E7%BD%AE%E8%B7%AF%E7%94%B1%E5%99%A8)
        - [查看代理状态](#%E6%9F%A5%E7%9C%8B%E4%BB%A3%E7%90%86%E7%8A%B6%E6%80%81)
        - [关闭代理](#%E5%85%B3%E9%97%AD%E4%BB%A3%E7%90%86)
        - [开启代理](#%E5%BC%80%E5%90%AF%E4%BB%A3%E7%90%86)
        - [检查 <URL/IP/域名> 是否走代理](#%E6%A3%80%E6%9F%A5-urlip%E5%9F%9F%E5%90%8D-%E6%98%AF%E5%90%A6%E8%B5%B0%E4%BB%A3%E7%90%86)
        - [更新规则](#%E6%9B%B4%E6%96%B0%E8%A7%84%E5%88%99)
        - [还原路由器为未配置状态](#%E8%BF%98%E5%8E%9F%E8%B7%AF%E7%94%B1%E5%99%A8%E4%B8%BA%E6%9C%AA%E9%85%8D%E7%BD%AE%E7%8A%B6%E6%80%81)
        - [仅生成 ipset 和 dnsmasq 规则配置文件](#%E4%BB%85%E7%94%9F%E6%88%90-ipset-%E5%92%8C-dnsmasq-%E8%A7%84%E5%88%99%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6)
        - [修改规则模板](#%E4%BF%AE%E6%94%B9%E8%A7%84%E5%88%99%E6%A8%A1%E6%9D%BF)
    + [远程控制工具](#%E8%BF%9C%E7%A8%8B%E6%8E%A7%E5%88%B6%E5%B7%A5%E5%85%B7)
        - [iOS 捷径（Shortcut）](#ios-%E6%8D%B7%E5%BE%84shortcut)
        - [Alfred Workflow](#alfred-workflow)
* [Surge](#surge)
    + [现成配置](#%E7%8E%B0%E6%88%90%E9%85%8D%E7%BD%AE)
        - [配置文件](#%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6)
        - [RULESET 文件](#ruleset-%E6%96%87%E4%BB%B6)
    + [安装](#%E5%AE%89%E8%A3%85-1)
    + [使用](#%E4%BD%BF%E7%94%A8-1)
        - [准备模板](#%E5%87%86%E5%A4%87%E6%A8%A1%E6%9D%BF)
        - [生成配置文件](#%E7%94%9F%E6%88%90%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6)
        - [指定目录](#%E6%8C%87%E5%AE%9A%E7%9B%AE%E5%BD%95)
        - [生成基于 URL 正则表达式的规则](#%E7%94%9F%E6%88%90%E5%9F%BA%E4%BA%8E-url-%E6%AD%A3%E5%88%99%E8%A1%A8%E8%BE%BE%E5%BC%8F%E7%9A%84%E8%A7%84%E5%88%99)
        - [生成 RULESET](#%E7%94%9F%E6%88%90-ruleset)

---

## 路由器

目前仅支持[华硕梅林固件（Asuswrt-Merlin）](https://asuswrt.lostrealm.ca)，其它支持 ss-redir + iptables + ipset + dnsmasq 的路由器固件或许也可以使用，但可能需要修改部分配置或代码。

### 原理

1. 从 Unblock Youku 的 [urls.js](https://github.com/uku/Unblock-Youku/blob/master/shared/urls.js) 中提取分流规则。

2. 根据分流规则生成 dnsmasq 和 ipset 规则，将需要回国代理的 IP 地址加入 chn ipset。

3. 添加 iptables 规则，将属于 chn ipset 的请求转发到 Shadowsocks 透明代理工具 ss-redir 的端口，通过 Shadowsocks 代理回国。

Unblock CHN 自动化以上过程，提供了一键配置路由器的命令和一些管理命令。

### 安装

1. 在路由器上插入一个 U 盘，用来安装 Unblock CHN 和相关程序。

2. [在路由器上安装 Entware](https://github.com/gxfxyz/unblockchn/wiki/在华硕梅林固件（Asuswrt-Merlin）路由器上安装-Entware)。

3. 安装依赖程序：

```console
# Python3
$ opkg install python3

# pip3
$ opkg install python3-pip

# Git
$ opkg install git-http

# Shadowsocks 透明代理工具 ss-redir
$ opkg install shadowsocks-libev-ss-redir
```

4. 安装 Unblock CHN：

```console
# 进入 U 盘目录（例如 /tmp/mnt/sda1）
$ cd /tmp/mnt/sda1

# 安装 Unblock CHN
$ git clone https://github.com/gxfxyz/unblockchn.git

# 进入 Unblock CHN 目录
$ cd unblockchn

# 安装 Unblock CHN 依赖
$ pip3 install -r requirements.txt
```

### 使用

```console
$ python3 unblockchn.py router --help
usage: python3 unblockchn.py router [-h] {status,on,off,check,renew,setup,restore,create}

Unblock CHN 路由器命令：
  status                  查看代理状态
  on                      开启代理
  off                     关闭代理
  check <URL/IP/域名>     检查 <URL/IP/域名> 是否走代理
  renew                   更新规则
  setup [--no-ss]         一键配置路由器 [--no-ss: 跳过配置 ss-redir]
  restore [--no-ss]       还原路由器为未配置状态 [--no-ss: 跳过还原 ss-redir]
  create                  仅生成 ipset 和 dnsmasq 规则配置文件

positional arguments:
  {status,on,off,check,renew,setup,restore,create}

optional arguments:
  -h, --help            show this help message and exit
```

#### 一键配置路由器

```console
$ python3 unblockchn.py router setup
Shadowsocks 服务器地址：xxx.xxx.xxx.xxx
Shadowsocks 服务器端口：xxxx
Shadowsocks 密码：xxxxxxxxxx
Shadowsocks 加密方法：xxxxxxx
✔ 保存 ss-redir 配置文件：/tmp/mnt/sda1/unblockchn/ss-redir.json
✔ 启动 ss-redir：/opt/bin/ss-redir -c /tmp/mnt/sda1/unblockchn/ss-redir.json -f /tmp/mnt/sda1/unblockchn/ss-redir.pid
✔ 保存 ss-redir 启动命令到路由器的 services-start 启动脚本中：/jffs/scripts/services-start
✔ 生成 ipset 默认配置模板文件：ipset.rules.tpl
✔ 生成 ipset 配置文件：ipset.rules & ipset.headless.rules
✔ 生成 dnsmasq 默认配置模板文件：dnsmasq.conf.add.tpl
✔ 生成 dnsmasq 配置文件：dnsmasq.conf.add
✔ 复制：/tmp/mnt/sda1/unblockchn/ipset.rules -> /jffs/configs/ipset.rules
✔ 复制：/tmp/mnt/sda1/unblockchn/dnsmasq.conf.add -> /jffs/configs/dnsmasq.conf.add
✔ 载入 ipset 规则：ipset restore < /jffs/configs/ipset.rules
✔ 保存 ipset 载入命令到路由器的 nat-start 启动脚本中：/jffs/scripts/nat-start
✔ 添加 iptables 规则：iptables -t nat -A PREROUTING -p tcp -m set --match-set chn dst -j REDIRECT --to-port 1080
✔ 保存 iptables 规则添加命令到路由器的 nat-start 启动脚本中：/jffs/scripts/nat-start
✔ 重启 dnsmasq：service restart_dnsmasq
✔ 定时每日 3 点更新规则：cru a unblockchn_renew "0 3 * * * /opt/bin/python3 /tmp/mnt/sda1/unblockchn/unblockchn.py router renew"
✔ 保存定时更新规则命令到路由器的 services-start 启动脚本中：/jffs/scripts/services-start
配置成功
```

如果想要跳过配置 ss-redir，那么就加上 --no-ss 参数：

```console
$ python3 unblockchn.py router setup --no-ss
```

至此，回国代理和自动分流就配置并开启好了。

可以访问下列地址以验证回国代理是否成功，如果显示 `true`，就说明回国代理已生效： 

http://uku.im/check

#### 查看代理状态

```console
$ python3 unblockchn.py router status
已开启
```

#### 关闭代理

```console
$ python3 unblockchn.py router off
关闭成功
```
#### 开启代理

```console
$ python3 unblockchn.py router on
开启成功
```

#### 检查 <URL/IP/域名> 是否走代理

```console
$ python3 unblockchn.py router check http://ipservice.163.com/isFromMainland
59.111.19.7 走代理

$ python3 unblockchn.py router check https://google.com
216.58.193.78 不走代理

$ python3 unblockchn.py router check www.bilibili.com
148.153.45.166 走代理

$ python3 unblockchn.py router check 192.168.2.1
192.168.2.1 不走代理
```

#### 更新规则

```console
$ python3 unblockchn.py router renew
✔ 生成 ipset 配置文件：ipset.rules & ipset.headless.rules
✔ 生成 dnsmasq 配置文件：dnsmasq.conf.add
✔ 复制：/tmp/mnt/sda1/unblockchn/ipset.rules -> /jffs/configs/ipset.rules
✔ 复制：/tmp/mnt/sda1/unblockchn/dnsmasq.conf.add -> /jffs/configs/dnsmasq.conf.add
✔ 清空 ipset 的 chn 表：ipset flush chn
✔ 载入 ipset 规则：ipset restore < /tmp/mnt/sda1/unblockchn/ipset.headless.rules
✔ 重启 dnsmasq：service restart_dnsmasq
更新成功
```

Unblock CHN 在路由器上默认定时每日 03:00 自动更新分流规则，及时跟进 Unblock Youku 规则的变化。

#### 还原路由器为未配置状态

```console
$ python3 unblockchn.py router restore
✔ 停止 ss-redir：kill 3002
✔ 从启动脚本里移除 ss-redir 启动命令：/jffs/scripts/services-start
✔ 删除：/jffs/configs/ipset.rules
✔ 删除：/jffs/configs/dnsmasq.conf.add
✔ 删除 iptables 规则：iptables -t nat -D PREROUTING -p tcp -m set --match-set chn dst -j REDIRECT --to-port 1080
✔ 从启动脚本里移除 iptables 规则添加命令：/jffs/scripts/nat-start
✔ 删除 ipset 的 chn 表：ipset destroy chn
✔ 从启动脚本里移除 ipset 载入命令：/jffs/scripts/nat-start
✔ 删除每日更新规则的 cron 定时任务：cru d unblockchn_renew
✔ 从启动脚本里移除定时命令：/jffs/scripts/services-start
✔ 重启 dnsmasq：service restart_dnsmasq
还原成功
```

如果想要跳过还原 ss-redir，那么就加上 --no-ss 参数：

```console
$ python3 unblockchn.py router restore --no-ss
```

#### 仅生成 ipset 和 dnsmasq 规则配置文件

```console
$ python3 unblockchn.py router create
✔ 生成 ipset 默认配置模板文件：ipset.rules.tpl
✔ 生成 ipset 配置文件：ipset.rules & ipset.headless.rules
✔ 生成 dnsmasq 默认配置模板文件：dnsmasq.conf.add.tpl
✔ 生成 dnsmasq 配置文件：dnsmasq.conf.add
生成配置文件成功
```

此命令让 Unblock CHN 跳过配置路由器，仅提取 Unblock Youku 的规则，在 `unblockchn` 目录下生成相应的 ipset 和 dnsmasq 规则配置文件。

#### 修改规则模板

除了 Unblock CHN 自动生成的规则以外，如果你需要自定义一些 dnsmasq 或 ipset 规则，可以通过修改 `unblockchn` 目录下的规则模板文件 `dnsmasq.conf.add.tpl` 和 `ipset.rules.tpl` 来实现。

保留模板文件中的 `{rules}` 一行，其在生成规则时会被 Unblock CHN 规则替换，然后在模板文件中添加你需要的规则，例如：

dnsmasq.conf.add.tpl
```
# NAS
address=/nas.xxxx.com/192.168.1.100
# CCTV
address=/cctv.xxxx.com/192.168.1.200
{rules}
```

ipset.rules.tpl
```
{rules}
create blacklist hash:ip family inet hashsize 1024 maxelem 65536
add blacklist 103.31.6.5
add blacklist 208.73.51.100
```

运行更新规则命令来使自定义的规则生效：

```console
$ python3 unblockchn.py router renew
```

### 远程控制工具

#### iOS 捷径（Shortcut）

在 iOS 的通知中心里远程（局域网内）控制路由器上的 Unblock CHN 代理。

![unblockchn_shortcut](https://user-images.githubusercontent.com/43481676/47972350-2d7d6c00-e050-11e8-8c52-aa7152f8f795.jpg)

[点此安装](https://www.icloud.com/shortcuts/105e946b6e8844cc82fd870038cfb8a5)

#### Alfred Workflow

在 macOS 上用 Alfred 来远程（局域网内）控制路由器上的 Unblock CHN 代理。

![unblockchn_alfred](https://user-images.githubusercontent.com/43481676/47972357-53a30c00-e050-11e8-9104-7dd640b8b6e8.png)

[点此下载](https://github.com/gxfxyz/unblockchn/raw/master/unblockchn.alfredworkflow)

**关键词：**

unblockchn

**设置：**

使用前需要先设置路由器 SSH 免密码登录：

1. 生成密钥：

```console
$ ssh-keygen -t rsa
```

2. 查看密钥：

```console
$ cat ~/.ssh/id_rsa.pub
```

3. 复制密钥到路由器管理页面：

```
系统管理 - 系统设置 - 服务 - 授权密钥
```

除此之外，在 Workflow 设置里点 [x] 按钮可以设置一些参数：

- router_ip:  路由器 IP 地址（默认 `192.168.1.1`）
- router_user:  路由器用户名（默认 `admin`）
- unblockchn_py_path:  unblockchn.py 在路由器上的路径（默认 `/tmp/mnt/sda1/unblockchn/unblockchn.py`）

---

## Surge

Unblock CHN 从 Unblock Youku 提取分流规则，生成相应的 Surge 规则配置文件，供 [Surge](https://itunes.apple.com/us/app/id1329879957) 或 [Shadowrocket](https://itunes.apple.com/us/app/shadowrocket/id932747118) 使用，实现在 iOS 或 macOS 上解除国内网站的海外访问限制。

### 现成配置

懒得亲自运行 Unblock CHN？你可以直接使用下列 Unblock CHN 已经生成好的 Surge 配置文件或 ruleset 文件。

如果 Unblock CHN 的规则有变化，下列文件会定时自动更新。

#### 配置文件

[unblockchn.surge.conf](https://gist.github.com/gxfxyz/0d0d91c526a6b07f59a700039f9fa334#file-unblockchn-surge-conf)

[下载](https://gist.githubusercontent.com/gxfxyz/0d0d91c526a6b07f59a700039f9fa334/raw/22b3b052b145ebd3c0e6b6b3726c3bdac4c7bc0b/unblockchn.surge.conf)后修改代理服务器信息就可使用。

若使用的是 Shadowrocket，可以分开设置代理节点，然后通过 [URL](https://gist.githubusercontent.com/gxfxyz/0d0d91c526a6b07f59a700039f9fa334/raw/22b3b052b145ebd3c0e6b6b3726c3bdac4c7bc0b/unblockchn.surge.conf) 单独更新配置内的规则。

#### RULESET 文件

[unblockchn.surge.ruleset](https://gist.github.com/gxfxyz/0d0d91c526a6b07f59a700039f9fa334#file-unblockchn-surge-ruleset)

[RULESET](https://nssurge-english.zendesk.com/hc/en-us/articles/360010493933-Surge-Mac-3-Release-Note) 是 Surge Mac 3 新加入的功能，目前 iOS 版 Surge 还未支持（Shadowrocket 也不支持）。

RULESET 让 Surge 配置文件可以通过路径或 URL 来引用外部规则文件，例如你可以这样引用 Unblock CHN 的 ruleset：

```
RULE-SET,https://git.io/fxjWu,PROXY
```

而完整配置文件就可以简化成这样：

[unblockchn.surge.ruleset.conf](https://gist.github.com/gxfxyz/0d0d91c526a6b07f59a700039f9fa334#file-unblockchn-surge-ruleset-conf)

这样若 Unblock CHN 的规则有更新，你可以通过重载配置文件来更新 RULESET 引用的规则，而无需更新整个配置文件。

### 安装

1. 安装 Unblock CHN：

```console
$ git clone https://github.com/gxfxyz/unblockchn.git
```

2. 进入 Unblock CHN 目录：

```console
$ cd unblockchn
```

3. 安装 Unblock CHN 依赖：

- 通过 [pipenv](https://github.com/pypa/pipenv)（推荐）

```console
# 安装依赖并创建虚拟环境
$ pipenv install

# 激活 pipenv 虚拟环境
$ pipenv shell
```

- 通过 pip

```console
$ pip3 install -r requirements.txt
```

### 使用

```console
$ python3 unblockchn.py surge --help
usage: python3 unblockchn.py surge [-h] [-d DST]

Unblock CHN

生成 Surge 配置文件

optional arguments:
  -h, --help         show this help message and exit
  -u, --url          生成基于 URL 正则表达式的规则（默认基于域名）
  -r, --ruleset      生成 Surge ruleset 文件
  -d DST, --dst DST  保存生成的文件到此目录
```

#### 准备模板

Unblock CHN 生成配置时，会在 `unblockchn` 目录下查找 `.conf.tpl` 后缀的 Surge 配置模板文件，因此你需要先准备至少一个模板文件。

复制样例模板文件 `sample_surge.conf.tpl`，重命名为例如 `surge.conf.tpl`。

用文件编辑器打开 `surge.conf.tpl` ，修改 Shadowrocket 服务器的地址、端口、加密方式、密码等信息。

你也可以加入其它 Surge 规则，但要保留 `{rules}` 一行，其在生成配置时会被 Unblock CHN 规则替换。

#### 生成配置文件

```console
$ python3 unblockchn.py surge
✔ 生成 Surge 配置文件：surge.conf
```

Unblock CHN 就会在目录下生成模板文件 `surge.conf.tpl` 对应的 Surge 配置文件 `surge.conf`。

Surge 或 Shadowrocket 载入配置文件后，可以访问下列地址以验证回国代理是否成功，如果显示 `true`，就说明回国代理已生效： 

http://uku.im/check

#### 指定目录

你可以添加 `-d` 参数，让 Unblock CHN 在生成配置文件后，将其复制到另外一个文件夹，例如 iCloud Drive 或其它网盘文件夹，这样可以方便在手机上更新配置文件：

```console
$ python3 unblockchn.py surge -d ~/Library/Mobile\ Documents/iCloud~run~surge/Documents
✔ 生成 Surge 配置文件：surge.conf
✔ 保存 Surge 配置文件到：/Users/User/Library/Mobile Documents/iCloud~run~surge/Documents/surge.conf
```

#### 生成基于 URL 正则表达式的规则

你可以使用 `--url` 参数：

```console
$ python3 unblockchn.py surge --url
```

让 Unblock CHN 生成基于 URL 正则表达式的 Surge 规则，例如：

```
URL-REGEX,^http://bangumi\.bilibili\.com/api/.*,PROXY
```

而 Unblock CHN 默认生成的是基于域名的 Surge 规则，例如：

```
DOMAIN,bangumi.bilibili.com,PROXY
```

域名规则会让整个域名下的所有 URL 都走回国代理，而 URL 规则只会让匹配正则表达式的 URL 走回国代理。

URL 规则的好处是匹配更准确，站点一般只通过几个特定 URL 来检测用户地区，因此只需要代理这些 URL 就好了，其它网站页面和资源可以直连。但是站点用来检测的 URL 很可能经常会变化，而 Unblock Youku 的 URL 规则往往是滞后的、不完善的，因此容易导致解锁失败。而且 URL 规则只对 HTTP 请求有效，HTTPS 请求因为加密了 URL，无法用 URL 规则来匹配，所以仍需要通过域名规则来代理，现在大部分网站也默认采用 HTTPS，因此 URL 规则实用性不是很好。

相比之下，域名规则虽然会让整个域名下的页面和资源都走回国代理，但是覆盖面广，规则不容易失效。而且站点的音视频流一般通过 CDN 来分发，会使用不同的域名，因此即使使用域名规则，大部分情况下音视频流还是会直连不走回国代理。

所以 Unblock CHN 默认且推荐使用基于域名的规则。

#### 生成 RULESET

你可以使用 `--ruleset` 参数，让 Unblock CHN 生成回国规则的 ruleset 文件 `unblockchn.surge.ruleset`：

```console
$ python3 unblockchn.py surge --ruleset
✔ 生成 Surge ruleset 文件：unblockchn.surge.ruleset
```

[RULESET 文件的使用](#ruleset-%E6%96%87%E4%BB%B6)

---

## 一些说明

1. Unblock Youku 的规则可能会失效，如果你遇到某个站点无法解锁，可以[向 Unblock Youku 反馈](https://bbs.uku.im)。

2. 因为 Unblock Youku 的规则主要是针对浏览器 Web 端，而一些手机端 App 有可能会采用不同的检测，所以可能需要手动添加一些额外规则才能解锁这些手机端 App。

3. 国内一些网站在海外可能会使用同一个 CDN 服务商，导致不同网站的域名会被解析为相同的 IP，由于 Unblock CHN 在路由器上实质是基于 IP 来分流的，因此可能会造成不需要代理回国的域名被误代理。目前，我发现微博图片的 `ws1.sinaimg.cn` 等域名和 B 站的 `data.bilibili.com` 域名有时会出现这种被解析到相同 IP 的情况，导致微博图片被误代理回国。临时解决办法是用 `renew` 命令来重置下 ipset，微博图片应该就能恢复直连，直到下一次访问 B 站。

4. 更新 Unblock CHN：`git pull`

5. `default_config.py` 里有一些配置项，你可以将其复制为 `config.py` 后进行修改，`config.py` 内的配置会覆盖 `default_config.py` 内的配置。

6. 目录下的 `unblockchn.log` 为日志文件，记录了运行过的命令和结果。

7. 本项目衍生自 Unblock Youku，如果你觉得本项目或 Unblock Youku 有用，请考虑[向 Unblock Youku  捐款](https://www.uku.im/) ❤️。

---

## 许可协议

[AGPL v3](LICENSE)
