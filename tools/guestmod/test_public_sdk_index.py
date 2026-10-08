"""Parser checks use declarations only, with no game input."""
import unittest
from public_sdk_index import DECL, VERIFY, symbols_header
from public_sdk_layouts import layout
from public_sdk_bindings import bindings, guest_type


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

    def test_layout_omits_nested_and_unknown_fields(self):
        text = """struct Actor {
          struct Inner { /* 0x0 */ be<u32> wrong; };
          /* 0x4 */ be<f32> speed;
          /* 0x8 */ Unknown compound;
          /* 0xC */ gptr<Other> owner;
        }; WWHD_SIZE(Actor, 0x10);"""
        output = layout(text, 'Actor')
        self.assertIn('f32 speed', output)
        self.assertIn('u32 owner', output)
        self.assertIn('__builtin_offsetof(Actor, speed) == 0x4', output)
        self.assertNotIn('wrong', output)
        self.assertNotIn('compound', output)

    def test_unsupported_signature_is_reported(self):
        index = {'revision': 'public', 'functions': [
            {'name': 'execute', 'address': 0x02000000, 'return': 'BOOL',
             'parameters': 'Actor* self, f32 scale'},
            {'name': 'vector', 'address': 0x02000004, 'return': 'UnknownValue',
             'parameters': ''}]}
        text, skipped = bindings(index)
        self.assertIn('s32, wwhd_execute_02000000, (void* self, f32 scale)', text)
        self.assertEqual([f['name'] for f in skipped], ['vector'])
        self.assertEqual(guest_type('bool*'), 'u8*')

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
