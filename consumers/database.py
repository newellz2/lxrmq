# -*- coding: utf-8 -*-
# pylint: disable=C0111,C0103,R0205
import logging
import time
import json

from .. import models

import pika
from pika import spec as pika_spec
from pika import channel as pika_channel
from pika.exchange_type import ExchangeType

from ..config import settings
from .base import BaseConsumer, BaseReconnectingConsumer

from reenrolldb.database import  SessionLocal
from reenrolldb.models import User, Environment

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

JSON_CONTENT_TYPE = 'application/json'

class LxdEnvDatabaseConsumer(BaseConsumer):
    """
    RMQ consumer for manipulating LXD containers.
    """
    EXCHANGE = 'lx'
    EXCHANGE_TYPE = ExchangeType.topic
    QUEUE = 'lx.db-queue'
    ROUTING_KEY = 'lx.db'


    def __init__(self, parameters):
        super().__init__(parameters)
        
        self.session = SessionLocal()

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
        
            if headers.x_type == 'environment-creation':

                LOGGER.info('Parsing instance environment message')

                message = models.CreateMessage.parse_raw(body)
                env = message.environment

                LOGGER.info(f'Environment {env.id}')

                #Find User
                user = self.session.query(User).filter(User.id==env.user.id).first()
                
                if user is not None:
                    LOGGER.info(f'Found user: ({user.id}:{user.username}) ')

                #Find Env

                LOGGER.info(f'Search for environment: ({env.id}) ')
                db_env = self.session.query(Environment).filter(Environment.id==env.id).first()

                if db_env is None:
                    LOGGER.info(f'Creating new Environment: ({ env.id }) ')
                    new_env = Environment()
                    new_env.id = env.id
                    new_env.user = user
                    new_env.document = env.json()
                    self.session.add(new_env)
                    self.session.commit()
                else:
                    db_env.document = env.json()
                    self.session.add(db_env)
                    self.session.commit()
                    LOGGER.info(f'Environment already exists: ({env.id}) ')

        except Exception as e:
            LOGGER.error(f'Error: {e}')

        self.acknowledge_message(basic_deliver.delivery_tag)


class ReconnectingLxdEnvDatabaseConsumer(BaseReconnectingConsumer):
    """
    This consumer reconnects if it encounters an exception.
    """

    def __init__(self, parameters):
        super().__init__(parameters)
        self._consumer = LxdEnvDatabaseConsumer(self._parameters)


    def _maybe_reconnect(self):
        if self._consumer.should_reconnect:
            self._consumer.stop()
            reconnect_delay = self._get_reconnect_delay()
            LOGGER.info('Reconnecting after %d seconds', reconnect_delay)
            time.sleep(reconnect_delay)
            self._consumer = LxdEnvDatabaseConsumer(self._parameters)