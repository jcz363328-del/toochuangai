import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from integrations.sellfox import sellfox_purchase as service

class SellfoxPurchaseTests(unittest.TestCase):
    def test_repeat_returns_original(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"ledger.sqlite"
            sender=Mock(return_value={"planNo":"TEST"})
            service.create_once({"userName":"甲"},path,sender=sender)
            result,reused=service.create_once({"userName":"甲"},path,sender=sender)
            self.assertTrue(reused)
            self.assertEqual({"planNo":"TEST"},result)
            sender.assert_called_once()

    def test_uncertainty_blocks_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"ledger.sqlite"
            sender=Mock(side_effect=TimeoutError())
            for _ in range(2):
                with self.assertRaises(service.PurchaseUncertain):
                    service.create_once({},path,sender=sender)
            sender.assert_called_once()

    def test_rejection_allows_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            sender=Mock(side_effect=[service.PurchaseRejected("invalid"),{"planNo":"TEST"}])
            path=Path(temp)/"ledger.sqlite"
            with self.assertRaises(service.PurchaseRejected):
                service.create_once({},path,sender=sender)
            result,reused=service.create_once({},path,sender=sender)
            self.assertFalse(reused)
            self.assertEqual({"planNo":"TEST"},result)

    def test_explicit_api_error_is_visible_and_not_uncertain(self):
        import sys
        client=Mock()
        client.session.request.return_value.status_code=400
        client.session.request.return_value.json.return_value={"code":40014,"msg":"采购方不存在"}
        with patch.object(service,"get_client",return_value=client), patch.dict(sys.modules,{"sellfox_import":Mock(API_BASE_URL="https://openapi.sellfox.com")}):
            with self.assertRaisesRegex(service.PurchaseRejected,"采购方不存在"):
                service.send_purchase({"items":[]})
        client.session.request.assert_called_once()

    def test_timeout_is_uncertain_without_retry(self):
        import sys,requests
        client=Mock()
        client.session.request.side_effect=requests.Timeout()
        with patch.object(service,"get_client",return_value=client), patch.dict(sys.modules,{"sellfox_import":Mock(API_BASE_URL="https://openapi.sellfox.com")}):
            with self.assertRaises(service.PurchaseUncertain):
                service.send_purchase({"items":[]})
        client.session.request.assert_called_once()

    def test_uncertain_preserves_diagnostic_on_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"ledger.sqlite"
            sender=Mock(side_effect=service.PurchaseUncertain("HTTP 502 回执异常"))
            for _ in range(2):
                with self.assertRaisesRegex(service.PurchaseUncertain,"HTTP 502"):
                    service.create_once({},path,sender=sender)
            sender.assert_called_once()
