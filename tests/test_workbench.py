import time
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

from app.exporter import csv_safe
from app.main import create_app
from app.parser import money, parse_notice
from app.provider import ServiceError, validate_source_url
from app.service import deduplicate
from app.settings import Settings


def notice(body='2338340.00', summary='233.834000'):
    return f'''2026年01月09日
一、项目编号
JZGC-ZC202510001
三、中标（成交）信息
中标类型：总价中标
中标（成交）金额（元）\\（%）：{body}
六、代理服务收费标准及金额
29721.74元
总中标金额
￥{summary} 万元（人民币）'''


@pytest.mark.parametrize('raw,unit,expected', [('1000','元','1000.00'),('12000','元','12000.00'),
    ('1,234.56','元','1234.56'),('100','万元','1000000.00')])
def test_complete_numeric_token(raw, unit, expected):
    assert money(raw,unit)==expected


def test_fee_is_not_transaction_amount():
    result=parse_notice(notice(),'智慧黑板成交公告')
    assert result['status']=='verified'
    assert Decimal(result['amount_yuan'])==Decimal('2338340.00')
    assert all('29721.74' not in x for x in result['evidence'])


def test_conflict_and_related_are_not_passed():
    assert parse_notice(notice(summary='100'),'成交公告')['status']=='pending'
    assert parse_notice(notice(),'智慧黑板更正公告')['status']=='pending'
    assert parse_notice(notice(),'智慧黑板废标公告')['status']=='excluded'
    assert parse_notice(notice().replace('总价中标','费率中标'),'成交公告')['status']=='pending'


@pytest.mark.parametrize('url',['http://www.ccgp.gov.cn/a','https://127.0.0.1/a',
    'https://ccgp.gov.cn.evil.example/a','https://ccgp.gov.cn:22/a','https://user:pass@ccgp.gov.cn/a'])
def test_unsafe_source_rejected(url):
    with pytest.raises(ServiceError):
        validate_source_url(url)


def test_project_duplicates_and_conflicting_packages():
    rows=[{'id':'a','project_id':'P1','amount_yuan':'10.00','status':'verified'},
          {'id':'b','project_id':'P1','amount_yuan':'10.00','status':'verified'}]
    deduplicate(rows)
    assert rows[1]['status']=='duplicate'
    rows[1].update(amount_yuan='20.00',status='verified')
    deduplicate(rows)
    assert all(r['status']=='pending' for r in rows)


def test_full_demo_task_and_exports(tmp_path):
    with TestClient(create_app(Settings(tmp_path,key=''))) as client:
        assert client.get('/').status_code==200
        assert client.get('/api/config').json()['live_available'] is False
        assert client.post('/api/tasks',json={'keyword':'智慧黑板','mode':'live'}).status_code==400
        submitted=client.post('/api/tasks',json={'keyword':'智慧黑板','mode':'demo','target':3})
        assert submitted.status_code==202
        task_id=submitted.json()['id']
        for _ in range(100):
            task=client.get('/api/tasks/'+task_id).json()
            if task['status'] not in ('queued','running'):
                break
            time.sleep(.02)
        assert task['status']=='completed'
        assert task['stats']['verified']==4
        assert all(r['mode']=='demo' for r in task['records'])
        for format in ('json','csv','html'):
            response=client.get(f'/api/tasks/{task_id}/export?format={format}')
            assert response.status_code==200
            assert len(response.content)>100
        html=client.get(f'/api/tasks/{task_id}/export?format=html').text
        assert '历史样本' in html and '2338340.00' in html
        assert len(client.get('/api/tasks').json())==1
        assert client.get('/api/tasks/notfound').status_code==404
    # A new process/store can still read the saved report.
    with TestClient(create_app(Settings(tmp_path,key=''))) as client:
        assert client.get('/api/tasks/'+task_id).json()['status']=='completed'


def test_access_control_and_csv_injection(tmp_path):
    with TestClient(create_app(Settings(tmp_path,key='',access_token='test-password'))) as client:
        assert client.get('/api/tasks').status_code==401
        assert client.get('/api/tasks',headers={'X-App-Token':'test-password'}).status_code==200
        assert 'test-password' not in client.get('/api/config').text
    assert csv_safe('=HYPERLINK("x")').startswith("'")
