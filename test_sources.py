import datetime as dt
import json
import re
import unittest
from unittest.mock import patch
import collector as c

class SourceTests(unittest.TestCase):
    def setUp(self):
        c.SOURCE_REPORT.clear()
        self.now = dt.datetime.now(dt.timezone.utc).isoformat()

    def test_city_and_location_requests(self):
        self.assertIsNone(c.classify('Нужен фотограф в Верхней Пышме завтра', True))
        self.assertIsNone(c.classify('Нужен фотограф в Берёзовском на свадьбу', True))
        self.assertIsNone(c.classify('Нужен фотограф в Москве завтра', True))
        self.assertIsNone(c.classify('Ищу фотографа на завтра', False, 'Екатеринбург'))
        self.assertIsNone(c.classify('Подскажите уличные локации для свадебной съёмки', True))
        self.assertIsNotNone(c.classify('Нужен фотограф на корпоратив, Фрунзе 35а', True))
        self.assertIsNotNone(c.classify('Нужен фотограф в Екатеринбурге завтра', False))

    def test_zarplata_identity_and_origin(self):
        job={'@type':'JobPosting','title':'Фотограф','datePosted':self.now,'jobLocation':{'address':{'addressLocality':'Екатеринбург'}}}
        page='<script type="application/ld+json">'+json.dumps(job)+'</script>'
        lead=c.parse_hh_vacancy(page,'https://ekaterinburg.zarplata.ru/vacancy/123','zarplata')
        self.assertEqual(lead['id'],'jobs:zarplata:123')
        self.assertIsNone(c.parse_hh_vacancy(page,'https://evil.example/vacancy/123','zarplata'))

    def widget(self, mid, text='Ищу фотографа на свадьбу в Екатеринбурге'):
        return f'<div data-post="chatphotomeet/{mid}"><div class="tgme_widget_message_text js-message_text">{text}</div><time datetime="{self.now}"></time></div>'

    def test_widget_original_link_and_offer(self):
        exists, lead = c.parse_public_widget(self.widget(7), 'chatphotomeet', 7, 'ФОТОМИТ')
        self.assertTrue(exists)
        self.assertEqual(lead['url'], 'https://t.me/chatphotomeet/7')
        self.assertEqual(c.parse_public_widget(self.widget(7,'Я фотограф, ищу моделей для съёмки'), 'chatphotomeet',7,'ФОТОМИТ'),(True,None))

    def test_unknown_response_is_not_deleted_message(self):
        with self.assertRaises(ValueError):
            c.parse_public_widget('<html>rate limit</html>','chatphotomeet',7,'ФОТОМИТ')
        self.assertEqual(c.parse_public_widget('<div class="tgme_widget_message_error">Post not found</div>','chatphotomeet',7,'ФОТОМИТ'),(False,None))

    def test_bootstrap_crosses_deleted_gap_to_known_seed(self):
        config={'telegram_public_chats':[{'username':'chatphotomeet','seed_message_id':70}]}
        def get(url, timeout=15):
            mid=int(re.search(r'/([0-9]+)\?',url).group(1))
            return self.widget(mid) if mid==70 else '<div class="tgme_widget_message_error">Missing</div>'
        with patch.object(c,'CFG',config), patch.object(c,'load_json',return_value={}), patch.object(c,'http_get',side_effect=get):
            leads,_=c.fetch_tg_public()
        self.assertEqual(len(leads),1)
        self.assertEqual(c.PENDING_TG_CURSORS['chatphotomeet'],70)

    def test_network_failure_preserves_retry_position(self):
        config={'telegram_public_chats':[{'username':'chatphotomeet','seed_message_id':70}]}
        def get(url, timeout=15):
            mid=int(re.search(r'/([0-9]+)\?',url).group(1))
            if mid==8: raise TimeoutError()
            return self.widget(mid) if mid==7 else '<div class="tgme_widget_message_error">Missing</div>'
        with patch.object(c,'CFG',config), patch.object(c,'load_json',return_value={}), patch.object(c,'http_get',side_effect=get):
            leads,_=c.fetch_tg_public()
        self.assertEqual(c.PENDING_TG_CURSORS['chatphotomeet'],7)

    def test_national_digest_does_not_mix_cities(self):
        bad='1. (#Екатеринбург) Нужны танцоры на мероприятие\n2. (#Москва) Ищу фотографа на свадьбу'
        self.assertIsNone(c.relevant_text(bad,False))
        good='1. (#Москва) Ищу фотографа на свадьбу\n2. (#Екатеринбург) Нужен фотограф на корпоратив'
        self.assertIn('Екатеринбург',c.relevant_text(good,False))
        self.assertNotIn('Москва',c.relevant_text(good,False))

    def test_vacancy_city_and_publication_date(self):
        def vacancy(city, ident, date):
            return {'vacancy':{'id':ident,'job-name':'художник-фотограф', 'creation-date':date,
                'vac_url':'https://trudvsem.ru/vacancy/card/company/'+ident,
                'addresses':{'address':[{'location':city}]},'company':{'name':'Студия'},'duty':'Съёмка мероприятий'}}
        today=dt.datetime.now().date().isoformat()
        data={'status':'200','results':{'vacancies':[vacancy('г Екатеринбург','1',today),vacancy('г Нижний Тагил','2',today),vacancy('г Екатеринбург','3','2020-01-01')]}}
        with patch.object(c,'http_get',return_value=json.dumps(data)):
            leads,_=c.fetch_trudvsem()
        self.assertEqual(len(leads),1)
        self.assertEqual(leads[0]['src'],'jobs')
        self.assertIn('вакансия',leads[0]['tags'])

class ProfiTests(unittest.TestCase):
    def test_original_url_date_city_and_service(self):
        now=dt.datetime.now(dt.timezone(dt.timedelta(hours=3)))
        row={'id':'123','receivd':now.strftime('%a %b %d %Y %H:%M:%S GMT%z')+' (MSK)',
             'geoplaces':[{'name':'Екатеринбург'}], 'pservices':[{'id':'26500'}],
             'detailsPublic':'Фотосессия в студии', 'name':'Тест', 'wpriceMax':'3000'}
        old=dict(row,id='124',receivd='Sun Nov 15 2020 16:12:11 GMT+0300 (MSK)')
        other=dict(row,id='125',geoplaces=[{'name':'Полевской'}])
        unrelated=dict(row,id='126',pservices=[{'id':'101'}])
        data={'props':{'pageProps':{'legoData':{'legoLandingData':{'blocks':[{'currentOrders':[row,old,other,unrelated]}]}}}}}
        page='<script id="__NEXT_DATA__">'+json.dumps(data)+'</script>'+''.join('/backoffice/n.php?o='+x for x in ['123','124','125','126'])
        with patch.object(c,'http_get',return_value=page): leads,note=c.fetch_profi()
        self.assertEqual(len(leads),1)
        self.assertEqual(leads[0]['url'],'https://profi.ru/backoffice/n.php?o=123')
        self.assertLess(abs(leads[0]['ts']-now.timestamp()),2)

    def test_generic_page_is_unavailable_not_empty_success(self):
        with patch.object(c,'http_get',return_value='<html>Sign in</html>'):
            leads,note=c.fetch_profi()
        self.assertIsNone(leads)

class HhWebTests(unittest.TestCase):
    def test_only_dated_photographer_jobs_in_city(self):
        job={'@type':'JobPosting','title':'Фотограф','datePosted':dt.datetime.now(dt.timezone.utc).isoformat(),
             'jobLocation':{'address':{'addressLocality':'Екатеринбург'}},'description':'Съёмка мероприятий'}
        def page(data): return '<script type="application/ld+json">'+json.dumps(data)+'</script>'
        link='https://ekaterinburg.hh.ru/vacancy/123'
        lead=c.parse_hh_vacancy(page(job),link)
        self.assertEqual(lead['url'],link)
        self.assertIn('вакансия',lead['tags'])
        for changed in [dict(job,datePosted='2020-01-01T00:00:00+03:00'), dict(job,datePosted=''),
                        dict(job,jobLocation={'address':{'addressLocality':'Москва'}}),dict(job,title='Ретушер фотографий')]:
            self.assertIsNone(c.parse_hh_vacancy(page(changed),link))
        self.assertIsNone(c.parse_hh_vacancy(page(job),'https://example.org/vacancy/123'))

    def test_unavailable_is_reported(self):
        with patch.object(c,'http_get',side_effect=RuntimeError('HTTP 403')):
            leads,note=c.fetch_hh_web()
        self.assertIsNone(leads)
        self.assertFalse(c.SOURCE_REPORT[-1]['ok'])

if __name__=='__main__': unittest.main()
