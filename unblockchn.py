#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import json
import socket
import shutil
import logging
import argparse
import subprocess
import logging.handlers
from urllib.parse import urlsplit
from collections import OrderedDict

import requests

try:
    from config import *
except ImportError:
    from default_config import *


elogger = logging.getLogger('stderr')
ologger = logging.getLogger('stdout')


def main():
    """python3 unblockchn.py [-h] {router,surge,acl}

Unblock CHN 命令：
  router                  路由器相关命令
  surge                   Surge 相关命令
  acl                     acl相关命令
"""
    elogger.debug("")
    elogger.debug(" ".join(sys.argv))

    # 整理一些文件到相应的子目录中（为了向后兼容）
    organize()

    parser = argparse.ArgumentParser(usage=main.__doc__)
    parser.add_argument('cmd', choices=['router', 'surge','acl'])
    args = parser.parse_args(sys.argv[1:2])

    if args.cmd == 'router':
        Router.execute(sys.argv[2:])
    elif args.cmd == 'surge':
        Surge.execute(sys.argv[2:])
    elif args.cmd == 'acl':
        Acl.execute(sys.argv[2:])

class Router(object):

    @classmethod
    def execute(cls, raw_args):
        """python3 unblockchn.py router [-h] {status,on,off,servers,switch,check,renew,setup,restore,create}

Unblock CHN 路由器命令：
  status                    查看代理状态
  on                        开启代理
  off                       关闭代理
  servers [--json]          列出代理服务器 [--json: 输出 json 格式]
  switch [name] [--auto]    切换代理服务器 [--auto: 自动选择延迟最低的代理服务器]
  check <URL/IP/域名>       检查 <URL/IP/域名> 是否走代理
  renew                     更新规则
  setup [--no-ss]           一键配置路由器 [--no-ss: 跳过配置 ss-redir]
  restore [--no-ss]         还原路由器为未配置状态 [--no-ss: 跳过还原 ss-redir]
  create                    仅生成 ipset 和 dnsmasq 规则配置文件
"""
        parser = argparse.ArgumentParser(usage=cls.execute.__doc__)
        parser.add_argument(
            'cmd',
            choices=['status', 'on', 'off', 'servers', 'switch', 'check', 'renew', 'setup', 'restore', 'create']
        )
        args = parser.parse_args(raw_args[0:1])

        if args.cmd == 'create':
            cls.cmd_create()
            return

        # 检查 iptables 和 ipset 命令是否存在
        cls.check_ipset_iptables()

        if args.cmd == 'status':
            cls.cmd_status()
        elif args.cmd == 'on':
            cls.cmd_on()
        elif args.cmd == 'off':
            cls.cmd_off()
        elif args.cmd == 'servers':
            cls.cmd_servers(raw_args[1:])
        elif args.cmd == 'switch':
            cls.cmd_switch(raw_args[1:])
        elif args.cmd == 'check':
            cls.cmd_check(raw_args[1:])
        elif args.cmd == 'renew':
            cls.cmd_renew()
        elif args.cmd == 'setup':
            cls.cmd_setup(raw_args[1:])
        elif args.cmd == 'restore':
            cls.cmd_restore(raw_args[1:])

    @classmethod
    def cmd_status(cls):
        """查看 Unblock CHN 代理状态"""
        cls.check_setup()
        ss_redir_running = cls.check_ss_redir()
        if not ss_redir_running:
            ologger.info("ss-redir 未运行")
            return
        iptables_chn_exists = cls.check_iptables_chn()
        if iptables_chn_exists:
            ss_redir_conf_name = cls.get_nvram("unblockchn_ss_conf")
            ologger.info(f"已开启 ({ss_redir_conf_name})")
        else:
            ologger.info("已关闭")

    @classmethod
    def cmd_on(cls):
        """开启 Unblock CHN 代理"""
        cls.check_setup()
        ss_redir_running = cls.check_ss_redir()
        if not ss_redir_running:
            cls.start_ss_redir()
        iptables_chn_exists = cls.check_iptables_chn()
        if not iptables_chn_exists:
            cls.add_iptables_chn()
        ss_redir_conf_name = cls.get_nvram("unblockchn_ss_conf")
        if ss_redir_running and iptables_chn_exists:
            ologger.info(f"已经开启 ({ss_redir_conf_name})")
        else:
            ologger.info(f"开启成功 ({ss_redir_conf_name})")
        # 记录开启状态到 nvram 变量
        cls.set_nvram('unblockchn_on', "True")

    @classmethod
    def cmd_off(cls):
        """关闭 Unblock CHN 代理"""
        cls.check_setup()
        iptables_chn_exists = cls.check_iptables_chn()
        if iptables_chn_exists:
            cls.delete_iptables_chn()
            ologger.info("关闭成功")
        else:
            ologger.info("已经关闭")
        # 记录关闭状态到 nvram 变量
        cls.set_nvram('unblockchn_on', "False")

    @classmethod
    def cmd_servers(cls, raw_args):
        """python3 unblockchn.py router servers [-h] [--json]

列出代理服务器
"""
        parser = argparse.ArgumentParser(usage=cls.cmd_servers.__doc__)
        parser.add_argument('-j', '--json', action='store_true', help="输出 json 格式")
        args = parser.parse_args(raw_args)

        # 读取代理服务器（配置文件）
        confs = cls.load_ss_redir_confs()

        # 标记目前使用的代理服务器
        ss_redir_conf_name = cls.get_nvram("unblockchn_ss_conf")
        if ss_redir_conf_name:
            if ss_redir_conf_name in confs:
                confs[ss_redir_conf_name]['selected'] = True

        # 输出 json 格式
        if args.json:
            json_str = json.dumps(confs, ensure_ascii=False, indent=4)
            ologger.info(json_str)
            return

        if not confs:
            ologger.info("未配置任何代理服务器")
            return

        ologger.info(f"共有 {len(confs)} 个代理服务器：")

        for i, conf_name in enumerate(confs):
            conf = confs[conf_name]
            ologger.info(f"{i + 1}) {conf_name}")
            ologger.info(f"Shadowsocks 服务器地址：{conf['server']}")
            ologger.info(f"Shadowsocks 服务器端口：{conf['server_port']}")
            ologger.info(f"Shadowsocks 密码：{conf['password']}")
            ologger.info(f"Shadowsocks 加密方法：{conf['method']}")

        if ss_redir_conf_name:
            ologger.info("-")
            ologger.info(f"目前使用的代理服务器为：{ss_redir_conf_name}")

    @classmethod
    def cmd_switch(cls, raw_args):
        """python3 unblockchn.py router switch [-h] [name] [--auto]

切换代理服务器
"""
        parser = argparse.ArgumentParser(usage=cls.cmd_switch.__doc__)
        parser.add_argument('name', nargs='?', help="代理服务器名")
        parser.add_argument('-a', '--auto', action='store_true', help="自动选择延迟最低的代理服务器")
        args = parser.parse_args(raw_args)

        # 读取代理服务器（配置文件）
        confs = cls.load_ss_redir_confs()

        if not confs:
            ologger.error("✘ 未配置任何代理服务器")
            sys.exit(1)

        if args.auto:
            selected_conf_name = cls.auto_select(confs)
        else:
            if args.name:
                selected_conf_name = args.name
            else:
                # 手动选择代理服务器（配置文件）
                elogger.info("0) 自动选择延迟最低的代理服务器")
                for i, conf_name in enumerate(confs):
                    conf = confs[conf_name]
                    hostname = conf['server']
                    port = conf['server_port']
                    elogger.info(f"{i + 1}) {conf_name} [{hostname}:{port}]")
                r = input(f"请选择要使用的代理服务器 [0-{len(confs)}]：") or "0"
                try:
                    n = int(r)
                except ValueError:
                    elogger.error(f"✘ 无效输入：{r}")
                    sys.exit(1)
                if n > len(confs) or n < 0:
                    elogger.error(f"✘ 无效输入：{r}")
                    sys.exit(1)
                if n == 0:
                    # 自动选择延迟最低的代理服务器
                    selected_conf_name = cls.auto_select(confs)
                else:
                    selected_conf_name = list(confs)[n - 1]

        if selected_conf_name not in confs:
            ologger.error(f"✘ 不存在此代理服务器：{selected_conf_name}")
            sys.exit(1)

        # 记录选定的代理服务器名（配置文件名）到 nvram 变量
        cls.set_nvram('unblockchn_ss_conf', selected_conf_name)

        # 停止 ss-redir 若已运行
        ss_redir_running = cls.check_ss_redir()
        if ss_redir_running:
            cls.stop_ss_redir()

        # 启动 ss-redir
        cls.start_ss_redir()

        selected_conf = confs[selected_conf_name]
        latencty_info = f"（{selected_conf['latency'] * 1000:.0f} ms）" if 'latency' in selected_conf else ""
        ologger.info(f"切换到了 {selected_conf_name} 代理服务器{latencty_info}")

    @classmethod
    def cmd_check(cls, raw_args):
        """python3 unblockchn.py router check [-h] url

检查 url 是否走 Unblock CHN 代理
"""
        parser = argparse.ArgumentParser(usage=cls.cmd_check.__doc__)
        parser.add_argument('url', help="URL / IP / 域名")
        args = parser.parse_args(raw_args)

        cls.check_setup()

        if "://" in args.url:
            domain = urlsplit(args.url).hostname
        else:
            domain = args.url.split('/')[0]
        ip = socket.gethostbyname(domain)

        cmd = f"ipset test chn {ip}"
        returncode = subprocess.call(
            cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if returncode == 0:
            ologger.info(f"{ip} 走代理")
        else:
            ologger.info(f"{ip} 不走代理")

    @classmethod
    def cmd_renew(cls):
        """更新 Unblock CHN 规则"""
        cls.check_setup()

        # 生成路由器配置文件
        unblock_youku = UnblockYouku()
        cls.create_conf_files(unblock_youku.black_domains)

        # 复制 ipset 和 dnsmasq 规则配置文件到 jffs 配置目录
        cls.cp_ipset_conf_to_jffs()
        cls.cp_dnsmasq_conf_to_jffs()

        # 清空 chn 和其它自定义的 ipset 表
        cls.flush_ipset()

        # 载入 ipset 规则
        headless_ipset_conf_path = os.path.join(CONFIGS_DIR_PATH, "ipset.headless.rules")
        cmd = f"ipset restore < {headless_ipset_conf_path}"
        subprocess.check_call(cmd, shell=True)
        elogger.info(f"✔ 载入 ipset 规则：{cmd}")

        # 重启 dnsmasq
        cls.restart_dnsmasq()

        ologger.info("更新成功")

    @classmethod
    def cmd_setup(cls, raw_args):
        """python3 unblockchn.py router setup [-h] [--no-ss]

Unblock CHN 一键配置路由器
"""
        parser = argparse.ArgumentParser(usage=cls.cmd_setup.__doc__)
        parser.add_argument('--no-ss', action='store_true', help="跳过配置 ss-redir")
        args = parser.parse_args(raw_args)

        # 不跳过配置 ss-redir
        if not args.no_ss:
            # 配置 ss-redir
            cls.setup_ss_redir()

        # 生成路由器配置文件
        unblock_youku = UnblockYouku()
        cls.create_conf_files(unblock_youku.black_domains)

        # 复制 ipset 和 dnsmasq 规则配置文件到 jffs 配置目录
        cls.cp_ipset_conf_to_jffs()
        cls.cp_dnsmasq_conf_to_jffs()

        # 配置 ipset 和 iptables
        cls.setup_ipset_iptables()

        # 记录 Unblock CHN 开启状态到 nvram 变量
        cls.set_nvram('unblockchn_on', "True")

        # 重启 dnsmasq
        cls.restart_dnsmasq()

        # 添加每日更新规则的 cron 定时任务
        cls.add_renew_cron_job()

        ologger.info("配置成功")

    @classmethod
    def cmd_restore(cls, raw_args):
        """python3 unblockchn.py router setup [-h] [--no-ss]

Unblock CHN 还原路由器为未配置状态
"""
        parser = argparse.ArgumentParser(usage=cls.cmd_restore.__doc__)
        parser.add_argument('--no-ss', action='store_true', help="跳过还原 ss-redir")
        args = parser.parse_args(raw_args)

        # 不跳过还原 ss-redir
        if not args.no_ss:
            # 停止 ss-redir
            ss_redir_running = cls.check_ss_redir()
            if ss_redir_running:
                cls.stop_ss_redir()

            # 从启动脚本里移除 ss-redir 启动命令
            comment = "# ss-redir"
            cls.remove_from_script(SERVICES_START_SCRIPT_PATH, comment)
            elogger.info(f"✔ 从启动脚本里移除 ss-redir 启动命令：{SERVICES_START_SCRIPT_PATH}")

            # 删除 nvram 中 unblockchn_ss_conf 变量
            cls.remove_nvram('unblockchn_ss_conf')

        # 若 ipset 模板内有其它内容则生成对应配置文件并复制到 jffs
        # 否则就删除 jffs 中的配置文件
        ipset_has_conf = cls.create_ipset_conf_file(ipset_rules=None)
        if ipset_has_conf:
            cls.cp_ipset_conf_to_jffs()
        else:
            if os.path.isfile(IPSET_CONF_JFFS_PATH):
                os.remove(IPSET_CONF_JFFS_PATH)
                elogger.info(f"✔ 删除：{IPSET_CONF_JFFS_PATH}")

                # 从启动脚本里移除 ipset 载入命令
                comment = "# Load ipset rules"
                cls.remove_from_script(NAT_START_SCRIPT_PATH, comment)
                elogger.info(f"✔ 从启动脚本里移除 ipset 载入命令：{NAT_START_SCRIPT_PATH}")

        # 若 dnsmasq 模板内有其它内容则生成对应配置文件并复制到 jffs
        # 否则就删除 jffs 中的配置文件
        dnsmasq_has_conf = cls.create_dnsmasq_conf_file(dnsmasq_rules=None)
        if dnsmasq_has_conf:
            cls.cp_dnsmasq_conf_to_jffs()
        else:
            if os.path.isfile(DNSMASQ_CONF_JFFS_PATH):
                os.remove(DNSMASQ_CONF_JFFS_PATH)
                elogger.info(f"✔ 删除：{DNSMASQ_CONF_JFFS_PATH}")

        # 删除 iptables 规则
        iptables_chn_exists = cls.check_iptables_chn()
        if iptables_chn_exists:
            cls.delete_iptables_chn()
            elogger.info(f"✔ 删除 iptables 规则：{DELETE_IPTABLES_CHN_CMD}")

        # 从启动脚本里移除 iptables 规则添加命令
        comment = "# Redirect chn ipset to ss-redir"
        cls.remove_from_script(NAT_START_SCRIPT_PATH, comment)
        elogger.info(f"✔ 从启动脚本里移除 iptables 规则添加命令：{NAT_START_SCRIPT_PATH}")

        # 删除 ipset 的 chn 表
        ipset_cmd = "ipset destroy chn"
        try:
            subprocess.check_output(ipset_cmd, shell=True, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            if "The set with the given name does not exist" not in str(e.stderr):
                raise e
        else:
            elogger.info(f"✔ 删除 ipset 的 chn 表：{ipset_cmd}")

        # 移除每日更新规则的 cron 定时任务
        cls.remove_renew_cron_job()

        # 从启动脚本里移除 xt_set 模块加载命令
        comment = "# Load xt_set module"
        cls.remove_from_script(SERVICES_START_SCRIPT_PATH, comment)
        elogger.info(f"✔ 从启动脚本里移除 xt_set 模块加载命令：{SERVICES_START_SCRIPT_PATH}")

        # 删除 nvram 中 unblockchn_on 变量
        cls.remove_nvram('unblockchn_on')

        # 重启 dnsmasq
        cls.restart_dnsmasq()

        ologger.info("还原成功")

    @classmethod
    def cmd_create(cls):
        """仅生成 ipset 和 dnsmasq 规则配置文件"""

        # 生成路由器配置文件
        unblock_youku = UnblockYouku()
        cls.create_conf_files(unblock_youku.black_domains)

        ologger.info("生成配置文件成功")

    @classmethod
    def setup_ss_redir(cls):
        """配置 ss-redir"""

        # 读取已有的代理服务器（配置文件）
        confs = cls.load_ss_redir_confs()

        # 列出已有代理服务器（配置文件）
        if confs:
            elogger.info(f"已有 {len(confs)} 个代理服务器：")
            for i, conf_name in enumerate(confs):
                conf = confs[conf_name]
                elogger.info(f"{i + 1}) {conf_name}")
                elogger.info(f"Shadowsocks 服务器地址：{conf['server']}")
                elogger.info(f"Shadowsocks 服务器端口：{conf['server_port']}")
                elogger.info(f"Shadowsocks 密码：{conf['password']}")
                elogger.info(f"Shadowsocks 加密方法：{conf['method']}")

        # 添加新的代理服务器（配置文件）
        while True:
            if confs:
                r = input("是否添加更多代理服务器？[y/N]：") or "n"
                if (not r.lower().startswith('y')) and (not r.lower().startswith('n')):
                    elogger.error(f"✘ 无效输入：{r}")
                    sys.exit(1)
                if r.lower().startswith("n"):
                    break

            conf = SS_REDIR_CONF_TPL.copy()
            if conf['server'] is None:
                conf['server'] = input("Shadowsocks 服务器地址：").strip()
            else:
                print(f"Shadowsocks 服务器地址：{conf['server']}")
            if conf['server_port'] is None:
                conf['server_port'] = int(input("Shadowsocks 服务器端口：").strip())
            else:
                print(f"Shadowsocks 服务器端口：{conf['server_port']}")
            if conf['password'] is None:
                conf['password'] = input("Shadowsocks 密码：").strip()
            else:
                print(f"Shadowsocks 密码：{conf['password']}")
            if conf['method'] is None:
                conf['method'] = input("Shadowsocks 加密方法：").strip()
            else:
                print(f"Shadowsocks 加密方法：{conf['method']}")

            conf_name = input("命名此代理服务器为：") or "CHN"
            if conf_name not in confs:
                confs[conf_name] = conf

            conf_path = os.path.join(SHADOWSOCKS_DIR_PATH, f"{conf_name}.json")
            with open(conf_path, 'w', encoding='utf-8') as f:
                json.dump(conf, f, indent=4)

            elogger.info(f"✔ 保存 ss-redir 配置文件：{conf_path}")

        # 选择代理服务器（配置文件）
        if len(confs) > 1:
            elogger.info("0) 自动选择延迟最低的代理服务器")
            for i, conf_name in enumerate(confs):
                conf = confs[conf_name]
                hostname = conf['server']
                port = conf['server_port']
                elogger.info(f"{i + 1}) {conf_name} [{hostname}:{port}]")
            r = input(f"请选择要使用的代理服务器 [0-{len(confs)}]：") or "0"
            try:
                n = int(r)
            except ValueError:
                elogger.error(f"✘ 无效输入：{r}")
                sys.exit(1)
            if n > len(confs) or n < 0:
                elogger.error(f"✘ 无效输入：{r}")
                sys.exit(1)
            if n == 0:
                # 自动选择延迟最低的代理服务器
                selected_conf_name = cls.auto_select(confs)
            else:
                selected_conf_name = list(confs)[n - 1]
            elogger.info(f"使用 {selected_conf_name} 代理服务器")
        else:
            selected_conf_name = list(confs)[0]

        # 记录选定的代理服务器名（配置文件名）到 nvram 变量
        cls.set_nvram('unblockchn_ss_conf', selected_conf_name)

        # 停止 ss-redir 若已运行
        ss_redir_running = cls.check_ss_redir()
        if ss_redir_running:
            cls.stop_ss_redir()

        # 启动 ss-redir
        cls.start_ss_redir()

        # 保存 ss-redir 启动命令到路由器的 services-start 启动脚本中
        cmd = f'{SS_REDIR_PATH} -c {SHADOWSOCKS_DIR_PATH}/"$(nvram get unblockchn_ss_conf)".json -f {SS_REDIR_PID_PATH}'
        comment = "# ss-redir"
        cls.append_to_script(SERVICES_START_SCRIPT_PATH, comment, cmd)
        elogger.info(f"✔ 保存 ss-redir 启动命令到路由器的 services-start 启动脚本中：{SERVICES_START_SCRIPT_PATH}")

    @classmethod
    def setup_ipset_iptables(cls):
        """配置 ipset 和 iptables"""

        # 加载 xt_set 模块
        xt_set_cmd = "modprobe xt_set"
        subprocess.check_call(xt_set_cmd, shell=True)
        elogger.info(f"✔ 加载 xt_set 模块：{xt_set_cmd}")

        # 保存 xt_set 模块加载命令到路由器的 services-start 启动脚本中
        comment = "# Load xt_set module"
        cls.append_to_script(SERVICES_START_SCRIPT_PATH, comment, xt_set_cmd)
        elogger.info(f"✔ 保存 xt_set 模块加载命令到路由器的 services-start 启动脚本中：{SERVICES_START_SCRIPT_PATH}")

        # 载入 ipset 规则
        ipset_cmd = f"ipset restore < {IPSET_CONF_JFFS_PATH}"
        try:
            subprocess.check_output(ipset_cmd, shell=True, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            if "set with the same name already exists" not in str(e.stderr):
                raise e
        elogger.info(f"✔ 载入 ipset 规则：{ipset_cmd}")

        # 保存 ipset 载入命令到路由器的 nat-start 启动脚本中
        comment = "# Load ipset rules"
        cls.append_to_script(NAT_START_SCRIPT_PATH, comment, ipset_cmd)
        elogger.info(f"✔ 保存 ipset 载入命令到路由器的 nat-start 启动脚本中：{NAT_START_SCRIPT_PATH}")

        # 添加 iptables 规则
        iptables_chn_exists = cls.check_iptables_chn()
        if not iptables_chn_exists:
            cls.add_iptables_chn()
        elogger.info(f"✔ 添加 iptables 规则：{ADD_IPTABLES_CHN_CMD}")

        # 保存 iptables 添加规则命令到路由器的 nat-start 启动脚本中
        comment = "# Redirect chn ipset to ss-redir"
        cmd = f'if [ "$(nvram get unblockchn_on)" = "True" ]; then {ADD_IPTABLES_CHN_CMD}; fi'
        cls.append_to_script(NAT_START_SCRIPT_PATH, comment, cmd)
        elogger.info(f"✔ 保存 iptables 规则添加命令到路由器的 nat-start 启动脚本中：{NAT_START_SCRIPT_PATH}")

    @classmethod
    def create_conf_files(cls, domains):
        """生成路由器 ipset 和 dnsmasq 规则配置文件"""

        # 生成 ipset 和 dnsmasq 规则
        ipset_rules = []
        dnsmasq_rules = []
        if domains:
            for domain in domains:
                if re.match(r"\d+\.\d+\.\d+\.\d+", domain):  # IP
                    rule = f"add chn {domain}"
                    ipset_rules.append(rule)
                else:  # 域名
                    rule = f"ipset=/{domain}/chn"
                    dnsmasq_rules.append(rule)

        # 从模板生成 ipset 规则配置文件 ipset.rules
        cls.create_ipset_conf_file(ipset_rules)

        # 从模板生成 dnsmasq 规则配置文件 dnsmasq.conf.add
        cls.create_dnsmasq_conf_file(dnsmasq_rules)

    @classmethod
    def create_ipset_conf_file(cls, ipset_rules):
        """从模板生成 ipset 规则配置文件 ipset.rules"""
        ipset_tpl_path = os.path.join(CONFIGS_DIR_PATH, "ipset.rules.tpl")
        if os.path.isfile(ipset_tpl_path):
            with open(ipset_tpl_path, 'r', encoding='utf-8') as f:
                ipset_tpl = f.read()
        else:
            ipset_tpl = "{rules}"
            with open(ipset_tpl_path, 'w', encoding='utf-8') as f:
                f.write(ipset_tpl)
            elogger.info("✔ 生成 ipset 默认配置模板文件（configs 目录）：ipset.rules.tpl")

        # 无 ipset 规则 & 无自定义模板内容
        if (not ipset_rules) and (ipset_tpl == "{rules}"):
            return False

        if ipset_rules:
            ipset_rules.insert(0, "create chn hash:ip family inet hashsize 1024 maxelem 65536")
            ipset_rules = "\n".join(ipset_rules)
        else:
            ipset_rules = ""
        ipset_conf = ipset_tpl.format(rules=ipset_rules).strip()

        # 生成包含表创建命令的 ipset 规则配置文件 ipset.rules
        ipset_conf_path = os.path.join(CONFIGS_DIR_PATH, "ipset.rules")
        with open(ipset_conf_path, 'w', encoding='utf-8') as f:
            f.write(ipset_conf)

        # 生成不包含表创建命令的 ipset 规则配置文件 ipset.headless.rules
        lines = ipset_conf.split('\n')
        lines = [line for line in lines if not line.startswith("create ")]
        headless_ipset_conf_path = os.path.join(CONFIGS_DIR_PATH, "ipset.headless.rules")
        with open(headless_ipset_conf_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))

        elogger.info("✔ 生成 ipset 配置文件（configs 目录）：ipset.rules & ipset.headless.rules")
        return True

    @classmethod
    def create_dnsmasq_conf_file(cls, dnsmasq_rules):
        """从模板生成 dnsmasq 规则配置文件 dnsmasq.conf.add"""
        dnsmasq_tpl_path = os.path.join(CONFIGS_DIR_PATH, "dnsmasq.conf.add.tpl")
        if os.path.isfile(dnsmasq_tpl_path):
            with open(dnsmasq_tpl_path, 'r', encoding='utf-8') as f:
                dnsmasq_tpl = f.read()
        else:
            dnsmasq_tpl = "{rules}"
            with open(dnsmasq_tpl_path, 'w', encoding='utf-8') as f:
                f.write(dnsmasq_tpl)
            elogger.info("✔ 生成 dnsmasq 默认配置模板文件（configs 目录）：dnsmasq.conf.add.tpl")

        # 无 dnsmasq 规则 & 无自定义模板内容
        if (not dnsmasq_rules) and (dnsmasq_tpl == "{rules}"):
            return False

        if dnsmasq_rules:
            dnsmasq_rules = "\n".join(dnsmasq_rules)
            dnsmasq_rules = "# Unblock CHN\n" + dnsmasq_rules
        else:
            dnsmasq_rules = ""
        dnsmasq_conf = dnsmasq_tpl.format(rules=dnsmasq_rules)

        dnsmasq_conf_path = os.path.join(CONFIGS_DIR_PATH, "dnsmasq.conf.add")
        with open(dnsmasq_conf_path, 'w', encoding='utf-8') as f:
            f.write(dnsmasq_conf)

        elogger.info("✔ 生成 dnsmasq 配置文件（configs 目录）：dnsmasq.conf.add")
        return True

    @classmethod
    def cp_ipset_conf_to_jffs(cls):
        """复制 ipset 规则配置文件到 jffs 配置目录"""
        ipset_conf_path = os.path.join(CONFIGS_DIR_PATH, "ipset.rules")
        if os.path.isfile(ipset_conf_path):
            shutil.copy2(ipset_conf_path, IPSET_CONF_JFFS_PATH)
            elogger.info(f"✔ 复制：{ipset_conf_path} -> {IPSET_CONF_JFFS_PATH}")
            return True
        return False

    @classmethod
    def cp_dnsmasq_conf_to_jffs(cls):
        """复制 dnsmasq 规则配置文件到 jffs 配置目录"""
        dnsmasq_conf_path = os.path.join(CONFIGS_DIR_PATH, "dnsmasq.conf.add")
        if os.path.isfile(dnsmasq_conf_path):
            shutil.copy2(dnsmasq_conf_path, DNSMASQ_CONF_JFFS_PATH)
            elogger.info(f"✔ 复制：{dnsmasq_conf_path} -> {DNSMASQ_CONF_JFFS_PATH}")
            return True
        return False

    @classmethod
    def add_iptables_chn(cls):
        """iptables 添加 chn ipset 规则"""
        subprocess.check_call(ADD_IPTABLES_CHN_CMD, shell=True)

    @classmethod
    def delete_iptables_chn(cls):
        """iptables 删除 chn ipset 规则"""
        subprocess.check_call(DELETE_IPTABLES_CHN_CMD, shell=True)

    @classmethod
    def check_iptables_chn(cls):
        """检查 iptables 是否有 chn ipset 规则"""
        returncode = subprocess.call(
            CHECK_IPTABLES_CHN_CMD, shell=True, stderr=subprocess.DEVNULL)
        return returncode == 0

    @classmethod
    def add_renew_cron_job(cls):
        """添加每日更新规则的 cron 定时任务"""
        unblockchn_path = os.path.realpath(__file__)
        renew_cmd = f"0 {RENEW_TIME} * * * {PYTHON3_PATH} {unblockchn_path} router renew"
        cron_cmd = f'cru a unblockchn_renew "{renew_cmd}"'
        try:
            subprocess.check_call(cron_cmd, shell=True)
        except subprocess.CalledProcessError as e:
            elogger.exception(e)
            elogger.warning(f"✘ 无法添加每日更新规则的定时任务，你需要手动添加以下条目到 crontab 中：\n{renew_cmd}")
            return
        else:
            elogger.info(f"✔ 定时每日 {RENEW_TIME} 点更新规则：{cron_cmd}")

        # 保存以上定时命令到路由器的 services-start 启动脚本中
        comment = "# unblockchn_renew cron job"
        cls.append_to_script(SERVICES_START_SCRIPT_PATH, comment, cron_cmd)
        elogger.info(f"✔ 保存定时更新规则命令到路由器的 services-start 启动脚本中：{SERVICES_START_SCRIPT_PATH}")

    @classmethod
    def remove_renew_cron_job(cls):
        """移除每日更新规则的 cron 定时任务"""
        cmd = "cru d unblockchn_renew"
        subprocess.check_call(cmd, shell=True)
        elogger.info(f"✔ 删除每日更新规则的 cron 定时任务：{cmd}")

        # 从启动脚本里移除定时命令
        comment = "# unblockchn_renew cron job"
        cls.remove_from_script(SERVICES_START_SCRIPT_PATH, comment)
        elogger.info(f"✔ 从启动脚本里移除定时命令：{SERVICES_START_SCRIPT_PATH}")

    @classmethod
    def append_to_script(cls, script_path, comment, cmd):
        """添加命令到脚本"""
        if os.path.isfile(script_path):
            with open(script_path, 'r', encoding='utf-8') as f:
                scpt = f.read()
        else:
            scpt = "#!/bin/sh\n"
        if comment not in scpt:
            scpt += "\n" + comment + "\n" + cmd + "\n"
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(scpt)
        cmd = f'chmod a+rx "{script_path}"'
        subprocess.check_call(cmd, shell=True)

    @classmethod
    def remove_from_script(cls, script_path, comment):
        """从脚本中移除命令"""
        if not os.path.isfile(script_path):
            return
        with open(script_path, 'r', encoding='utf-8') as f:
            scpt = f.read()
        pattern = r"\n" + comment + r"\n.+\n?"
        scpt = re.sub(pattern, "", scpt)
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(scpt)

    @classmethod
    def load_ss_redir_confs(cls):
        """读取 ss-redir 代理服务器（配置文件）"""
        confs = OrderedDict()
        for name in os.listdir(SHADOWSOCKS_DIR_PATH):
            if not name.endswith(".json"):
                continue
            if name.startswith("._"):
                continue
            conf_name = name[:-5]
            conf_path = os.path.join(SHADOWSOCKS_DIR_PATH, name)
            with open(conf_path, 'r', encoding='utf-8') as f:
                conf = json.load(f)
            confs[conf_name] = conf
        return confs

    @classmethod
    def auto_select(cls, confs):
        """自动选择延迟最低的代理服务器"""
        working_confs = []
        for i, conf_name in enumerate(confs):
            conf = confs[conf_name]
            hostname = conf['server']
            port = conf['server_port']
            try:
                # 测试连接延迟
                latency = cls.get_connection_time(hostname, port, times=3, timeout=5)
                conf['latency'] = latency
                result = f"{latency * 1000:.0f} ms"
                working_confs.append({'name': conf_name, 'latency': latency})
            except socket.gaierror:
                result = "无效地址"
            except socket.timeout:
                result = "连接超时"
            except ConnectionError:
                result = "连接失败"
            elogger.info(f"{i + 1}) {conf_name} [{hostname}:{port}]: {result}")
        if not working_confs:
            ologger.error("✘ 代理服务器都无法连接")
            sys.exit(1)
        fastest_conf = min(working_confs, key=lambda x: x['latency'])
        fastest_conf_name = min(confs, key=lambda x: confs[x]['latency'])
        return fastest_conf_name

    @classmethod
    def get_connection_time(cls, hostname, port, times=3, timeout=5):
        """测试连接延迟"""
        ip = socket.gethostbyname(hostname)
        start = time.perf_counter()
        for _ in range(times):
            socket.create_connection((ip, port), timeout)
        end = time.perf_counter()
        duration = end - start
        return duration / times

    @classmethod
    def start_ss_redir(cls):
        """启动 ss-redir"""
        conf_name = cls.get_nvram("unblockchn_ss_conf")
        conf_path = os.path.join(SHADOWSOCKS_DIR_PATH, f"{conf_name}.json")
        cmd = f"{SS_REDIR_PATH} -c {conf_path} -f {SS_REDIR_PID_PATH}"
        subprocess.call(cmd, shell=True)
        time.sleep(1)
        is_running = cls.check_ss_redir()
        if is_running:
            elogger.info(f"✔ 启动 ss-redir（{conf_name} 代理服务器）：{cmd}")
        else:
            ologger.error("✘ 无法启动 ss-redir")
            elogger.error(f"请手动运行以下命令查看错误信息：\n{cmd}")
            sys.exit(1)

    @classmethod
    def stop_ss_redir(cls):
        """停止 ss-redir"""
        with open(SS_REDIR_PID_PATH, 'r', encoding='utf-8') as f:
            pid = f.read()
        cmd = f"kill {pid}"
        subprocess.check_call(cmd, shell=True)
        elogger.info(f"✔ 停止 ss-redir：{cmd}")

    @classmethod
    def check_ss_redir(cls):
        """检查 ss-redir 是否运行中"""
        if not os.path.isfile(SS_REDIR_PID_PATH):
            return False
        with open(SS_REDIR_PID_PATH, 'r', encoding='utf-8') as f:
            pid = f.read()
        return os.path.exists(f"/proc/{pid}")

    @classmethod
    def check_setup(cls):
        """检查路由器是否配置过"""
        chn_ipset_exists = cls.check_chn_ipset()
        if not chn_ipset_exists:
            ologger.error("✘ 路由器未正确配置，请先运行以下命令进行配置：\npython3 unblockchn.py router setup")
            sys.exit(1)

    @classmethod
    def check_chn_ipset(cls):
        """检查 ipset 是否有 chn 表"""
        cmd = "ipset list chn"
        returncode = subprocess.call(
            cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return returncode == 0

    @classmethod
    def check_ipset_iptables(cls):
        """检查 iptables 和 ipset 命令是否存在"""
        iptables_exists = cls.check_command('iptables')
        ipset_exists = cls.check_command('ipset')
        if not (iptables_exists and ipset_exists):
            d = {'iptables': iptables_exists, 'ipset': ipset_exists}
            missing = [k for k in d if not d[k]]
            ologger.error(f"✘ 运行环境不支持 {' 和 '.join(missing)} 命令")
            sys.exit(1)

    @classmethod
    def check_command(cls, command):
        """检查命令是否存在"""
        returncode = subprocess.call(
            ["which", command],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if returncode == 0:
            return True
        else:
            return False

    @classmethod
    def flush_ipset(cls):
        """清空 chn 和其它自定义的 ipset 表"""
        ipset_names = cls.get_ipset_names()

        for ipset_name in ipset_names:
            cmd = f"ipset flush {ipset_name}"
            subprocess.check_call(cmd, shell=True)
            elogger.info(f"✔ 清空 ipset 的 {ipset_name} 表：{cmd}")

    @classmethod
    def destroy_ipset(cls):
        """删除 chn 和其它自定义的 ipset 表"""
        ipset_names = cls.get_ipset_names()

        for ipset_name in ipset_names:
            cmd = f"ipset destroy {ipset_name}"
            try:
                subprocess.check_output(cmd, shell=True, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                if "The set with the given name does not exist" not in str(e.stderr):
                    raise e
            else:
                elogger.info(f"✔ 删除 ipset 的 {ipset_name} 表：{cmd}")

    @classmethod
    def get_ipset_names(cls):
        ipset_names = {'chn'}
        ipset_conf_path = os.path.join(CONFIGS_DIR_PATH, "ipset.rules")
        if not os.path.isfile(ipset_conf_path):
            return ipset_names
        with open(ipset_conf_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.startswith("create "):
                    continue
                ipset_name = line.split(' ')[1]
                ipset_names.add(ipset_name)
        return ipset_names

    @classmethod
    def restart_dnsmasq(cls):
        """重启 dnsmasq"""
        subprocess.check_call(DNSMASQ_RESTART_CMD, shell=True, stdout=subprocess.DEVNULL)
        elogger.info(f"✔ 重启 dnsmasq：{DNSMASQ_RESTART_CMD}")

    @classmethod
    def set_nvram(cls, name, value):
        """设置 nvram 值"""
        cmd = f"nvram set {name}={value}"
        subprocess.check_call(cmd, shell=True)
        cmd = "nvram commit"
        subprocess.check_call(cmd, shell=True)

    @classmethod
    def get_nvram(cls, name):
        """获取 nvram 值"""
        cmd = f"nvram get {name}"
        output = subprocess.check_output(cmd, shell=True)
        return output.strip().decode('utf-8')

    @classmethod
    def remove_nvram(cls, name):
        """删除 nvram 值"""
        cmd = f"nvram unset {name}"
        subprocess.check_call(cmd, shell=True)
        cmd = "nvram commit"
        subprocess.check_call(cmd, shell=True)


class Surge(object):

    @classmethod
    def execute(cls, raw_args):
        """python3 unblockchn.py surge [-h] [-d DST]

Unblock CHN

生成 Surge 配置文件
"""
        parser = argparse.ArgumentParser(usage=cls.execute.__doc__)
        parser.add_argument('-u', '--url', action='store_true', help="生成基于 URL 正则表达式的规则（默认基于域名）")
        parser.add_argument('-r', '--ruleset', action='store_true', help="生成 Surge ruleset 文件")
        parser.add_argument('-d', '--dst', help="保存生成的文件到此目录")
        args = parser.parse_args(raw_args)

        unblock_youku = UnblockYouku()

        if args.url:  # 基于 URL 生成规则
            black_urls = unblock_youku.black_urls
            white_urls = unblock_youku.white_urls
            rules = cls.url_rules(black_urls, white_urls)
        else:  # 基于域名生成规则
            black_domains = unblock_youku.black_domains
            rules = cls.domain_rules(black_domains)

        if args.ruleset:  # 生成 Surge ruleset 文件
            cls.create_ruleset_file(rules)
        else:  # 生成 Surge 规则配置文件
            has_conf = cls.create_conf_files(rules)
            if not has_conf:
                elogger.error("✘ 目录下不存在后缀为 .conf.tpl 的 Surge 配置模板文件（忽略 sample_surge.conf.tpl）")
                sys.exit(1)

        # 保存生成的文件到 args.dst
        if args.dst:
            if not os.path.exists(args.dst):
                elogger.error(f"✘ 目的地文件夹不存在：{args.dst}")
                sys.exit(1)
            if not os.path.isdir(args.dst):
                elogger.error(f"✘ 目的地路径非文件夹：{args.dst}")
                sys.exit(1)
            if args.ruleset:  # 复制 Surge ruleset 文件
                cls.cp_ruleset_file(args.dst)
            else:  # 复制 Surge 规则配置文件
                cls.cp_conf_files(args.dst)

    @classmethod
    def url_rules(cls, black_urls, white_urls):
        """生成基于 URL 正则表达式的规则"""
        black_rules = cls.urls_to_rules(black_urls)
        white_urls = cls.urls_to_rules(white_urls)
        rules = {
            'black': black_rules,
            'white': white_urls
        }
        return rules

    @classmethod
    def urls_to_rules(cls, urls):
        """将 urls 转换为 Surge 规则"""
        rules = []
        for url in urls:
            if url.startswith('http://'):  # http
                reg_url = re.escape(url)
                reg_url = reg_url.replace("\\*", ".*")
                reg_url = "^" + reg_url
                rule = f"URL-REGEX,{reg_url}"
            else:  # https
                domain = urlsplit(url).hostname
                if domain.startswith("*."):  # DOMAIN-SUFFIX
                    domain = domain.replace("*.", "", 1)
                    rule = f"AND,((DOMAIN-SUFFIX,{domain}),(DEST-PORT,443))"
                else:  # DOMAIN
                    rule = f"AND,((DOMAIN,{domain}),(DEST-PORT,443))"
            rules.append(rule)
        return rules

    @classmethod
    def domain_rules(cls, black_domains):
        """生成基于域名的规则"""
        black_rules = []
        for domain in black_domains:
            if domain.startswith("*."):  # DOMAIN-SUFFIX
                domain = domain.replace("*.", "", 1)
                rule = f"DOMAIN-SUFFIX,{domain}"
            else:  # DOMAIN
                rule = f"DOMAIN,{domain}"
            black_rules.append(rule)
        rules = {
            'black': black_rules,
            'white': []
        }
        return rules

    @classmethod
    def create_conf_files(cls, rules):
        """从模板生成 Surge 规则配置文件"""
        white_rules = rules['white']
        white_rules = [rule + "," + "DIRECT" for rule in white_rules]
        black_rules = rules['black']
        black_rules = [rule + "," + SURGE_PROXY_GROUP_NAME for rule in black_rules]

        rules = "\n".join(white_rules + black_rules)

        has_conf = False

        for name in os.listdir(SURGE_DIR_PATH):
            if not name.endswith(".conf.tpl"):
                continue
            if name.startswith("._"):
                continue
            if name == "sample_surge.conf.tpl":  # 跳过样例模板
                continue
            tpl_path = os.path.join(SURGE_DIR_PATH, name)
            with open(tpl_path, 'r', encoding='utf-8') as f:
                tpl = f.read()
            conf_name = name[:-4]
            conf_path = os.path.join(SURGE_DIR_PATH, conf_name)
            conf = tpl.format(rules=rules)
            with open(conf_path, 'w', encoding='utf-8') as f:
                f.write(conf)
            has_conf = True
            elogger.info(f"✔ 生成 Surge 配置文件（surge 目录）：{conf_name}")

        return has_conf

    @classmethod
    def create_ruleset_file(cls, rules):
        """生成 Surge ruleset 文件"""
        rules = "\n".join(rules['black'])
        ruleset_file_path = os.path.join(SURGE_DIR_PATH, "unblockchn.surge.ruleset")
        with open(ruleset_file_path, 'w', encoding='utf-8') as f:
            f.write(rules)
        elogger.info("✔ 生成 Surge ruleset 文件（surge 目录）：unblockchn.surge.ruleset")

    @classmethod
    def cp_conf_files(cls, dst):
        """复制目录下的 Surge 配置文件到 dst 文件夹"""
        for name in os.listdir(SURGE_DIR_PATH):
            if not name.endswith('.conf'):
                continue
            if name.startswith("._"):
                continue
            src_path = os.path.join(SURGE_DIR_PATH, name)
            dst_path = os.path.join(dst, name)
            shutil.copy2(src_path, dst_path)
            elogger.info(f"✔ 保存 Surge 配置文件到：{dst_path}")

    @classmethod
    def cp_ruleset_file(cls, dst):
        """复制目录下的 Surge ruleset 文件到 dst 文件夹"""
        name = "unblockchn.surge.ruleset"
        src_path = os.path.join(SURGE_DIR_PATH, name)
        dst_path = os.path.join(dst, name)
        shutil.copy2(src_path, dst_path)
        elogger.info(f"✔ 保存 Surge ruleset 文件到：{dst_path}")


class UnblockYouku(object):

    def __init__(self):
        super(UnblockYouku, self).__init__()
        self.source = requests.get(UNBLOCK_YOUKU_URLSJS_URL).text
        self._black_urls = None
        self._white_urls = None
        self._black_domains = None
        self._white_domains = None

    @property
    def black_urls(self):
        """URLs 黑名单"""
        if self._black_urls is not None:
            return self._black_urls

        header_urls = self.extract('header_urls')
        redirect_urls = self.extract('redirect_urls')
        chrome_proxy_urls = self.extract('chrome_proxy_urls')
        pac_proxy_urls = self.extract('pac_proxy_urls')

        self._black_urls = header_urls + redirect_urls + chrome_proxy_urls + pac_proxy_urls
        self._black_urls = list(set(self._black_urls))
        self._black_urls.sort()

        return self._black_urls

    @property
    def white_urls(self):
        """URLs 白名单"""
        if self._white_urls is not None:
            return self._white_urls

        chrome_proxy_bypass_urls = self.extract('chrome_proxy_bypass_urls')
        pac_proxy_bypass_urls = self.extract('pac_proxy_bypass_urls')

        self._white_urls = chrome_proxy_bypass_urls + pac_proxy_bypass_urls
        self._white_urls = list(set(self._white_urls))
        self._white_urls.sort()

        return self._white_urls

    @property
    def black_domains(self):
        """域名黑名单"""
        if self._black_domains is not None:
            return self._black_domains

        self._black_domains = []
        for url in self.black_urls:
            domain = urlsplit(url).hostname
            self._black_domains.append(domain)

        self._black_domains = list(set(self._black_domains))
        self._black_domains.sort(key=lambda s: s[::-1], reverse=True)

        return self._black_domains

    @property
    def white_domains(self):
        """域名白名单"""
        if self._white_domains is not None:
            return self._white_domains

        self._white_domains = []
        for url in self.white_urls:
            domain = urlsplit(url).hostname
            self._white_domains.append(domain)

        self._white_domains = list(set(self._white_domains))
        self._white_domains.sort(key=lambda s: s[::-1], reverse=True)

        return self._white_domains

    def extract(self, name):
        """从 Unblock Youku 的 urls.js 中提取指定的 URL 列表"""
        pattern = f"unblock_youku\\.{name}\\s*=.+?(\\[.+?\\])"
        match = re.search(pattern, self.source, re.DOTALL)
        if not match:
            elogger.error(f"✘ 从 Unblock Youku 提取 {name} 规则失败")
            sys.exit(1)
        s = match.group(1)
        s = s.replace("'", '"')  # 替换单引号为双引号
        s = re.sub(r"(?<!:)//.+", "", s)  # 去除注释
        s = re.sub(r",\s*\]", "\n]", s)  # 去除跟在最后一个元素后面的逗号
        urls = json.loads(s)
        return urls


class Acl(object):

    @classmethod
    def execute(cls, raw_args):
        """python3 unblockchn.py acl [-h] [-d DST]

Unblock CHN

生成 ACL 文件
"""
        parser = argparse.ArgumentParser(usage=cls.execute.__doc__)
        parser.add_argument('-p', '--pac', action='store_true', help="生成 PAC 文件")
        parser.add_argument('-a', '--acl', action='store_true', help="生成 ACL 文件")
        parser.add_argument('-d', '--dst', help="保存生成的文件到此目录")
        args = parser.parse_args(raw_args)

        unblock_youku = UnblockYouku()

        if args.acl:
            check = True
        else:
            check = False
        # 生成 ruleset 文件
        black_domains = unblock_youku.black_domains
        rules = cls.domain_rules(black_domains, check)
        cls.create_ruleset_file(rules, check)
        cls.create_pac_file(check)


        # 保存生成的文件到 args.dst
        if args.dst:
            # 复制 ACL ruleset 文件
            cls.cp_ruleset_file(args.dst, check)

    @classmethod
    def domain_rules(cls, black_domains, check):
        """生成基于域名的规则"""
        black_rules = []
        if check:
            for domain in black_domains:
                if domain.startswith("*."):  # DOMAIN-SUFFIX
                    domain = domain.replace("*.", "", 1)
                    domain = domain.replace(".", "\.")
                    rule = f"(^|\.){domain}$"
                else:  # DOMAIN
                    if cls.is_ipv4(domain):
                        rule = f"{domain}"  
                    else:
                        domain = domain.replace(".", "\.")
                        rule = f"(^|\.){domain}$"
                black_rules.append(rule)
        else:
            for domain in black_domains:
                if domain.startswith("*."):  # DOMAIN-SUFFIX
                    domain = domain.replace("*.", "", 1)
                    rule = f"\t\"||{domain}\","
                else:  # DOMAIN
                    rule = f"\t\"||{domain}\","
                black_rules.append(rule)
        rules = {
            'black': black_rules,
            'white': []
        }
        return rules

    
    @classmethod
    def create_ruleset_file(cls, rules, check):
        """生成 ACL ruleset 文件"""
        rules = "\n".join(rules['black'])
        if check:
            ruleset_file_path = os.path.join(ACL_DIR_PATH, "unblockchn.acl.ruleset")
            with open(ruleset_file_path, 'w', encoding='utf-8') as f:
                f.write(rules)
            elogger.info("✔ 生成 ACL ruleset 文件（acl 目录）：unblockchn.acl.ruleset")
        else:
            ruleset_file_path = os.path.join(ACL_DIR_PATH, "unblockchn.pac.ruleset")
            with open(ruleset_file_path, 'w', encoding='utf-8') as f:
                f.write(rules)
            elogger.info("✔ 生成 PAC ruleset 文件（acl 目录）：unblockchn.pac.ruleset")
                          
    @classmethod
    def create_pac_file(cls, check):
        if check:
            """生成 ACL ruleset 文件"""
            filenames = ['acl_head.txt', 'unblockchn.acl.ruleset', 'acl_foot.txt']
            ruleset_file_path = os.path.join(ACL_DIR_PATH, "china.acl")
        else:
            """生成 PAC ruleset 文件"""
            filenames = ['pac_head.txt', 'unblockchn.pac.ruleset', 'pac_foot.txt']
            ruleset_file_path = os.path.join(ACL_DIR_PATH, "pac.txt")                          
        with open(ruleset_file_path, 'w', encoding='utf-8') as f:
            for fname in filenames:
                with open("acl/"+fname) as infile:
                    for line in infile:
                        f.write(line)
        if check:
            elogger.info("✔ 生成 ACL 文件（acl 目录）：china.acl")
        else:
            elogger.info("✔ 生成 PAC 文件（acl 目录）：pac.txt")                          
        
    @classmethod
    def is_ipv4(cls, ip):
        match = re.match("^(\d{0,3})\.(\d{0,3})\.(\d{0,3})\.(\d{0,3})$", ip)
        if not match:
            return False
        quad = []
        for number in match.groups():
            quad.append(int(number))
        if quad[0] < 1:
            return False
        for number in quad:
            if number > 255 or number < 0:
                return False
        return True

    @classmethod
    def cp_ruleset_file(cls, dst, check):
        """复制目录下的 ACL ruleset 文件到 dst 文件夹"""
        if check:
            name = "china.acl"
        else:
            name = "pac.txt"
        src_path = os.path.join(ACL_DIR_PATH, name)
        dst_path = os.path.join(dst, name)
        shutil.copy2(src_path, dst_path)
        if check:
            elogger.info(f"✔ 保存 ACL 文件到：{dst_path}")
        else:
            elogger.info(f"✔ 保存 PAC 文件到：{dst_path}")
        


class UnblockYouku(object):

    def __init__(self):
        super(UnblockYouku, self).__init__()
        self.source = requests.get(UNBLOCK_YOUKU_URLSJS_URL).text
        self._black_urls = None
        self._white_urls = None
        self._black_domains = None
        self._white_domains = None

    @property
    def black_urls(self):
        """URLs 黑名单"""
        if self._black_urls is not None:
            return self._black_urls

        header_urls = self.extract('header_urls')
        redirect_urls = self.extract('redirect_urls')
        chrome_proxy_urls = self.extract('chrome_proxy_urls')
        pac_proxy_urls = self.extract('pac_proxy_urls')

        self._black_urls = header_urls + redirect_urls + chrome_proxy_urls + pac_proxy_urls
        self._black_urls = list(set(self._black_urls))
        self._black_urls.sort()

        return self._black_urls

    @property
    def white_urls(self):
        """URLs 白名单"""
        if self._white_urls is not None:
            return self._white_urls

        chrome_proxy_bypass_urls = self.extract('chrome_proxy_bypass_urls')
        pac_proxy_bypass_urls = self.extract('pac_proxy_bypass_urls')

        self._white_urls = chrome_proxy_bypass_urls + pac_proxy_bypass_urls
        self._white_urls = list(set(self._white_urls))
        self._white_urls.sort()

        return self._white_urls

    @property
    def black_domains(self):
        """域名黑名单"""
        if self._black_domains is not None:
            return self._black_domains

        self._black_domains = []
        for url in self.black_urls:
            domain = urlsplit(url).hostname
            self._black_domains.append(domain)

        self._black_domains = list(set(self._black_domains))
        self._black_domains.sort(key=lambda s: s[::-1], reverse=True)

        return self._black_domains

    @property
    def white_domains(self):
        """域名白名单"""
        if self._white_domains is not None:
            return self._white_domains

        self._white_domains = []
        for url in self.white_urls:
            domain = urlsplit(url).hostname
            self._white_domains.append(domain)

        self._white_domains = list(set(self._white_domains))
        self._white_domains.sort(key=lambda s: s[::-1], reverse=True)

        return self._white_domains

    def extract(self, name):
        """从 Unblock Youku 的 urls.js 中提取指定的 URL 列表"""
        pattern = f"unblock_youku\\.{name}\\s*=.+?(\\[.+?\\])"
        match = re.search(pattern, self.source, re.DOTALL)
        if not match:
            elogger.error(f"✘ 从 Unblock Youku 提取 {name} 规则失败")
            sys.exit(1)
        s = match.group(1)
        s = s.replace("'", '"')  # 替换单引号为双引号
        s = re.sub(r"(?<!:)//.+", "", s)  # 去除注释
        s = re.sub(r",\s*\]", "\n]", s)  # 去除跟在最后一个元素后面的逗号
        urls = json.loads(s)
        return urls


def organize():
    """整理一些文件到相应的子目录中（为了向后兼容）"""
    ensure_dir(CONFIGS_DIR_PATH)
    ensure_dir(SURGE_DIR_PATH)
    ensure_dir(SHADOWSOCKS_DIR_PATH)
    config_filenames = [
        "ipset.rules", "ipset.headless.rules", "ipset.rules.tpl",
        "dnsmasq.conf.add", "dnsmasq.conf.add.tpl",
    ]
    shadowsocks_filenames = [
        "ss-redir.json",
        "ss-redir.pid",
    ]
    for name in os.listdir(DIR_PATH):
        if name in config_filenames:
            old_path = os.path.join(DIR_PATH, name)
            new_path = os.path.join(CONFIGS_DIR_PATH, name)
            shutil.move(old_path, new_path)
            continue
        if name.endswith(".conf") or name.endswith(".conf.tpl") or name.endswith(".ruleset"):
            old_path = os.path.join(DIR_PATH, name)
            new_path = os.path.join(SURGE_DIR_PATH, name)
            shutil.move(old_path, new_path)
            continue
        if name in shadowsocks_filenames:
            old_path = os.path.join(DIR_PATH, name)
            new_path = os.path.join(SHADOWSOCKS_DIR_PATH, name)
            shutil.copy2(old_path, new_path)
            continue


def ensure_dir(dir_path):
    """若 dir_path 目录不存在则创建它"""
    if not os.path.isdir(dir_path):
        try:
            os.makedirs(dir_path)
        except OSError:
            pass


def init_logging():
    """日志初始化"""

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.NOTSET)

    # 输出日志到文件
    log_file_path = os.path.join(DIR_PATH, "unblockchn.log")
    formatter = logging.Formatter(
        "%(asctime)s ~ %(levelname)-8s - "
        "%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logfile = logging.handlers.RotatingFileHandler(
        log_file_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=1
    )
    logfile.setFormatter(formatter)
    logfile.setLevel(logging.DEBUG)
    root_logger.addHandler(logfile)

    # 输出日志到控制台
    formatter = logging.Formatter("%(message)s")
    # stderr logger
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.setLevel(logging.INFO)
    elogger.addHandler(console)
    # stdout logger
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(logging.INFO)
    ologger.addHandler(console)

    # 设置 requests 和 urllib3 日志级别
    requests_logger = logging.getLogger("requests")
    requests_logger.setLevel(logging.WARNING)
    urllib3_logger = logging.getLogger('urllib3')
    urllib3_logger.setLevel(logging.WARNING)


if __name__ == '__main__':
    try:
        init_logging()
        main()
    except Exception as error:
        elogger.exception(error)
