"""Conservative extraction for public procurement notices; never estimates a unit price."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
from bs4 import BeautifulSoup

CN = timezone(timedelta(hours=8))
NUMBER = r'(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?'
BODY = re.compile(r'(?:中标[（(]成交[）)]金额|成交金额|中标金额)\s*[（(]\s*(万元|元)\s*[）)][^\n：:]{0,20}[：:]\s*[￥¥]?\s*(' + NUMBER + r')(?![0-9.,])')
SUMMARY = re.compile(r'总中标金额\s*[￥¥]?\s*(' + NUMBER + r')\s*(万元|元)')


def money(number: str, unit: str) -> str:
    if not re.fullmatch(NUMBER, number.strip()) or unit not in ('元', '万元'):
        raise ValueError('无法确认金额格式或单位')
    try:
        value = Decimal(number.replace(',', '')) * (Decimal('10000') if unit == '万元' else Decimal('1'))
        return format(value.quantize(Decimal('.01')), '.2f')
    except InvalidOperation as error:
        raise ValueError('金额数值无效') from error


def title_kind(title: str) -> str:
    if any(word in title for word in ('废标', '流标', '终止公告')):
        return 'unsuccessful'
    if any(word in title for word in ('更正', '变更', '澄清', '补遗')):
        return 'related'
    if any(word in title for word in ('成交', '中标', '结果')):
        return 'result_candidate'
    return 'unknown'


def plain_text(html: bytes | str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup(['script', 'style', 'noscript']):
        node.decompose()
    return soup.get_text('\n', strip=True)


def parse_notice(text: str, title: str, freshness: str = '') -> dict:
    out = dict(status='pending', reason='未定位到明确且可交叉核对的成交总额',
               amount_yuan=None, summary_yuan=None, amount_kind='项目成交总额',
               evidence=[], project_id='', published_date='', comparable_unit_price=False)
    kind = title_kind(title)
    out['notice_type'] = kind
    if kind == 'unsuccessful':
        return {**out, 'status': 'excluded', 'reason': '废标、流标或终止公告，不作为成交记录'}
    if kind == 'related':
        return {**out, 'reason': '更正、变更或澄清材料，需关联原公告复核'}
    pid = re.search(r'一[、.]\s*项目编号\s*[：:]?\s*([^\n]+)', text)
    if not pid:
        pid = re.search(r'项目编号\s*[：:]\s*([A-Za-z0-9()（）\-]+)', title)
    if pid:
        out['project_id'] = pid.group(1).strip()[:100]
    date = re.search(r'(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日', text)
    if date:
        try:
            published = datetime(*map(int, date.groups()), tzinfo=CN)
            out['published_date'] = published.strftime('%Y-%m-%d')
            today = datetime.now(CN)
            if published.date() > today.date():
                return {**out, 'reason': '公告日期晚于当前日期，需要复核'}
            floor = None
            if freshness.startswith('y'):
                floor = datetime(today.year-int(freshness[1:])+1, 1, 1, tzinfo=CN)
            elif freshness == 'm6':
                month_number = today.year*12 + today.month-1 - 5
                floor = datetime(month_number//12, month_number%12+1, 1, tzinfo=CN)
            if floor and published < floor:
                return {**out, 'status': 'excluded', 'reason': '原公告日期不在所选相对范围内'}
        except ValueError:
            return {**out, 'reason': '公告日期格式需要人工确认'}
    if not re.search(r'总价中标|总价成交', text):
        return {**out, 'reason': '未确认总价成交口径，可能为费率或其他报价方式'}
    bodies = list(BODY.finditer(text))
    summaries = list(SUMMARY.finditer(text))
    if not bodies:
        return out
    values = {money(m.group(2), m.group(1)) for m in bodies}
    out['evidence'] = [m.group(0) for m in bodies[:3]]
    if len(values) != 1:
        return {**out, 'reason': '正文存在多个金额，需按包件分别核对'}
    out['amount_yuan'] = next(iter(values))
    if not summaries:
        return {**out, 'reason': '仅定位到正文金额，缺少概要金额交叉核对'}
    summary_values = {money(m.group(1), m.group(2)) for m in summaries}
    out['evidence'].extend(m.group(0) for m in summaries[:2])
    if len(summary_values) != 1:
        return {**out, 'reason': '概要存在多个金额，需按包件确认'}
    out['summary_yuan'] = next(iter(summary_values))
    if out['amount_yuan'] != out['summary_yuan']:
        return {**out, 'reason': '概要与正文金额不一致，需要核对更正及费用口径'}
    if not out['project_id'] or not out['published_date']:
        return {**out, 'reason': '金额一致，但项目编号或原公告日期缺失'}
    return {**out, 'status': 'verified', 'reason': '原文概要与正文金额一致，项目编号及日期已提取；规格仍需业务复核'}
