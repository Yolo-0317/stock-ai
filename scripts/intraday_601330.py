#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, time, requests

CODE, SECID = "601330", "1.601330"
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def q():  # 行情
    r = requests.get("https://push2.eastmoney.com/api/qt/stock/get",
        params={"secid": SECID, "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f170", "_": int(time.time()*1000)}, headers=H)
    data = r.json().get("data") or {}
    if data:
        print("行情:", data.get("f58"), "最新价:", data.get("f43",0)/100, "涨跌幅:", data.get("f170",0)/100, "%")
        print("最高:", data.get("f44",0)/100, "最低:", data.get("f45",0)/100, "今开:", data.get("f46",0)/100, "昨收:", data.get("f60",0)/100)

def k():  # K线
    r = requests.get("https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={"secid": SECID, "klt": 101, "fqt": 1, "lmt": 60, "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61", "_": int(time.time()*1000)}, headers=H)
    data = r.json().get("data") or {}
    kl = data.get("klines", [])
    if kl:
        closes = [float(k.split(",")[2]) for k in kl[-20:]]
        ma5 = sum(closes[-5:])/5
        ma10 = sum(closes[-10:])/10
        ma20 = sum(closes[-20:])/20
        print("MA5:", round(ma5,2), "MA10:", round(ma10,2), "MA20:", round(ma20,2))
        print("近期支撑:", min(closes[-10:]), "近期压力:", max(closes[-10:]))

def f():  # 资金流
    r = requests.get("https://push2.eastmoney.com/api/qt/stock/fflow/kline/get",
        params={"secid": SECID, "lmt": 1, "klt": 101, "fields2": "f51,f52,f53,f54,f55,f56,f57", "_": int(time.time()*1000)}, headers=H)
    data = r.json().get("data") or {}
    kk = data.get("klines", [])
    if kk:
        p = kk[-1].split(",")
        print("主力净流入:", float(p[1])/10000 if p[1]!="-" else "N/A", "万 占比:", p[2] if len(p)>2 else "N/A", "%")

print("=== 601330 五维数据抓取 ===")
q()
k()
f()
