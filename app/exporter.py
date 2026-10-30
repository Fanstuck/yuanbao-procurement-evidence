from __future__ import annotations

import csv
from html import escape as e
import io
import json

LABELS={'verified':'金额核对通过','pending':'待复核','excluded':'不纳入','duplicate':'重复记录'}


def csv_safe(value):
    text=str(value if value is not None else '')
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) else text


def csv_report(task: dict) -> bytes:
    stream=io.StringIO(newline='')
    writer=csv.writer(stream)
    writer.writerow(['项目名称','项目编号','公告日期','项目成交总额（元）','核验状态','说明','来源网址','抓取时间'])
    for r in task['records']:
        writer.writerow([csv_safe(x) for x in (r['title'],r.get('project_id'),r.get('published_date'),
            r.get('amount_yuan'),LABELS[r['status']],r['reason'],r['url'],r.get('fetched_at'))])
    return ('\ufeff'+stream.getvalue()).encode('utf-8')


def html_report(task: dict) -> str:
    req=task['input']; stats=task['stats']
    mode='实时检索' if req['mode']=='live' else '固定示例回放（2026-10-30 历史样本）'
    rows=''.join(f'<tr><td>{e(r["title"])}</td><td>{e(r.get("project_id",""))}<br>{e(r.get("published_date",""))}</td><td>{e(r.get("amount_yuan") or "—")}</td><td>{LABELS[r["status"]]}<br><small>{e(r["reason"])}</small></td><td><a href="{e(r["url"],quote=True)}">原始公告</a></td></tr>' for r in task['records'])
    evidence=''.join(f'<section><h3>{e(r["title"])}</h3><p>{e(r["url"])}</p><p>抓取时间：{e(r.get("fetched_at",""))}　状态：{LABELS[r["status"]]}</p><blockquote>'+ '<br>'.join(e(x) for x in r.get('evidence',[]))+'</blockquote></section>' for r in task['records'] if r.get('evidence'))
    request_rows=''.join(f'<li>{e(str(r.get("request_id","")))} · {e(str(r.get("version","")))} · {r.get("elapsed_seconds",0)} 秒'+(' · 历史回放' if r.get('replayed') else '')+'</li>' for r in task['requests'])
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>采购历史成交信息查询报告</title><style>
    body{{font:15px/1.8 "Microsoft YaHei",sans-serif;color:#233b34;max-width:1100px;margin:40px auto;padding:20px}}h1{{color:#087252}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;border:1px solid #cbdcd4;text-align:left;vertical-align:top}}th{{background:#edf7f1}}small{{color:#60716a}}section{{margin:28px 0;break-inside:avoid}}blockquote{{background:#f0f6f2;padding:15px;border-left:4px solid #12865f}}a,p{{overflow-wrap:anywhere}}.notice{{padding:16px;background:#fff4dc}}button{{padding:10px 20px}}@media print{{button{{display:none}}body{{margin:0;max-width:none;font-size:11px}}}}
    </style><h1>采购历史成交信息查询报告</h1><p>任务 {e(task['id'])} · {e(mode)} · 创建于 {e(task['created_at'])}</p><p>货物：{e(req['keyword'])}　地区：{e(req['region'])}　时间条件：{e(req['freshness'] or '不限')}　目标：{req['target']} 条</p><p>候选 {stats['candidates']} 条 / 金额核对通过 {stats['verified']} 条 / 待复核 {stats['pending']} 条 / 不纳入 {stats['excluded']} 条 / 重复 {stats['duplicate']} 条</p><div class="notice">{'目标数量已达到。' if stats['verified']>=req['target'] else '有效记录不足，未达到查询目标。'} 所列金额为项目成交总额，不等同于设备单价。金额核对通过仅代表本版规则检查，不代表规格可比、独立双信源确认或采购结论。</div><p><button onclick="window.print()">打印 / 另存为 PDF</button></p><h2>结果明细</h2><table><tr><th>项目</th><th>编号 / 日期</th><th>总额（元）</th><th>状态与原因</th><th>来源</th></tr>{rows}</table><h2>核验依据</h2>{evidence or '<p>本任务尚无可用正文证据。</p>'}<h2>检索追踪</h2><ul>{request_rows}</ul><p>系统版本 1.0.0 · 公开信息查询原型 · AI 辅助开发</p></html>'''


def json_report(task: dict) -> bytes:
    return json.dumps(task,ensure_ascii=False,indent=2).encode('utf-8')
