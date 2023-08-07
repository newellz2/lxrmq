import os

import json
import logging
import datetime
import itertools
import pathlib

import etcd3
import jinja2
import pylxd
import nanoid

from pylxd import models
from etcd3.client import Etcd3Client
from lxrmq.models import CreateMessage, OperationMessage, OperationsEnum, InstanceStatusMessage
from lxrmq.config import settings

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')

LOGGER = logging.getLogger(__name__)

NANOID_SET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz-'

class LxdTemplateManager(object):
    template_dir: str
    container_templates: dict

    def __init__(self, template_dir="templates"):

        self.container_templates = {}
        files = []

        #Only looks for JSON templates
        for dirpath, dirnames, filenames in os.walk(template_dir):
            LOGGER.info(f'Found files in template directory: {filenames}')
            files = [f for f in filenames if 'json.j2' in f]

        for f in filenames:
            path = pathlib.Path(template_dir, f)
            with open(path, 'r') as fd:
                try:
                    json_obj = json.load(fd)
                    self.container_templates[json_obj['template']['name']] = json_obj
                except Exception as e:
                    LOGGER.info(f'Cannot load template ({f}): {e}')

    def get(self, name):
        template = self.container_templates.get(name, None)
        return template

    def render(self, name, properties):
        template = self.get(name)
        template_str = json.dumps(template)
        rendered_template = jinja2.Environment(
            loader=jinja2.BaseLoader).from_string(template_str)

        return rendered_template.render(properties)

    def render_list(self, items, properties):
        output = []

        for i in items:
            item_template = jinja2.Environment(
                loader=jinja2.BaseLoader).from_string(i)
            rendered_item = item_template.render(properties)
            output.append(rendered_item)
        return output


class LxdHost(object):
    name: str
    address: str
    instances: list[models.Instance]

    def __init__(self, **kwargs):
        self.instances = kwargs.get('instances', None)
        self.name = kwargs.get('name', None)
        self.address = kwargs.get('address', None)

    def proxy_ports(self):
        devices = [i.devices for i in self.instances]
        proxies = []
        for d in devices:
            for k, v in d.items():
                device_type = v.get('type', None)
                if device_type == 'proxy':
                    proxies.append(v)
        ports = [p['listen'].split(':')[2]
                 for p in proxies if p.startswith('tcp')]
        ports = [int(p) for p in ports]
        return ports


class LxdApi(object):
    ports: set[int]
    nodes: dict
    template_manager: LxdTemplateManager
    etcd: Etcd3Client
    lock_name: str

    ADMIN_USERS = ['lxconsumer', 'lxadmin', 'lxfrontend']


    def __init__(self, config=None):

        if config.LXD_ENDPOINT is None:
            self.client = pylxd.Client()
        else:
            pass  # TODO

        self.etcd = etcd3.client(
            host=config.ETCD_HOST,
            port=config.ETCD_PORT,
            ca_cert=config.ETCD_CACERT,
            cert_cert=config.ETCD_CERT,
            cert_key=config.ETCD_KEY
        )

        self.ports = config.PORT_RANGE
        self.nodes = config.NODES
        self.lock_name = config.ETCD_LOCK_NAME

        self.template_manager = LxdTemplateManager()

    @property
    def instances(self):
        return self.client.instances.all()

    def get(self, name):
        return self.client.instances.get(name)

    def allocated_ports(self):
        devices = [i.devices for i in self.instances]
        proxies = []
        allocated_ports = []
        for d in devices:
            for k, v in d.items():
                device_type = v.get('type', None)
                if device_type == 'proxy':
                    proxies.append(v)

        ports = [p['listen'].split(':')[2]
                 for p in proxies if p['listen'].startswith('tcp')]

        [allocated_ports.append(int(p)) for p in ports]

        return allocated_ports

    def available_ports(self):
        allocated_ports = self.allocated_ports()
        pending_ports = [int(k) for k in self.pending_ports().keys()]
        available_ports = self.ports - \
            set(allocated_ports) - set(pending_ports)

        return list(available_ports)

    def pending_ports(self):
        result = self.etcd.get('/lxd/pending_ports')

        pending_ports = None

        if result != (None, None):
            pending_ports = json.loads(result[0])
        else:
            pending_ports = {}

        return pending_ports

    def set_available_ports(self, ports):
        available_ports = self.available_ports()
        result = self.etcd.put('/lxd/available_ports',
                               json.dumps(list(available_ports)))
        return result

    def next_proxy_port(self, num=1):
        ports = []
        lock = self.etcd.lock(self.lock_name)
        lock_result = lock.acquire()

        LOGGER.info(f'next_proxy_port Lock: {lock_result}')

        available_ports = self.available_ports()
        count = len(available_ports)

        if count >= num:
            ports = list(available_ports)[:num]
            res = [self.add_pending_port(p) for p in ports]
            res = [self.remove_available_port(p) for p in ports]

        lock_result = lock.release()

        LOGGER.info(f'next_proxy_port Lock Release: {lock_result}')

        return ports

    def add_pending_port(self, port):
        # Add port to pending_ports
        now = datetime.datetime.now()
        result = self.etcd.get('/lxd/pending_ports')
        new_pending = {f'{port}': {'timestamp': now.strftime('%s')}}

        if result == (None, None):
            result = self.etcd.put('/lxd/pending_ports',
                                   json.dumps(new_pending))
        else:
            existing_pending = json.loads(result[0])
            existing_pending.update(new_pending)
            result = self.etcd.put('/lxd/pending_ports',
                                   json.dumps(existing_pending))

        return result

    def remove_available_port(self, port):
        # Remove pending port from available_ports
        result = self.etcd.get('/lxd/available_ports')
        if result == (None, None):
            result = self.etcd.put('/lxd/available_ports', json.dumps(self.available_ports()))
        else:
            available_ports = json.loads(result[0])
            if port in available_ports:
                available_ports.remove(port)
                result = self.etcd.put(
                    '/lxd/available_ports', json.dumps(available_ports))

        return result

    def remove_pending_port(self, port):
        lock = self.etcd.lock(self.lock_name)
        lock_result = lock.acquire()
        LOGGER.info(f'remove_pending_port Lock: {lock_result}')
        result = self.etcd.get('/lxd/pending_ports')

        if result == (None, None):
            self.etcd.put('/lxd/pending_ports', json.dumps({}))
        else:
            existing_pending = json.loads(result[0])
            if str(port) in existing_pending:
                del existing_pending[str(port)]
                self.etcd.put('/lxd/pending_ports',
                                json.dumps(existing_pending))
        lock_result = lock.release()
        LOGGER.info(f'remove_pending_port Lock Release: {lock_result}')

    def hosts(self):
        hosts = []
        hosts_groups = itertools.groupby(
            self.instances, key=lambda i: i.location)

        for h in hosts_groups:
            node = self.nodes.get(str(h[0]), None)
            instances = list(h[1])
            new_host = LxdHost(**node, instances=instances)
            hosts.append(new_host)

        return hosts

    def create_instance(self, config_name, properties):
        config_string = self.template_manager.render(config_name, properties)

        config = json.loads(config_string)

        instance = self.client.instances.create(config, wait=True)
        
        instance.start(wait=True)

        return instance

    def start_instance(self, instance_name):
        return self.client.instances.start(instance_name)

    def permission_check(self, operation: str, name: str, user: str):
        result = False

        if user in self.ADMIN_USERS:
            result = True
            return result
        
        LOGGER.info(f'Permission Check: {operation} {name} {user}')

        instance = self.client.instances.get(name)
        
        #Get the user env var
        instance_user = dict(instance.config).get('environment.LX_USER', None)

        if instance_user == user:
            result = True

        return result

    def handle_create_message(self, message: CreateMessage, user: str):

        environment = message.environment

        template_name = None

        if self.permission_check('create', environment.instance.name, user) is False:
            raise PermissionError('User does not have permission to create this instance')

        if environment.instance.template is None:
            template_name = f'{environment.course.subject}{environment.course.catalog_number}-{environment.course.semester}'
        else:
            template_name = environment.instance.template
        
        instance_id = nanoid.generate(NANOID_SET, 16)

        environment.instance.id = instance_id

        LOGGER.info(f'Creating instance ({environment.instance.name})')
        template = self.template_manager.get(template_name)
        ports = []

        LOGGER.info(
            f'Template ({template_name}), Content: ({template})')

        if template['template'].get('ports') is not None:
            needed_ports = template['template']['ports']
            LOGGER.info(f'Requesting ({needed_ports}) ports')
            ports = self.next_proxy_port(num=needed_ports)
            LOGGER.info(f'Received the ports: {ports}')

        context = {
            'environment': environment,
            'ports': ports
        }

        LOGGER.info(f'Creating instance with context: {context}')
        instance = self.create_instance(template_name, context)

        LOGGER.info(f'Retrieving the instance location.')
        location = settings.NODES[str(instance.location)]

        LOGGER.info(f'Instance location {location}')

        for name, device in instance.devices.items():

            if device['type'] == 'proxy':
                LOGGER.info(f'Modifying device {device}')
                items = device['listen'].split(':')
                items[1] = location['address']
                device['listen'] = ':'.join(items)
                instance.devices.update(
                    { name: device }
                )

        LOGGER.info(f'Instance Devices: {instance.devices}')
        instance.save()

        for c in template['template'].get('commands', []):
            command = self.template_manager.render_list(c, context)
            LOGGER.info(f'Running command: {command}')
            result = instance.execute(command)
            LOGGER.info(f'Command result: {result}')


        [ self.remove_pending_port(p) for p in ports ]

        environment.instance.location = location['name']
        environment.instance.devices = instance.devices
        environment.instance.status = ''

        return environment


    def handle_operation_message(self, message: OperationMessage, user: str):

        LOGGER.info(f'Handling ({message.json()})')

        if self.permission_check(message.operation, message.instance, user) is False:
            raise PermissionError('User does not have permission to perform this operation')

        LOGGER.info(f'Handling ({message.operation}) for instance ({message.instance})')

        instance: models.Instance = self.client.instances.get(message.instance)

        if message.operation not in [OperationsEnum.restart, OperationsEnum.status]:
            raise ValueError('Invalid operation')

        if message.operation == OperationsEnum.restart:
            instance.restart(wait=True)

        response = {
            'id': instance.config['environment.LX_INSTANCE_ID'],
            'type': 'instance_status',
            'name': instance.name,
            'status': instance.state().status,
            'environment': {
                'id': instance.config['environment.LX_ENV_ID'],
            }
        }

        return response
