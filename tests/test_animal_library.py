import hashlib
import unittest
from pathlib import Path
from backend.media import LocalAnimalLibrary

class AnimalLibraryTests(unittest.TestCase):
    def test_named_animal_cannot_be_replaced_by_theme_matches(self):
        library=LocalAnimalLibrary()
        for query,name in [('北极熊的保护色','北极熊'),('章鱼怎样隐藏','章鱼'),('兰花螳螂为什么像花','兰花螳螂'),('比目鱼的伪装','比目鱼')]:
            items=library.search(query)
            self.assertGreaterEqual(len(items),2)
            self.assertTrue(all(item['species_zh']==name for item in items),(query,items))
        self.assertEqual(library.search('长颈鹿的保护色'),[])
    def test_comparison_can_return_both_requested_animals(self):
        names={i['species_zh'] for i in LocalAnimalLibrary().search('北极熊和北极狐的保护色')}
        self.assertEqual(names,{'北极熊','北极狐'})
    def test_expanded_photos_and_attribution_are_present(self):
        entries=LocalAnimalLibrary().all_entries()
        self.assertGreaterEqual(len(entries),44)
        for entry in entries:
            credit=entry['credit'];self.assertTrue(credit['author']);self.assertTrue(credit['license_url'])
            self.assertTrue(credit['source_url'].startswith('https://commons.wikimedia.org/'))
            file=Path('assets/animals')/entry['file']
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),credit['sha256'])
