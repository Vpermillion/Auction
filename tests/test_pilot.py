import re
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from auction.app import create_app
from auction.seed import seed
from auction import service
from auction.payments import DisabledPaymentAdapter


class PilotCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'test.sqlite3')
        service.migrate(self.path)
        self.db = service.connect(self.path)
        seed(self.db)
        self.app = create_app({'TESTING':True,'DATABASE':self.path,'SECRET_KEY':'test-secret-of-at-least-32-characters'})
        self.client = self.app.test_client()
        self.counter = 0

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def key(self):
        self.counter += 1
        return f'test-idempotency-key-{self.counter:06}'

    def login(self, address='buyer@example.test'):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            token = session['csrf']
        response = self.client.post('/login',data={'email':address,'password':'Pilot-demo-2026!','csrf':token})
        self.assertEqual(response.status_code,302)

    def post(self, path, data=None, json_data=None):
        self.client.get('/')
        with self.client.session_transaction() as session:
            token = session['csrf']
        if json_data is not None:
            return self.client.post(path,json=json_data,headers={'X-CSRF-Token':token})
        return self.client.post(path,data={**(data or {}),'csrf':token})

    def row(self, aid=1):
        return self.db.execute('SELECT * FROM auctions WHERE id=?',(aid,)).fetchone()

    def values(self, **changes):
        a = self.row()
        values = {k:str(a[k]) for k in ['title','description','condition','evidence','image','start_price','increment','soft_close','payment_hours','fees','seller_terms','payment_instructions']}
        values['closes_at'] = datetime.fromtimestamp(service.now(self.db)+86400, timezone(timedelta(hours=8))).strftime('%Y-%m-%dT%H:%M')
        values.update(changes)
        return values

    def test_concurrent_bidders_only_one_same_price_accepted(self):
        barrier=threading.Barrier(10)
        def attempt(i):
            db=service.connect(self.path)
            try:
                barrier.wait()
                try:
                    service.place_bid(db,1 if i%2 else 5,1,180000,f'concurrent-price-{i:06}')
                    return 'accepted'
                except service.RuleError:
                    return 'rejected'
            finally:
                db.close()
        with ThreadPoolExecutor(max_workers=10) as pool:
            results=list(pool.map(attempt,range(10)))
        self.assertEqual(results.count('accepted'),1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM bids WHERE auction_id=1').fetchone()[0],1)

    def test_concurrent_duplicate_requests_return_one_bid(self):
        barrier=threading.Barrier(8)
        def attempt(_):
            db=service.connect(self.path)
            try:
                barrier.wait()
                return service.place_bid(db,1,1,180000,'same-concurrent-request-key')
            finally:
                db.close()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(attempt,range(8)))
        self.assertEqual(len({result[0]['id'] for result in results}),1)
        self.assertEqual(sum(not replay for _,replay in results),1)

    def test_duplicate_replay_after_close_and_payload_mismatch(self):
        key=self.key()
        first,_=service.place_bid(self.db,1,1,180000,key)
        self.db.execute("UPDATE auctions SET closes_at=unixepoch()-1 WHERE id=1")
        service.close_due(self.db)
        replay,duplicate=service.place_bid(self.db,1,1,180000,key)
        self.assertTrue(duplicate)
        self.assertEqual(first['id'],replay['id'])
        with self.assertRaises(service.RuleError):
            service.place_bid(self.db,1,1,190000,key)
        with self.assertRaises(service.RuleError):
            service.place_bid(self.db,1,2,180000,key)

    def test_bids_at_or_after_deadline_close_without_accepting(self):
        self.db.execute('UPDATE auctions SET closes_at=2000000000 WHERE id=1')
        for timestamp in [2000000000,2000000001]:
            with patch('auction.service.now',return_value=timestamp):
                with self.assertRaises(service.RuleError):
                    service.place_bid(self.db,1,1,180000,self.key())
        self.assertEqual(self.row()['state'],'closed')
        self.assertIsNone(self.row()['winner_id'])

    def test_time_is_read_after_write_lock(self):
        with patch('auction.service.now',wraps=service.now) as clock:
            service.place_bid(self.db,1,1,180000,self.key())
            self.assertTrue(clock.called)
        # An SQL trace records BEGIN before the authoritative time query.
        trace=[]
        self.db.set_trace_callback(trace.append)
        service.place_bid(self.db,5,1,190000,self.key())
        self.assertLess(next(i for i,x in enumerate(trace) if 'BEGIN IMMEDIATE' in x), next(i for i,x in enumerate(trace) if "SELECT unixepoch('now')" in x))

    def test_bid_waiting_for_lock_cannot_use_predeadline_time(self):
        self.db.execute('UPDATE auctions SET closes_at=2000000000,soft_close=0 WHERE id=1')
        entered = threading.Event()
        clock = [1999999999]
        self.db.execute('BEGIN IMMEDIATE')
        def attempt():
            other = service.connect(self.path)
            other.set_trace_callback(lambda sql: entered.set() if sql == 'BEGIN IMMEDIATE' else None)
            try:
                with self.assertRaises(service.RuleError):
                    service.place_bid(other,1,1,180000,'blocked-request-at-deadline')
            finally:
                other.close()
        with patch('auction.service.now', side_effect=lambda _db: clock[0]):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(attempt)
                self.assertTrue(entered.wait(timeout=5))
                clock[0] = 2000000000
                self.db.commit()
                future.result(timeout=5)
        self.assertEqual(self.row()['state'],'closed')
        self.assertIsNone(self.row()['winner_id'])

    def test_concurrent_bid_and_closer_select_same_existing_winner(self):
        service.place_bid(self.db,1,1,180000,self.key())
        self.db.execute('UPDATE auctions SET closes_at=2000000000,soft_close=0 WHERE id=1')
        barrier = threading.Barrier(2)
        def operation(close):
            other=service.connect(self.path)
            try:
                barrier.wait()
                if close:
                    service.close_due(other)
                else:
                    with self.assertRaises(service.RuleError):
                        service.place_bid(other,5,1,190000,'bid-and-close-race-request')
            finally:
                other.close()
        with patch('auction.service.now',return_value=2000000000):
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(operation,[True,False]))
        self.assertEqual(self.row()['winner_id'],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM bids WHERE auction_id=1').fetchone()[0],1)

    def test_repeated_soft_close_extensions(self):
        self.db.execute('UPDATE auctions SET closes_at=2000000100 WHERE id=1')
        with patch('auction.service.now',return_value=2000000000):
            service.place_bid(self.db,1,1,180000,self.key())
        self.assertEqual(self.row()['closes_at'],2000000120)
        with patch('auction.service.now',return_value=2000000119):
            service.place_bid(self.db,5,1,190000,self.key())
        self.assertEqual(self.row()['closes_at'],2000000239)

    def test_soft_close_disabled_and_outside_window(self):
        timestamp=service.now(self.db)
        self.db.execute('UPDATE auctions SET closes_at=?,soft_close=0 WHERE id=1',(timestamp+60,))
        service.place_bid(self.db,1,1,180000,self.key())
        self.assertEqual(self.row()['closes_at'],timestamp+60)
        self.db.execute('UPDATE auctions SET closes_at=?,soft_close=120 WHERE id=1',(timestamp+1000,))
        service.place_bid(self.db,5,1,190000,self.key())
        self.assertEqual(self.row()['closes_at'],timestamp+1000)

    def test_highest_bid_wins_once_and_no_bid_no_winner(self):
        service.place_bid(self.db,1,1,180000,self.key())
        service.place_bid(self.db,5,1,190000,self.key())
        self.db.execute('UPDATE auctions SET closes_at=unixepoch()-1 WHERE id IN (1,2)')
        service.close_due(self.db)
        service.close_due(self.db)
        self.assertEqual(self.row()['winner_id'],5)
        self.assertIsNone(self.row(2)['winner_id'])
        self.assertEqual(self.db.execute("SELECT count(*) FROM audit WHERE action='auction_closed' AND entity_id=1").fetchone()[0],1)

    def test_integer_amounts_and_minimum_increment(self):
        for amount in [180000.1,'180000',True,-1,0,10**13]:
            with self.assertRaises(service.RuleError):
                service.place_bid(self.db,1,1,amount,self.key())
        service.place_bid(self.db,1,1,180000,self.key())
        with self.assertRaises(service.RuleError):
            service.place_bid(self.db,5,1,189999,self.key())

    def test_seller_operator_suspended_buyer_and_shop_cannot_bid(self):
        for uid in [2,3,4]:
            with self.assertRaises(service.RuleError):
                service.place_bid(self.db,uid,1,180000,self.key())
        self.db.execute('UPDATE users SET suspended=1 WHERE id=1')
        with self.assertRaises(service.RuleError):
            service.place_bid(self.db,1,1,180000,self.key())
        self.db.execute("UPDATE shops SET status='suspended' WHERE id=1")
        with self.assertRaises(service.RuleError):
            service.place_bid(self.db,5,1,180000,self.key())

    def test_bids_and_audit_cannot_be_edited_or_deleted(self):
        for sql in ["UPDATE bids SET amount=1 WHERE auction_id=4","DELETE FROM bids WHERE auction_id=4","UPDATE audit SET detail='changed'","DELETE FROM audit"]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(sql)

    def test_all_page_templates_render_for_relevant_roles(self):
        for path in ['/','/explore','/shops/altan-studio','/auctions/1','/policies','/login','/register','/missing']:
            self.assertEqual(self.client.get(path).status_code,404 if path=='/missing' else 200,path)
        for email,paths in [('buyer@example.test',['/account']),('seller@example.test',['/seller','/seller/new']),('operator@example.test',['/operator'])]:
            self.login(email)
            for path in paths:
                self.assertEqual(self.client.get(path).status_code,200,path)

    def test_csrf_and_role_checks(self):
        self.assertEqual(self.client.post('/inquiry',data={'email':'a@b.test','message':'hello world'}).status_code,400)
        self.login()
        self.assertEqual(self.client.get('/seller').status_code,403)
        self.assertEqual(self.client.get('/operator').status_code,403)
        self.assertEqual(self.post('/operator/action',{'kind':'user','entity_id':'2','reason':'not allowed here'}).status_code,403)
        self.assertEqual(self.client.post('/api/auctions/1/bids',json={'amount':180000,'request_key':self.key()}).status_code,400)

    def test_cross_shop_read_edit_cancel_status_relist_and_export_isolation(self):
        self.login('other-seller@example.test')
        self.assertEqual(self.client.get('/seller/1/edit').status_code,403)
        for action,data in [('edit',self.values()),('cancel',{'reason':'foreign shop cancellation'}),('status',{'kind':'payment','value':'paid','reason':'foreign payment attempt'}),('relist',{'reason':'foreign relist attempt'})]:
            self.assertEqual(self.post('/seller/1/'+action,data).status_code,403,action)
        output=self.client.get('/seller/export.csv').get_data(as_text=True)
        self.assertIn('silver lining',output)
        self.assertNotIn('everyday pendant',output)
        self.assertNotIn('buyer@example.test',self.client.get('/seller').get_data(as_text=True))

    def test_full_seller_create_publish_buyer_bid_close_and_fulfill(self):
        self.login('seller@example.test')
        response=self.post('/seller/new',self.values())
        self.assertEqual(response.status_code,302)
        aid=int(re.search('/seller/(\d+)/edit',response.location).group(1))
        self.assertEqual(self.client.get(response.location).status_code,200)
        self.assertEqual(self.post(f'/seller/{aid}/publish').status_code,302)
        self.assertEqual(self.post(f'/seller/{aid}/edit',self.values(title='silently changed')).status_code,409)
        self.login()
        response=self.post(f'/api/auctions/{aid}/bids',json_data={'amount':180000,'request_key':self.key()})
        self.assertEqual(response.status_code,201)
        self.db.execute('UPDATE auctions SET closes_at=unixepoch()-1 WHERE id=?',(aid,))
        response=self.client.get('/account')
        self.assertIn('You won',response.get_data(as_text=True))
        self.login('seller@example.test')
        for kind,value in [('payment','paid'),('fulfillment','collected')]:
            self.assertEqual(self.post(f'/seller/{aid}/status',{'kind':kind,'value':value,'reason':'Confirmed from seller records'}).status_code,302)
        self.assertEqual(self.row(aid)['fulfillment'],'collected')

    def test_public_bid_history_has_no_email_or_private_request_key(self):
        service.place_bid(self.db,1,1,180000,self.key())
        for path in ['/auctions/1','/api/auctions/1']:
            body=self.client.get(path).get_data(as_text=True)
            self.assertIn('Bidder-7F2A',body)
            self.assertNotIn('buyer@example.test',body)
            self.assertNotIn('test-idempotency',body)
            self.assertNotIn('user_id',body)

    def test_winner_instructions_private_and_other_bidder_sees_loss(self):
        self.login('buyer2@example.test')
        self.assertNotIn('DEMO ONLY — do not transfer money',self.client.get('/account').get_data(as_text=True))
        self.login()
        self.assertIn('DEMO ONLY',self.client.get('/account').get_data(as_text=True))

    def test_report_operator_review_and_suspension(self):
        self.login()
        self.assertEqual(self.post('/auctions/1/report',{'reason':'Suspected coordinated bidding for operator review'}).status_code,302)
        self.login('operator@example.test')
        report_id=self.db.execute('SELECT id FROM reports').fetchone()[0]
        self.assertEqual(self.post('/operator/action',{'kind':'report','entity_id':str(report_id),'reason':'Reviewed and seller contacted manually'}).status_code,302)
        service.place_bid(self.db,1,1,180000,self.key())
        self.assertEqual(self.post('/operator/action',{'kind':'auction','entity_id':'1','reason':'Pause for misleading seller evidence'}).status_code,302)
        self.assertEqual(self.row()['state'],'suspended')
        self.assertIsNone(self.row()['winner_id'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM bids WHERE auction_id=1').fetchone()[0],1)

    def test_shop_suspension_preserves_already_closed_award(self):
        self.login('operator@example.test')
        self.assertEqual(self.post('/operator/action',{'kind':'shop','entity_id':'1','reason':'Review this synthetic seller account'}).status_code,302)
        self.assertEqual(self.row()['state'],'suspended')
        self.assertEqual(self.row(4)['winner_id'],1)
        self.assertEqual(self.row(4)['state'],'closed')

    def test_operator_onboarding_and_duplicate_rollback(self):
        self.login('operator@example.test')
        values=dict(name='New Demo Shop',slug='new-demo-shop',address='Demo pickup location',contact='shop@example.test',
                    terms='Draft seller policies for legal review',instructions='Demo payment instructions only',identity_note='Documents checked manually; no item authentication',email='new-seller@example.test',password='temporary-demo-password')
        self.assertEqual(self.post('/operator/onboard',values).status_code,302)
        self.assertEqual(self.post('/operator/onboard',{**values,'slug':'duplicate-shop'}).status_code,400)
        self.assertIsNone(self.db.execute("SELECT * FROM shops WHERE slug='duplicate-shop'").fetchone())

    def test_cancel_relist_retains_bids(self):
        service.place_bid(self.db,1,1,180000,self.key())
        self.login('seller@example.test')
        self.assertEqual(self.post('/seller/1/cancel',{'reason':'Material condition error requires a new listing'}).status_code,302)
        self.assertEqual(self.post('/seller/1/relist',{'reason':'Reviewed correction and notified demo bidders'}).status_code,302)
        self.assertEqual(self.row()['state'],'cancelled')
        self.assertEqual(self.db.execute('SELECT count(*) FROM bids WHERE auction_id=1').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT state FROM auctions ORDER BY id DESC LIMIT 1').fetchone()[0],'draft')

    def test_unpaid_review_requires_elapsed_deadline(self):
        self.login('seller@example.test')
        data={'kind':'payment','value':'unpaid_review','reason':'No payment received; contacted buyer manually'}
        self.assertEqual(self.post('/seller/4/status',data).status_code,409)
        self.db.execute('UPDATE auctions SET closes_at=unixepoch()-200000 WHERE id=4')
        self.assertEqual(self.post('/seller/4/status',data).status_code,302)
        self.assertEqual(self.post('/seller/4/relist',{'reason':'Documented review with original winner; relist agreed'}).status_code,302)
        self.assertEqual(self.row(4)['winner_id'],1)

    def test_registration_cannot_escalate_role(self):
        response=self.post('/register',{'email':'new@example.test','password':'a-long-demo-password','role':'operator','shop_id':'1','accept':'yes'})
        self.assertEqual(response.status_code,302)
        row=self.db.execute("SELECT * FROM users WHERE email='new@example.test'").fetchone()
        self.assertEqual(row['role'],'buyer')
        self.assertIsNone(row['shop_id'])
        self.assertNotEqual(row['password'],'a-long-demo-password')

    def test_suspended_session_stops_writes(self):
        self.login()
        self.db.execute('UPDATE users SET suspended=1 WHERE id=1')
        response=self.post('/api/auctions/1/bids',json_data={'amount':180000,'request_key':self.key()})
        self.assertEqual(response.status_code,401)

    def test_rate_limit_persists_across_connections(self):
        self.assertTrue(service.rate_limit(self.db,'test',2,60))
        other=service.connect(self.path)
        try:
            self.assertTrue(service.rate_limit(other,'test',2,60))
            self.assertFalse(service.rate_limit(other,'test',2,60))
        finally:
            other.close()

    def test_security_headers_language_and_disabled_provider(self):
        response=self.client.get('/')
        self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(self.post('/language',{'lang':'mn','next':'//evil.test'}).location,'/')
        self.assertIn('lang="mn"',self.client.get('/explore').get_data(as_text=True))
        with self.assertRaises(RuntimeError):
            DisabledPaymentAdapter().verify_payment('browser screenshot')

    def test_uploads_rejected_and_status_select_works_without_javascript(self):
        import io
        self.login('seller@example.test')
        response=self.post('/seller/new',{**self.values(),'photo':(io.BytesIO(b'not-a-photo'),'photo.jpg')})
        self.assertEqual(response.status_code,400)
        response=self.post('/seller/4/status',{'outcome':'payment:paid','reason':'Synthetic manual record without JavaScript'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.row(4)['payment'],'paid')

    def test_bid_endpoint_rejects_nonobject_json(self):
        self.login()
        for value in [[],['not an object'],123,'text',False]:
            response=self.post('/api/auctions/1/bids',json_data=value)
            self.assertEqual(response.status_code,400)


if __name__=='__main__':
    unittest.main()
