import unittest
from datetime import date
from Department.运营部.shipping_reference import recommend

class ShippingReferenceTests(unittest.TestCase):
    def test_wait_for_monday_and_sea_priority(self):
        r=recommend('美国',500,10,today=date(2026,11,27))
        self.assertEqual(('sea',3,'2026-11-30',35),(r['kind'],r['monday_wait'],r['monday'],r['sea_total_days']))
        self.assertTrue(all(x['country']=='美国' for x in r['routes']))
        self.assertEqual('2026-12-14',r['latest_monday'])

    def test_bridge_minimum_only_and_earliest_viable_route(self):
        r=recommend('美国',200,10,today=date(2026,11,27))
        self.assertEqual('bridge',r['kind'])
        self.assertEqual('联邦-快',r['method']['method'])
        self.assertEqual(160,r['bridge_qty'])
        self.assertEqual(360,200+r['bridge_qty'])

    def test_monday_and_exact_margin(self):
        r=recommend('美国',330,10,today=date(2026,11,30))
        self.assertEqual('sea',r['kind'])
        self.assertEqual(0,r['monday_wait'])
        self.assertEqual('2026-11-30',r['latest_monday'])

    def test_cannot_bridge_in_time(self):
        r=recommend('美国',100,10,today=date(2026,11,27))
        self.assertEqual('risk',r['kind'])
        self.assertEqual(0,r['bridge_qty'])

    def test_no_other_country_route_or_unsupported_sea(self):
        r=recommend('英国',300,10,today=date(2026,11,27))
        self.assertEqual('express_only',r['kind'])
        self.assertNotIn('sea',r)
        self.assertTrue(all(x['country']=='英国' and x['samples']>=5 for x in r['routes']))
        self.assertEqual([],recommend('未知国家',300,10)['routes'])

    def test_all_country_routes_are_shown_but_small_samples_are_not_used(self):
        r=recommend('美国',300,10,today=date(2026,11,27))
        self.assertGreater(len(r['all_routes']),len(r['routes']))
        self.assertTrue(all(x['country']=='美国' for x in r['all_routes']))
        self.assertTrue(any(x['samples']<5 for x in r['all_routes']))
        self.assertTrue(all(x['samples']>=5 for x in r['routes']))

    def test_no_sales(self):
        self.assertEqual('unavailable',recommend('美国',300,0)['kind'])

if __name__=='__main__':unittest.main()
