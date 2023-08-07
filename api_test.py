import unittest
import types
import pylxd

import etcd3.leases as leases
import etcd3.exceptions as exceptions
from etcd3.client import KVMetadata

from unittest import mock

from api import LxdApi
from config import Settings

import models


class TestLxdApi(unittest.TestCase):

    @mock.patch('etcd3.client.Etcd3Client', autospec=True)
    def test_lxd_container_provisioner_none_success(self, mock_etcd3):

        etcd = mock_etcd3.return_value
        etcd.get.return_value = (None, None)

        settings = Settings()
        api = LxdApi(config=settings)

        pending_ports = api.pending_ports()

        self.assertEqual(pending_ports, {})

    @mock.patch('etcd3.client.Etcd3Client', autospec=True)
    def test_lxd_container_provisioner_exception_success(self, mock_etcd3):

        etcd = mock_etcd3.return_value
        etcd.get.side_effect = exceptions.Etcd3Exception()
        etcd.get.return_value = (None, None)

        settings = Settings()
        api = LxdApi(config=settings)

        exception = None
        try:
            pending_ports = api.pending_ports()
        except exceptions.Etcd3Exception as e:
            exception = e

        self.assertEqual(type(exception), exceptions.Etcd3Exception)

    @mock.patch('etcd3.client.Etcd3Client', autospec=True)
    def test_pending_ports_dict_sucess(self, mock_etcd3):

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
        etcd.get.return_value = (
            '{ "9000": {"timestamp": "1686799510"} }', meta)

        settings = Settings()
        api = LxdApi(config=settings)

        pending_ports = api.pending_ports()

        self.assertEqual(pending_ports, {"9000": {"timestamp": "1686799510"}})

    @mock.patch('etcd3.client.Etcd3Client', autospec=True)
    def test_hosts_sucess(self, mock_etcd3):

        settings = Settings()
        api = LxdApi(config=settings)

        hosts = api.hosts()

        local = hosts[0]

        self.assertEqual(local.name, 'localhost')

    @mock.patch('pylxd.Client', autospec=True)
    @mock.patch('etcd3.client.Etcd3Client', autospec=True)
    def test_handle_create_message_success(self, mock_etcd3, mock_client):

        etcd = mock_etcd3.return_value
        client = mock_client.return_value

        client.instances = mock.MagicMock()

        mock_instance = mock.MagicMock(spec=pylxd.models.Instance)
        mock_instance.name = 'mock_instance'
        mock_instance.status = 'Running'
        mock_instance.location = None
        mock_instance.devices = {'novnc': {'connect': 'tcp:127.0.0.1:5801',
                                           'listen': 'tcp:127.0.0.1:9000',
                                           'type': 'proxy'},
                                 'ttyd': {'connect': 'tcp:127.0.0.1:7681',
                                          'listen': 'tcp:127.0.0.1:9001',
                                          'type': 'proxy'},
                                 'vscode': {'connect': 'tcp:127.0.0.1:3300',
                                            'listen': 'tcp:127.0.0.1:9002',
                                            'type': 'proxy'}}
        client.instances.create.return_value = mock_instance

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
        etcd.get.return_value = ('{}', meta)

        settings = Settings()
        api = LxdApi(config=settings)

        message = models.CreateMessage.parse_obj({
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

        result = api.handle_create_message(message)

        self.assertEqual(result.instance.devices['novnc'], {'connect': 'tcp:127.0.0.1:5801','listen': 'tcp:127.0.0.1:9000','type': 'proxy'})


    @mock.patch('pylxd.Client', autospec=True)
    @mock.patch('etcd3.client.Etcd3Client', autospec=True)
    def test_handle_operations_message_restart_success(self, mock_etcd3, mock_client):
        etcd = mock_etcd3.return_value

        client = mock_client.return_value
        client.instances = mock.MagicMock()

        mock_instance = mock.MagicMock(spec=pylxd.models.Instance)
        mock_instance.name = 'cs135-f23-user0'
        mock_instance.status = 'Running'
        mock_instance.location = None
        mock_instance.devices = {'novnc': {'connect': 'tcp:127.0.0.1:5801',
                                           'listen': 'tcp:127.0.0.1:9000',
                                           'type': 'proxy'},
                                 'ttyd': {'connect': 'tcp:127.0.0.1:7681',
                                          'listen': 'tcp:127.0.0.1:9001',
                                          'type': 'proxy'},
                                 'vscode': {'connect': 'tcp:127.0.0.1:3300',
                                            'listen': 'tcp:127.0.0.1:9002',
                                            'type': 'proxy'}}
        mock_instance.state.return_value = { 'status_code': 103, 'status': 'Running' , 'pid': 1234}
        client.instances.get.return_value = mock_instance


        message = models.OperationMessage.parse_obj({
            'username': 'user0',
            'instance': 'cs135-f23-user0',
            'operation': 'restart'
        })

        settings = Settings()
        api = LxdApi(config=settings)
        result = api.handle_operation_message(message)

        self.assertEqual(result['status'], 'Running')



if __name__ == '__main__':
    unittest.main()
