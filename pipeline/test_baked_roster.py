import json
import os
import tempfile
import unittest

from pipeline.baked_roster import publish_character


class BakedRosterTest(unittest.TestCase):
    def test_publish_validates_outputs_and_appends_once(self):
        with tempfile.TemporaryDirectory() as root:
            slug = "newcomer"
            ui_root = os.path.join(root, "play", "ui", slug)
            os.makedirs(ui_root)
            with open(os.path.join(root, "play", f"{slug}.osb6"), "wb") as output:
                output.write(b"bundle")
            for name in ("portrait_raw.png", "portrait_tile.png", "portrait_medium.png",
                         f"{slug}.osbui", "announcer.wav"):
                with open(os.path.join(ui_root, name), "wb") as output:
                    output.write(b"asset")
            with open(os.path.join(ui_root, "character.json"), "w", encoding="utf-8") as output:
                json.dump({"display": "Newcomer"}, output)
            manifest_path = os.path.join(root, "characters.json")
            with open(manifest_path, "w", encoding="utf-8") as output:
                json.dump([{"slug": "queen"}], output)

            self.assertTrue(publish_character(slug, root, manifest_path))
            self.assertFalse(publish_character(slug, root, manifest_path))
            with open(manifest_path, encoding="utf-8") as source:
                self.assertEqual(json.load(source), [{"slug": "queen"}, {"slug": slug}])


if __name__ == "__main__":
    unittest.main()
