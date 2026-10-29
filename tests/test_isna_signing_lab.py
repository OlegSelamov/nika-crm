"""No-network tests for the test-only server -> Android SOAP signing handshake."""
import os
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from services import isna_bip
from services.isna_signing_lab import (
    create_server_signing_sample, OFFLINE_SERVICE_ID, OFFLINE_SENDER_ID,
    DEMO_NS,
)


class TestServerSigningSample(unittest.TestCase):
    def test_signable_bip_sample_has_no_live_credentials_or_fno(self):
        with patch.dict(os.environ, {
            "ISNA_BIP_SERVICE_ID": "FNO_INTEGRATION",
            "ISNA_BIP_SENDER_ID": "real-sender-should-not-leak",
            "ISNA_BIP_PASSWORD": "real-secret-should-not-leak",
        }), patch.object(isna_bip.requests, "post") as post:
            result = create_server_signing_sample()
            post.assert_not_called()
        xml = result["soapXml"]
        root = ET.fromstring(xml)
        self.assertTrue(result["offlineOnly"])
        self.assertFalse(result["soapSent"])
        self.assertFalse(result["hasTaxpayerData"])
        self.assertFalse(result["hasGatewayPassword"])
        self.assertFalse(result["containsRealServiceId"])
        self.assertNotIn("real-sender-should-not-leak", xml)
        self.assertNotIn("real-secret-should-not-leak", xml)
        self.assertNotIn("FNO_INTEGRATION", xml)
        self.assertEqual(root.tag, f"{{{isna_bip.SOAP_NS}}}Envelope")
        body = root.find(f"{{{isna_bip.SOAP_NS}}}Body")
        self.assertTrue(body.get(f"{{{isna_bip.WSU_NS}}}Id", "").startswith("id-"))
        self.assertEqual(root.findtext(".//requestInfo/serviceId"), OFFLINE_SERVICE_ID)
        self.assertEqual(root.findtext(".//sender/senderId"), OFFLINE_SENDER_ID)
        self.assertIsNone(root.find(".//sender/password"))
        demo = root.find(f".//{{{DEMO_NS}}}NikaWsSecurityTest")
        self.assertIsNotNone(demo)
        self.assertEqual(demo.findtext(f"{{{DEMO_NS}}}Submission"), "false")

    def test_each_demo_has_distinct_message_id_and_wsu_body_id(self):
        first = ET.fromstring(create_server_signing_sample()["soapXml"])
        second = ET.fromstring(create_server_signing_sample()["soapXml"])
        self.assertNotEqual(first.findtext(".//requestInfo/messageId"), second.findtext(".//requestInfo/messageId"))
        b1 = first.find(f"{{{isna_bip.SOAP_NS}}}Body")
        b2 = second.find(f"{{{isna_bip.SOAP_NS}}}Body")
        self.assertNotEqual(b1.get(f"{{{isna_bip.WSU_NS}}}Id"), b2.get(f"{{{isna_bip.WSU_NS}}}Id"))


if __name__ == "__main__":
    unittest.main()
