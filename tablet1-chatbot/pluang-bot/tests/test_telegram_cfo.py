import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import telegram_cfo as cfo


class TestTelegramCfoParser(unittest.TestCase):
    def test_parse_idr_amounts(self):
        self.assertEqual(cfo.parse_idr_amount("makan 15rb"), 15000)
        self.assertEqual(cfo.parse_idr_amount("kopi 12k"), 12000)
        self.assertEqual(cfo.parse_idr_amount("gaji 1.5jt"), 1500000)
        self.assertEqual(cfo.parse_idr_amount("gaji 1,5jt"), 1500000)
        self.assertEqual(cfo.parse_idr_amount("bayar 50.000"), 50000)
        self.assertEqual(cfo.parse_idr_amount("/tagihan Kuota 65rb tgl 25"), 65000)

    def test_natural_expense_income_savings_transfer(self):
        exp = cfo.parse_finance_chat("makan siang 18rb")
        self.assertEqual(exp["action"], "TX")
        self.assertEqual(exp["type"], "EXPENSE")
        self.assertEqual(exp["amount"], 18000)
        self.assertEqual(exp["category"], "Food & Refreshments")

        trp = cfo.parse_finance_chat("bensin 20k")
        self.assertEqual(trp["type"], "EXPENSE")
        self.assertEqual(trp["category"], "Transportation")
        self.assertEqual(trp["amount"], 20000)

        inc = cfo.parse_finance_chat("gaji 1jt")
        self.assertEqual(inc["type"], "INCOME")
        self.assertEqual(inc["amount"], 1000000)

        sav = cfo.parse_finance_chat("nabung 150rb darurat")
        self.assertEqual(sav["type"], "SAVINGS")
        self.assertEqual(sav["toAccountId"], "ACC-EMG")
        self.assertEqual(sav["amount"], 150000)

        trf = cfo.parse_finance_chat("pindah 50rb ke darurat")
        self.assertEqual(trf["type"], "TRANSFER")
        self.assertEqual(trf["accountId"], "ACC-OPS")
        self.assertEqual(trf["toAccountId"], "ACC-EMG")
        self.assertEqual(trf["amount"], 50000)

    def test_question_routes_to_cfo_not_expense(self):
        ask = cfo.parse_finance_chat("boleh beli sepatu 250rb bulan ini ga?")
        self.assertEqual(ask["action"], "CFO_ASK")
        ask2 = cfo.parse_finance_chat("apakah modal futures aku aman?")
        self.assertEqual(ask2["action"], "CFO_ASK")

    def test_commands_assets_liabilities_bills_pdf_guide(self):
        self.assertEqual(cfo.parse_finance_chat("/uang")["action"], "SUMMARY")
        self.assertEqual(cfo.parse_finance_chat("cek uang")["action"], "SUMMARY")
        self.assertEqual(cfo.parse_finance_chat("/pdf")["action"], "PDF")
        self.assertEqual(cfo.parse_finance_chat("kirim pdf keuangan")["action"], "PDF")
        self.assertEqual(cfo.parse_finance_chat("/panduan")["action"], "GUIDE")
        self.assertEqual(cfo.parse_finance_chat("/undo")["action"], "UNDO")

        ast = cfo.parse_finance_chat("/aset Emas Antam 3.2jt")
        self.assertEqual(ast["action"], "ADD_ASSET")
        self.assertEqual(ast["valueIdr"], 3200000)

        lia = cfo.parse_finance_chat("/hutang PayLater 500rb 100rb")
        self.assertEqual(lia["action"], "ADD_LIABILITY")
        self.assertEqual(lia["principalIdr"], 500000)
        self.assertEqual(lia["monthlyPaymentIdr"], 100000)

        bill = cfo.parse_finance_chat("/tagihan Kuota Internet 65rb tgl 25")
        self.assertEqual(bill["action"], "ADD_BILL")
        self.assertEqual(bill["amountIdr"], 65000)
        self.assertEqual(bill["dueDay"], 25)

    def test_does_not_hijack_crypto_commands(self):
        self.assertIsNone(cfo.parse_finance_chat("/btc"))
        self.assertIsNone(cfo.parse_finance_chat("/scan sol"))
        self.assertIsNone(cfo.parse_finance_chat("/wallet"))


if __name__ == "__main__":
    unittest.main()
