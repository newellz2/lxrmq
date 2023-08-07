# -*- coding: utf-8 -*-
# pylint: disable=C0111,C0103,R0205
import ssl
import functools
import datetime
import logging
import time
import json
import uuid
import os
import pathlib
import subprocess
import re

import pika
import pydantic
import jinja2

from .. import models

import pika
from pika import spec as pika_spec
from pika import channel as pika_channel
from pika.exchange_type import ExchangeType

from ..config import settings
from .base import BaseConsumer, BaseReconnectingConsumer

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

JSON_CONTENT_TYPE = 'application/json'

WORKING_DIR = os.getcwd()


class LxdSimpleInstanceCreationConsumer(BaseConsumer):
    """
    RMQ consumer for manipulating LXD containers.
    """
    EXCHANGE = 'lx'
    EXCHANGE_TYPE = ExchangeType.topic
    QUEUE = 'lx.simple-queue'
    ROUTING_KEY = 'lx.simple'
    APACHE2_CONF_DIR = '/etc/apache2/sites-enabled/conf'
    TEMPLATE_DIR = str(pathlib.Path(WORKING_DIR, 'templates'))
    TEMPLATES = {
        'cs135-f23': 'cs135-apache2.conf.j2'
    }

    def __init__(self, parameters):
        super().__init__(parameters)

        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader("templates"),
            autoescape=jinja2.select_autoescape()
        )

        templates = self._env.list_templates()

        LOGGER.info(f'Listing templates {templates}')

    def on_message(self, _unused_channel: pika_channel.Channel,
                   basic_deliver: pika_spec.Basic.Deliver,
                   properties: pika.BasicProperties,
                   body: bytes):
        """Invoked by pika when a message is delivered from RabbitMQ. 

        :param pika.channel.Channel _unused_channel: The channel object
        :param pika.Spec.Basic.Deliver: basic_deliver method
        :param pika.Spec.BasicProperties: properties
        :param bytes body: The message body

        """

        LOGGER.info('Received message from %s: %s',
                    properties.reply_to, body)

        LOGGER.info(f'Received headers: {properties.headers}')
        try:
            headers = models.MessageHeaders.parse_obj(properties.headers)

            if headers.x_type == 'instance-creation':
                LOGGER.info('Parsing instance creation message')
                message = models.CreateMessage.parse_raw(body)

                env = message.environment

                if env.type == 'simple':
                    LOGGER.info(
                    f'Instance Creation Message: Env.id={env.id} Inst.id={env.instance.id} Course={env.course}')
                    ttyd_address = env.instance.get_listen_address('ttyd')
                    vscode_address = env.instance.get_listen_address('vscode')
                    novnc_address = env.instance.get_listen_address('novnc')

                    env.instance.services = [
                        {'display_name': 'Terminal', 'name':'ttyd', 'address': f'{settings.HTTPS_ENDPOINT}/{env.id}/ttyd/'},
                        {'display_name': 'Visual Studio Code', 'name':'vscode', 'address': f'{settings.HTTPS_ENDPOINT}/{env.id}/vscode/'},
                        {'display_name': 'Desktop', 'name':'novnc', 'address': f'{settings.HTTPS_ENDPOINT}/{env.id}/novnc/vnc.html?path={env.id}/novnc/websockify&autoconnect=true&resize=remote&quality=8&compression=2'}
                    ]

                    context = {
                        'env_id': env.id,
                        'novnc_address': novnc_address,
                        'vscode_address': vscode_address,
                        'ttyd_address': ttyd_address,
                        'username': env.user.username
                    }

                    template = self._env.get_template('simple-apache2.conf.j2')
                    rendered_template = template.render(context)

                    output_file = pathlib.Path(
                        self.APACHE2_CONF_DIR, f'{env.id}.conf')
                    
                    with open(output_file, 'w') as f:
                        f.write(rendered_template)

                    subprocess.run(
                        'sudo /usr/sbin/apache2ctl graceful', shell=True)
                    
                    LOGGER.info(
                        f'Rendered template ({template}) to ({output_file})')
                    
                    env.instance.control = True

                    outbound_message = models.CreateMessage(environment=env)
                    
                    self.send_message(outbound_message.json(), 'lx.db','environment-creation', 'lx')
        except Exception as e:
            LOGGER.error(f'Exception: {e}')

        self.acknowledge_message(basic_deliver.delivery_tag)


class ReconnectingLxdSimpleInstanceCreationConsumer(BaseReconnectingConsumer):
    """
    This consumer reconnects if it encounters an exception.
    """

    def __init__(self, parameters):
        super().__init__(parameters)
        self._consumer = LxdSimpleInstanceCreationConsumer(self._parameters)

    def _maybe_reconnect(self):
        if self._consumer.should_reconnect:
            self._consumer.stop()
            reconnect_delay = self._get_reconnect_delay()
            LOGGER.info('Reconnecting after %d seconds', reconnect_delay)
            time.sleep(reconnect_delay)
            self._consumer = LxdSimpleInstanceCreationConsumer(
                self._parameters)
