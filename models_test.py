import unittest
from unittest import mock

from lxrmq import models

class TestModels(unittest.TestCase):
    def test_instance_get_listen_address(self):
        instance = models.Instance.parse_obj({
            'name': 'cs135-f23-user0',
            'type': 'container',
            'devices': {
                'novnc': {'connect': 'tcp:127.0.0.1:5801',
                                   'listen': 'tcp:100.64.0.1:9000',
                                   'type': 'proxy'
                                   },
                'vscode': {'connect': 'tcp:127.0.0.1:3300',
                                   'listen': 'tcp:100.64.0.1:9001',
                                   'type': 'proxy'
                                   },
                'ttyd': {'connect': 'tcp:127.0.0.1:3300',
                                   'listen': 'tcp:100.64.0.1:9002',
                                   'type': 'proxy'
                                   }
            }
        })

        listen_address = instance.get_listen_address('novnc')

        self.assertEqual(listen_address, '100.64.0.1:9000')

        listen_address = instance.get_listen_address('vscode')

        self.assertEqual(listen_address, '100.64.0.1:9001')

        listen_address = instance.get_listen_address('ttyd')

        self.assertEqual(listen_address, '100.64.0.1:9002')

if __name__ == '__main__':
    runner = unittest.TextTestRunner(warnings=None)
    unittest.main(testRunner=runner)
