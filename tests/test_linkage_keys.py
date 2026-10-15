"""argo_linkage_keys — the cleaning and comparison rules linkage stands on.

Every value here is made up. The shapes are the real ones: the hospital-number and histology
formats found in the old linkage scripts and the P20 histology rules. A wrong rule here produces
no crash — only wrong links or missed typos — so each rule gets a known input and output.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "plugins/argo-core/skills/redcap-api/scripts"))

import argo_linkage_keys as lk  # noqa: E402


class Sites(unittest.TestCase):
    def test_every_spelling_lands_on_one_code(self):
        for raw in ("oauthc", "OAUTHC", "oauthc_ife", "oau", " OAU "):
            self.assertEqual(lk.site_code(raw), "OAUTHC", raw)
        self.assertEqual(lk.site_code("uith_ilorin"), "UITH")
        self.assertIsNone(lk.site_code("somewhere new"))

    def test_coded_site_fields_decode_to_the_same_site_across_projects(self):
        crc = lk.site_choices("0, OAUTHC, Ile-Ife | 15, NHA, Abuja | 2, FMC, Owo | 8, FMC, Abeokuta")
        breast = lk.site_choices("1, OAUTHC, Ile-Ife | 19, NH, Abuja | 21, AEFUTH, Abakaliki "
                                 "| 2, FMC, Owo | 15, FMC Kebbi | -888, Missing in case notes")
        self.assertEqual((crc["0"], crc["15"]), (breast["1"], breast["19"]))
        self.assertEqual((crc["2"], crc["8"], breast["15"]), ("FMC-OWO", "FMC-ABEOKUTA", "FMC-KEBBI"))
        self.assertNotIn("-888", breast)
        self.assertEqual(lk.site_choices("8, FMC, Abeokuta"), {"8": "FMC-ABEOKUTA"},
                         "a lone FMC label still keeps its town")


class HospitalNumbers(unittest.TestCase):
    def test_missing_values_are_missing_never_keys(self):
        for raw, why in (("", "blank"), (None, "blank"), ("-888", "missing-data code"),
                         ("08-08-8888", "missing-data code"), ("NIL", "placeholder"),
                         ("not available", "placeholder")):
            h = lk.hospital_number(raw)
            self.assertEqual(h.missing, why, raw)
            self.assertEqual(h.key, "")

    def test_annotations_prefixes_and_suffixes(self):
        self.assertEqual(lk.hospital_number("123456*").key, "123456")
        self.assertEqual(lk.hospital_number("123456 (old file)").key, "123456")
        h = lk.hospital_number("LUTH-654321", site="oauthc")
        self.assertEqual((h.key, h.site), ("654321", "LUTH"), "a prefix in the value names the site")
        h = lk.hospital_number("123456-2")
        self.assertEqual((h.key, h.suffix), ("123456", "2"))
        self.assertIn("five_digit", lk.hospital_number("12345").flags)

    def test_an_unconfirmed_format_is_kept_whole_and_flagged(self):
        h = lk.hospital_number("ABC-12-123456")
        self.assertEqual(h.key, "ABC12123456")
        self.assertIn("unrecognised_format", h.flags)

    def compare(self, a, b, sa="oauthc", sb="oauthc"):
        return lk.compare_hospital(lk.hospital_number(a, sa), lk.hospital_number(b, sb))

    def test_comparisons(self):
        self.assertEqual(self.compare("123456", "123456 "), "exact")
        self.assertEqual(self.compare("123456-1", "123456"), "suffix_differs")
        self.assertEqual(self.compare("012345", "12345"), "leading_zero")
        self.assertEqual(self.compare("123456", "123457"), "one_digit")
        self.assertEqual(self.compare("123456", "124356"), "transposed")
        self.assertEqual(self.compare("123456", "12456"), "digit_missing")
        self.assertIsNone(self.compare("123456", "987654"))
        self.assertIsNone(self.compare("-999", "-999"), "missing never matches missing")

    def test_a_number_is_unique_only_within_one_hospital(self):
        self.assertEqual(self.compare("123456", "123456", "oauthc", "luth"), "different_site")
        self.assertIsNone(self.compare("123456", "123457", "oauthc", "luth"))


class HistologyNumbers(unittest.TestCase):
    def parts(self, raw, site=None):
        h = lk.histology_number(raw, site)
        return (h.prefix, h.number, h.year)

    def test_site_formats(self):
        self.assertEqual(self.parts("H1641/21"), ("H", 1641, 21))          # OAUTHC
        self.assertEqual(self.parts("H/1009/25"), ("H", 1009, 25))
        self.assertEqual(self.parts("1175/21"), ("", 1175, 21))            # OAUTHC, no letter
        self.assertEqual(self.parts("B951/2021"), ("B", 951, 21))          # LUTH, year last
        self.assertEqual(self.parts("HP2074/21"), ("HP", 2074, 21))        # LASUTH
        self.assertEqual(self.parts("TH499/21"), ("TH", 499, 21))          # UITH
        self.assertEqual(self.parts("S-553-23"), ("S", 553, 23))           # NHA
        self.assertEqual(self.parts("S-0376/2023"), ("S", 376, 23))        # UMTH, leading zero

    def test_year_first_private_lab(self):
        self.assertEqual(self.parts("B22/3700"), ("B", 3700, 22), "year-last would be year 3700")
        self.assertEqual(self.parts("B 24/2019", site="lasuth"), ("B", 2019, 24))
        h = lk.histology_number("B 24/2019")
        self.assertIn("ambiguous_b", h.flags, "site unknown and both readings possible")

    def test_missing_and_unparseable(self):
        self.assertEqual(lk.histology_number("-999").missing, "missing-data code")
        self.assertIn("unrecognised_format", lk.histology_number("PENDING 12").flags)
        self.assertEqual(lk.split_histology("H123/21, H456/22"), ["H123/21", "H456/22"])

    def compare(self, a, b):
        return lk.compare_histology(lk.histology_number(a), lk.histology_number(b))

    def test_comparisons(self):
        self.assertEqual(self.compare("H1641/21", "h1641/2021"), "exact")
        self.assertEqual(self.compare("1641/21", "H1641/21"), "exact_no_prefix")
        self.assertEqual(self.compare("H1641/21", "H1641/22"), "year_differs")
        self.assertEqual(self.compare("H1641/21", "S1641/21"), "prefix_differs")
        self.assertEqual(self.compare("H1641/21", "H1614/21"), "one_digit")
        self.assertIsNone(self.compare("H1641/21", "H2000/19"))


class Names(unittest.TestCase):
    def test_tokens(self):
        self.assertEqual(lk.name_tokens("Mrs. Adébáyọ̀", "BELLO"), ["adebayo", "bello"])

    def test_verdicts(self):
        self.assertEqual(lk.compare_names(("Ade", "Bello"), ("ADE", "bello")), ("same", "exact"))
        self.assertEqual(lk.compare_names(("Ade", "Bello"), ("Bello", "Ade")), ("same", "swapped"))
        self.assertEqual(lk.compare_names(("Oluwaseun", "Bello"), ("Oluwaseyi", "Bello"))[0],
                         "ambiguous")
        self.assertEqual(lk.compare_names(("A", "Bello"), ("Ade", "Bello")),
                         ("ambiguous", "initial"))
        self.assertEqual(lk.compare_names(("Ngozi", "Okafor"), ("Musa", "Yusuf")),
                         ("different", "unrelated"))
        self.assertEqual(lk.compare_names(("", ""), ("Ade", "Bello")), ("ambiguous", "missing"))

    def test_jaro_winkler_reference_value(self):
        self.assertAlmostEqual(lk.jaro_winkler("martha", "marhta"), 0.9611, places=3)


class Pairs(unittest.TestCase):
    A = {"site": "oauthc", "hospital_number": "123456", "histology": "H1641/21",
         "first_name": "Ade", "last_name": "Bello"}

    def with_(self, **kw):
        return {**self.A, **kw}

    def test_agree(self):
        self.assertEqual(lk.compare_pair(self.A, self.with_(first_name="ADE")).kind, "agree")

    def test_a_typo_in_one_key_is_a_near_miss_for_an_ra(self):
        f = lk.compare_pair(self.A, self.with_(hospital_number="124356"))
        self.assertEqual(f.kind, "near_miss")
        self.assertIn("two digits swapped", f.explain)
        f = lk.compare_pair(self.A, self.with_(histology="H1641/22", hospital_number=""))
        self.assertEqual(f.kind, "near_miss")
        self.assertIn("year", f.explain)

    def test_same_number_different_person_is_a_conflict(self):
        f = lk.compare_pair(self.A, self.with_(first_name="Musa", last_name="Yusuf"))
        self.assertEqual(f.kind, "conflict")

    def test_same_number_at_two_hospitals(self):
        self.assertEqual(lk.compare_pair(self.A, self.with_(site="luth", histology="")).kind,
                         "near_miss")

    def test_nothing_in_common(self):
        other = {"site": "oauthc", "hospital_number": "987654", "histology": "H2000/19",
                 "first_name": "Musa", "last_name": "Yusuf"}
        self.assertEqual(lk.compare_pair(self.A, other).kind, "unrelated")


if __name__ == "__main__":
    unittest.main()
