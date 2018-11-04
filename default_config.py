#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os


# unblockchn 目录路径
DIR_PATH = os.path.dirname(os.path.realpath(__file__))

# Unblock Youku 的规则文件 urls.js 链接
UNBLOCK_YOUKU_URLSJS_URL = "https://raw.githubusercontent.com/uku/Unblock-Youku/master/shared/urls.js"


# --- router ---

# python3 命令路径
PYTHON3_PATH = "/opt/bin/python3"

# ss_redir 命令路径
SS_REDIR_PATH = "/opt/bin/ss-redir"
# ss_redir 配置文件路径
SS_REDIR_CONF_PATH = os.path.join(DIR_PATH, "ss-redir.json")
# ss_redir pid 文件路径
SS_REDIR_PID_PATH = os.path.join(DIR_PATH, "ss-redir.pid")
# ss_redir 本地端口
SS_REDIR_LOCAL_PORT = 1080
# ss_redir 配置
SS_REDIR_CONF = {
    "server": None,
    "server_port": None,
    "local_address": "0.0.0.0",
    "local_port": SS_REDIR_LOCAL_PORT,
    "password": None,
    "timeout": 300,
    "method": None,
    "fast_open": False,
    "mode": "tcp_and_udp"
}

# iptables 添加 chn ipset 规则命令
ADD_IPTABLES_CHN_CMD = "iptables -t nat -A PREROUTING -p tcp -m set --match-set chn dst -j REDIRECT --to-port {}".format(SS_REDIR_LOCAL_PORT)
# iptables 删除 chn ipset 规则命令
DELETE_IPTABLES_CHN_CMD = "iptables -t nat -D PREROUTING -p tcp -m set --match-set chn dst -j REDIRECT --to-port {}".format(SS_REDIR_LOCAL_PORT)
# iptables 检查 chn ipset 规则命令
CHECK_IPTABLES_CHN_CMD = "iptables -t nat -C PREROUTING -p tcp -m set --match-set chn dst -j REDIRECT --to-port {}".format(SS_REDIR_LOCAL_PORT)

# ipset 规则配置文件在 jffs 分区下的保存路径
IPSET_CONF_JFFS_PATH = "/jffs/configs/ipset.rules"
# dnsmasq 规则配置文件在 jffs 分区下的保存路径
DNSMASQ_CONF_JFFS_PATH = "/jffs/configs/dnsmasq.conf.add"

# services-start 启动脚本路径
SERVICES_START_SCRIPT_PATH = "/jffs/scripts/services-start"
# nat-start 启动脚本路径
NAT_START_SCRIPT_PATH = "/jffs/scripts/nat-start"

# dnsmasq 重启命令
DNSMASQ_RESTART_CMD = "service restart_dnsmasq"

# 定时每天几点更新规则
RENEW_TIME = 3


# --- surge ---

# Surge 配置中 Proxy Group 名
SURGE_PROXY_GROUP_NAME = "PROXY"
