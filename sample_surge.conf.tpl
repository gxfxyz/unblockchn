[General]
loglevel = notify
bypass-system = true
skip-proxy = 127.0.0.1, 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, 100.64.0.0/10, localhost, *.local
bypass-tun = 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12
ipv6 = true

[Proxy]
SS = custom, 服务器地址, 端口, 加密方式, 密码, https://raw.githubusercontent.com/ConnersHua/SSEncrypt/master/SSEncrypt.module

[Proxy Group]
PROXY = select, DIRECT, SS

[Rule]
// Unblock CHN
{rules}
// FINAL
FINAL,DIRECT
