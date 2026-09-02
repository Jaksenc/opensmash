import bz2
import csv
import gzip
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))

from build_wikipedia_people_seed import (  # noqa: E402
    RankedPage,
    complete_months,
    load_pageranks,
    load_qranks,
    manual_person,
    page_score,
    read_exclusions,
    select_people,
)


def entity(name, *, human=True, image=True):
    claims = {
        "P31": [
            {"mainsnak": {"datavalue": {"value": {"id": "Q5" if human else "Q11424"}}}}
        ]
    }
    if image:
        claims["P18"] = [{"mainsnak": {"datavalue": {"value": f"{name}.jpg"}}}]
    return {
        "claims": claims,
        "labels": {"en": {"value": name}},
        "sitelinks": 50,
    }


class WikipediaPeopleSeedTest(unittest.TestCase):
    def test_complete_months_uses_only_finished_months(self):
        self.assertEqual(
            complete_months(4, date(2026, 9, 1)),
            [(2026, 8), (2026, 7), (2026, 6), (2026, 5)],
        )

    def test_score_rewards_sustained_popularity_over_one_spike(self):
        sustained = page_score([100_000, 100_000, 100_000, 100_000])
        spike = page_score([400_000, 0, 0, 0])
        self.assertGreater(sustained, spike)

    def test_limit_is_exact_after_human_and_exclusion_filters(self):
        pages = [
            RankedPage("A", 12, 100, 3, 30, 50),
            RankedPage("B", 11, 100, 3, 30, 50),
            RankedPage("C", 10, 200, 3, 60, 100),
            RankedPage("D", 9, 100, 3, 30, 50),
            RankedPage("E", 8, 100, 3, 30, 50),
        ]
        qids = {page.title: f"Q{index}" for index, page in enumerate(pages, start=1)}
        entities = {
            "Q1": entity("Alpha"),
            "Q2": entity("Not a human", human=False),
            "Q3": entity("No portrait", image=False),
            "Q4": entity("Excluded"),
            "Q5": entity("Echo"),
        }
        qranks = {"Q1": 200, "Q2": 500, "Q3": 300, "Q4": 400, "Q5": 100}
        selected = select_people(
            pages, qids, entities, qranks, {}, 0, 2, {"Excluded"}
        )
        self.assertEqual([person.name for person in selected], ["No portrait", "Alpha"])

        selected_with_forced_inclusion = select_people(
            pages,
            qids,
            entities,
            qranks,
            {},
            0,
            2,
            {"Excluded"},
            {"Echo"},
        )
        self.assertEqual(
            [person.name for person in selected_with_forced_inclusion],
            ["No portrait", "Echo"],
        )

        selected_by_pagerank = select_people(
            pages,
            qids,
            entities,
            qranks,
            {"Q1": 200, "Q3": 100, "Q5": 300},
            1,
            2,
            {"Excluded"},
        )
        self.assertEqual(
            [person.name for person in selected_by_pagerank], ["Echo", "Alpha"]
        )

        with_portraits = select_people(
            pages,
            qids,
            entities,
            qranks,
            {},
            0,
            2,
            {"Excluded"},
            require_image=True,
        )
        self.assertEqual([person.name for person in with_portraits], ["Alpha", "Echo"])

    def test_load_qranks_reads_only_requested_entities(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qrank.csv.gz"
            with gzip.open(path, "wt", encoding="utf-8", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(["Entity", "QRank"])
                writer.writerow(["Q1", 100])
                writer.writerow(["Q2", 50])
            self.assertEqual(load_qranks(path, {"Q2"}), {"Q2": 50})

    def test_load_pageranks_reads_only_requested_entities(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pagerank.tsv.bz2"
            with bz2.open(path, "wt", encoding="utf-8") as output:
                output.write("Q1\t1.5\nQ2\t0.5\n")
            self.assertEqual(load_pageranks(path, {"Q2"}), {"Q2": 0.5})

    def test_exclusion_file_ignores_comments_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "exclusions.txt"
            path.write_text("# reason\nAlpha\n\nBeta\n", encoding="utf-8")
            self.assertEqual(read_exclusions([path], ["Gamma"]), {"Alpha", "Beta", "Gamma"})

    def test_manual_person_is_a_deterministic_human_entity(self):
        first_qid, first_entity = manual_person("Aravind Srinivas")
        second_qid, second_entity = manual_person("Aravind Srinivas")
        self.assertEqual(first_qid, second_qid)
        self.assertEqual(first_entity, second_entity)
        self.assertTrue(first_qid.startswith("manual-"))
        self.assertEqual(
            first_entity["claims"]["P31"][0]["mainsnak"]["datavalue"]["value"]["id"],
            "Q5",
        )


if __name__ == "__main__":
    unittest.main()
