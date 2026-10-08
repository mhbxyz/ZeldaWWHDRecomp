"""Parser checks use declarations only, with no game input."""
import unittest
from public_sdk_index import DECL, VERIFY, symbols_header


class PublicDeclarations(unittest.TestCase):
    def test_scalar_and_pointer_return(self):
        for text, result, name in [
            ('\nstatic f32 approach(f32* p, f32 rate) {', 'f32', 'approach'),
            ('\nvoid *construct(void *self) {', 'void *', 'construct'),
        ]:
            match = DECL.search(text)
            self.assertIsNotNone(match)
            self.assertEqual(match[1].strip(), result)
            self.assertEqual(match[2], name)

    def test_member_declaration(self):
        match = DECL.search('\ns32 Actor::execute() {')
        self.assertEqual(match[1].strip(), 's32')
        self.assertEqual(match[2], 'Actor::execute')

    def test_ambiguous_symbols_keep_addresses(self):
        index = {'public_source': 'public', 'revision': 'revision',
                 'functions': [{'name': 'execute', 'address': 0x02000000},
                               {'name': 'execute', 'address': 0x02000004},
                               {'name': '&Actor::draw', 'address': 0x02000008}],
                 'unresolved_declarations': []}
        text = symbols_header(index)
        self.assertIn('WWHD_ADDR_execute_02000000 0x02000000', text)
        self.assertNotIn('#define WWHD_ADDR_execute ', text)
        self.assertIn('#define WWHD_ADDR_Actor__draw ', text)

    def test_member_verification_retains_name(self):
        match = VERIFY.search('VERIFY(0x02000000, &Actor::execute);')
        self.assertEqual(match[2], '&Actor::execute')


if __name__ == '__main__':
    unittest.main()
