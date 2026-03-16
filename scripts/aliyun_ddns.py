#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import requests
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.acs_exception.exceptions import ClientException, ServerException
from aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest import DescribeDomainRecordsRequest
from aliyunsdkalidns.request.v20150109.UpdateDomainRecordRequest import UpdateDomainRecordRequest
from aliyunsdkalidns.request.v20150109.AddDomainRecordRequest import AddDomainRecordRequest

# ================= 配置区域 =================
# 建议通过环境变量设置，或者直接在此处填写
ACCESS_KEY_ID = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID', '你的AccessKeyID')
ACCESS_KEY_SECRET = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET', '你的AccessKeySecret')
DOMAIN_NAME = 'yoloworld.site'  # 你的主域名
SUB_DOMAIN = 'www'         # 你的子域名，例如 home.example.com 则填 home
# ===========================================

def get_public_ip():
    """获取本机公网 IP"""
    urls = [
        'https://myip.ipip.net/',
        'https://api.ipify.org?format=json',
        'https://ifconfig.me/all.json',
        'https://ipinfo.io/json'
    ]
    for url in urls:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # 不同 API 返回结构略有不同
                ip = data.get('ip') or data.get('ip_addr') or data.get('query')
                if ip:
                    return ip
        except Exception as e:
            print(f"尝试从 {url} 获取 IP 失败: {e}")
            continue
    return None

def update_aliyun_dns(current_ip):
    """更新阿里云 DNS 记录"""
    client = AcsClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, 'cn-hangzhou')

    # 1. 查询现有的解析记录
    request = DescribeDomainRecordsRequest()
    request.set_DomainName(DOMAIN_NAME)
    request.set_RRKeyWord(SUB_DOMAIN)
    request.set_TypeKeyWord('A')
    
    try:
        response = client.do_action_with_exception(request)
        res_data = json.loads(response)
        records = res_data.get('DomainRecords', {}).get('Record', [])
        
        target_record = None
        for record in records:
            if record.get('RR') == SUB_DOMAIN:
                target_record = record
                break
        
        if target_record:
            record_id = target_record.get('RecordId')
            old_ip = target_record.get('Value')
            
            if old_ip == current_ip:
                print(f"IP 未发生变化 ({current_ip})，无需更新。")
                return True
            
            # 2. 更新记录
            print(f"检测到 IP 变化: {old_ip} -> {current_ip}，正在更新...")
            update_request = UpdateDomainRecordRequest()
            update_request.set_RecordId(record_id)
            update_request.set_RR(SUB_DOMAIN)
            update_request.set_Type('A')
            update_request.set_Value(current_ip)
            
            client.do_action_with_exception(update_request)
            print("更新成功！")
        else:
            # 3. 如果记录不存在，则新增
            print(f"未找到子域名 {SUB_DOMAIN} 的解析记录，正在新增...")
            add_request = AddDomainRecordRequest()
            add_request.set_DomainName(DOMAIN_NAME)
            add_request.set_RR(SUB_DOMAIN)
            add_request.set_Type('A')
            add_request.set_Value(current_ip)
            
            client.do_action_with_exception(add_request)
            print("新增成功！")
            
        return True
    except (ClientException, ServerException) as e:
        print(f"阿里云 API 调用失败: {e}")
        return False
    except Exception as e:
        print(f"发生未知错误: {e}")
        return False

if __name__ == '__main__':
    if ACCESS_KEY_ID == '你的AccessKeyID' or ACCESS_KEY_SECRET == '你的AccessKeySecret':
        print("错误: 请先配置脚本中的 ACCESS_KEY_ID 和 ACCESS_KEY_SECRET。")
        sys.exit(1)

    print("正在获取本机公网 IP...")
    ip = get_public_ip()
    if ip:
        print(f"当前公网 IP: {ip}")
        update_aliyun_dns(ip)
    else:
        print("无法获取公网 IP，请检查网络连接。")
