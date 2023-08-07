# -*- coding: utf-8 -*-
# pylint: disable=C0111,C0103,R0205
import logging
import time
import json

import pika
from pika import spec as pika_spec
from pika import channel as pika_channel
from pika.exchange_type import ExchangeType

from lxrmq import models
from lxrmq.consumers.base import BaseConsumer, BaseReconnectingConsumer

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
LOGGER = logging.getLogger(__name__)

JSON_CONTENT_TYPE = 'application/json'

class LxdApiConsumer(BaseConsumer):
    """
    RMQ consumer for manipulating LXD containers.
    """
    EXCHANGE = 'lx'
    EXCHANGE_TYPE = ExchangeType.topic
    QUEUE = 'lx.api-queue'
    ROUTING_KEY = 'lx.api'
    
    CREATE_ROUTING_KEY = 'lx.simple'

    def __init__(self, parameters, lxdapi):
        super().__init__(parameters)
        self._lxdapi = lxdapi


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
  
        LOGGER.info('Received message # %s from %s:%s: %s',
                    properties.reply_to, properties.app_id, properties.user_id, body)

        headers: models.MessageHeaders = None
        result = None

        #Check headers
        try:
            headers = models.MessageHeaders.parse_obj(properties.headers)            
        except Exception as e:
            result = e
            LOGGER.info(f'Headers Exception: {e}, Type({type(e)})')
            self.send_error(
                {'type' : f'{type(e).__name__}', 'message': str(e)},
                properties.reply_to,
                properties.correlation_id
                )
            self.acknowledge_message(basic_deliver.delivery_tag)
            return

        LOGGER.info(f'Message Type: {headers.x_type}')

        if properties.content_type != JSON_CONTENT_TYPE:
            LOGGER.info(f'Message content-type not a valid.')
            self.send_error('Not a valid content-type.', properties.reply_to, properties.correlation_id)
            self.acknowledge_message(basic_deliver.delivery_tag)
            return

        #Create
        if headers.x_type == 'create':
            try:
                self.handle_create_message(body, headers, properties)
            except Exception as e:
                LOGGER.info(f'Failed to create instance: {e}')
                result = e
                
        #Operation
        if headers.x_type == 'operation':
            LOGGER.info(f'Performing instance operation.')
            try:
                self.handle_operation_message(body, headers, properties)
            except Exception as e:
                result = e

        if isinstance(result, Exception):
            LOGGER.info(f'Exception: {result}')
            self.send_error(
                    {'type' : f'{type(result).__name__}', 'message': str(result)},
                    properties.reply_to,
                    properties.correlation_id
                    )

        self.acknowledge_message(basic_deliver.delivery_tag)

    def handle_create_message(self, body: bytes, headers: models.MessageHeaders, properties: pika_spec.BasicProperties):
        message = models.CreateMessage.parse_raw(body)
        result = self._lxdapi.handle_create_message(message, properties.user_id)

        LOGGER.info(f'Create completed: {result}')
        create_message = models.CreateMessage(environment=result)

        self.send_response(create_message.json(), properties.reply_to, properties.correlation_id)
        self.send_message(create_message.json(), self.CREATE_ROUTING_KEY, 'instance-creation', self.EXCHANGE)

        return result


    def handle_operation_message(self, body: bytes, headers: models.MessageHeaders, properties: pika_spec.BasicProperties):
        message = models.OperationMessage.parse_raw(body)
        result = self._lxdapi.handle_operation_message(message, headers.x_user)

        LOGGER.info(f'Operation completed: {result}')
        
        self.send_response(result, properties.reply_to, properties.correlation_id)

        return result


class ReconnectingLxdApiConsumer(BaseReconnectingConsumer):

    def __init__(self, parameters, lxdapi):
        super().__init__(parameters)
        self._lxdapi = lxdapi
        self._consumer = LxdApiConsumer(self._parameters, self._lxdapi)

    def _maybe_reconnect(self):
        if self._consumer.should_reconnect:
            self._consumer.stop()
            reconnect_delay = self._get_reconnect_delay()
            LOGGER.info('Reconnecting after %d seconds', reconnect_delay)
            time.sleep(reconnect_delay)
            self._consumer = LxdApiConsumer(self._parameters, self._lxdapi)
