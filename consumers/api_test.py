import logging
import json
import datetime
import types

import unittest
from unittest import mock

import etcd3.leases as leases
import etcd3.exceptions as exceptions
from etcd3.client import KVMetadata

import pika
from api import LxdApiConsumer
from lxrmq import models

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)


class TestLxdApiConsumer(unittest.TestCase):

    def __inti__(self):
        super().__init__()

    def setup_mock_consumer(self, mock_aioconn, mock_lxdapi):
        lxdapi = mock_lxdapi.return_value
        parameters = pika.ConnectionParameters('localhost', '5671', '/')

        mock_channel = mock.Mock()
        mock_channel.basic_ack = mock.Mock()

        consumer = LxdApiConsumer(parameters, lxdapi)
        consumer._channel = mock_channel
        consumer.send_error = mock.Mock()
        consumer.send_message = mock.Mock()
        consumer.send_response = mock.Mock()

        return (consumer, lxdapi)

    @mock.patch('lxrmq.api.LxdApi', autospec=True)
    @mock.patch('pika.adapters.asyncio_connection.AsyncioConnection', autospec=True)
    def test_on_message_validation_error(self, mock_aioconn, mock_lxdapi):

        consumer, lxdapi = self.setup_mock_consumer(mock_aioconn, mock_lxdapi)
        lxdapi.handle_create_message.return_value = None

        # Mock Delivery
        mock_deliver = mock.Mock()
        mock_deliver.routing_key = 'test_queue'
        mock_deliver.body = b'Test message'
        mock_deliver.delivery_tag = 12345
        mock_deliver.consumer_tag = 'consumer_tag'
        mock_deliver.exchange = 'exchange'
        mock_deliver.redelivered = False
        mock_deliver.delivery_mode = 1

        # Properties
        properties = pika.BasicProperties(reply_to='example')

        body = b'Bad Input'

        result = consumer.on_message(None, mock_deliver, properties, body)

        args, kwargs = consumer.send_error.call_args

        self.assertEqual(args[0].get('error_type'), 'ValidationError')

    @mock.patch('etcd3.client.Etcd3Client', autospec=True)
    @mock.patch('lxrmq.api.LxdApi', autospec=True)
    @mock.patch('pika.adapters.asyncio_connection.AsyncioConnection', autospec=True)
    def test_create_instance_success(self, mock_aioconn, mock_lxdapi, mock_etcd3):

        consumer, lxdapi = self.setup_mock_consumer(mock_aioconn, mock_lxdapi)
        
        etcd = mock_etcd3.return_value

        l = leases.Lease(100, 1)

        kvm = types.SimpleNamespace()
        kvm.key = b'/lxd/pending_ports'
        kvm.create_revision = 3350
        kvm.mod_revision = 3379
        kvm.version = 15
        kvm.lease = l

        header = types.SimpleNamespace()
        header.cluster_id = 14841639068965178418
        header.member_id = 10276657743932975437
        header.revision = 3392
        header.raft_term = 25

        meta = KVMetadata(kvm, header)
        etcd.get.return_value = ('{ "9000": {"timestamp": "1686799510"} }', meta)

        create_message = json.dumps({
            'environment': {
                'id': f'000000010',
                'name': 'CS135',
                'type': 'simple',
                'instance': {
                    'name': 'cs135-f23-user0',
                    'type': 'container',
                },
                'user': {
                    'id': '000000001',
                    'username': 'user0',
                    'uid_number': 1000000
                },
                'course': {
                    'subject': 'cs',
                    'catalog_number': '135',
                    'semester': 'f23'
                }
            }
        })

        # Mock Delivery
        mock_deliver = mock.Mock()
        mock_deliver.routing_key = 'test_queue'
        mock_deliver.body = create_message
        mock_deliver.delivery_tag = 12345
        mock_deliver.consumer_tag = 'consumer_tag'
        mock_deliver.exchange = 'lx'
        mock_deliver.redelivered = False
        mock_deliver.delivery_mode = 1

        # Properties
        properties = pika.BasicProperties(
            user_id='lxconsumer',
            content_type='application/json',
            reply_to='amq.rabbitmq.reply-to',
            correlation_id='correlation_id',
            timestamp=int(datetime.datetime.now().strftime('%s')),
            headers={
                'x-type': 'create',
                'x-application': 're-enroll',
                'x-user': 'newellz2',
                'x-source': 'host'
            }
        )

        message = models.CreateMessage.parse_obj({
            'environment': {
                'id': f'000000010',
                'name': 'CS135',
                'type': 'simple',
                'instance': {
                    'id': '000000010',
                    'name': 'cs135-f23-user0',
                    'type': 'container',
                    'devices': {'novnc': {'connect': 'tcp:127.0.0.1:5801',
                                           'listen': 'tcp:127.0.0.1:9000',
                                           'type': 'proxy'},
                                 'ttyd': {'connect': 'tcp:127.0.0.1:7681',
                                          'listen': 'tcp:127.0.0.1:9001',
                                          'type': 'proxy'},
                                 'vscode': {'connect': 'tcp:127.0.0.1:3300',
                                            'listen': 'tcp:127.0.0.1:9002',
                                            'type': 'proxy'}}
                },
                'user': {
                    'id': '000000001',
                    'username': 'user0',
                    'uid_number': 1000000
                },
                'course': {
                    'subject': 'cs',
                    'catalog_number': '135',
                    'semester': 'f23'
                }
            }
        })
    

        lxdapi.handle_create_message.return_value = message

        # result = consumer.on_message(None, mock_deliver, properties, body)
        result = consumer.handle_create_message(create_message, properties)

        args, kwargs = consumer.send_message.call_args

        self.assertEqual(args[0].environment.id, '000000010')

if __name__ == '__main__':
    runner = unittest.TextTestRunner(warnings=None)
    unittest.main(testRunner=runner)
