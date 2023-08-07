#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=C0111,C0103,R0205
import os
import ssl
import functools
import datetime
import logging
import uuid
import json
import time
import pika
import sys



def on_client_rx_reply_from_server(ch, method_frame, properties, body):
    headers = properties.headers

    if headers.get('x_type', None) == 'error':
        print(f'Server Error: {body}')
        return

    if headers.get('x_type') == 'response':
        instance = None
        
        try:
            instance = json.loads(body)
        except Exception as e:
            print(f'Error: {e}')
        
        headers = properties.headers
        
        if instance:
            print(instance)
    ch.close()


def main():

    context = ssl.create_default_context(
        cafile="ca.pem")
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = False
    context.load_cert_chain("cert.pem",
                            "key.pem")
    ssl_options = pika.SSLOptions(context, "server")
    credentials = pika.PlainCredentials('user', 'password')

    parameters = pika.ConnectionParameters('host',
                                           5671,
                                           '',
                                           credentials=credentials,
                                           ssl_options=ssl_options)

    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.basic_consume('amq.rabbitmq.reply-to',
                          on_client_rx_reply_from_server,
                          auto_ack=True)


    #135
    correlation_id = uuid.uuid4()
    timestamp = datetime.datetime.now()
    hostname = os.uname().nodename

    props = pika.BasicProperties(
        user_id='user',
        content_type='application/json',
        reply_to='amq.rabbitmq.reply-to',
        correlation_id=str(correlation_id),
        timestamp=int(timestamp.strftime('%s')),
        headers={
            'x-type': 'create',
            'x-application': 'basic-provisioner',
            'x-user': 'username',
            'x-source': hostname
        }
    )


    create_message = json.dumps({
            'environment': {
                'id': f'00000000',
                'name': 'Example',
                'type': 'simple',
                'instance': {
                    'name': 'example-username',
                    'type': 'container',
                },
                'user': {
                    'id': '0000001',
                    'username': 'username',
                    'uid_number': 1000000
                },
                'course': {
                    'subject': 'EX',
                    'catalog_number': '100',
                    'semester': 'f23'
                }
            }
        })

    channel.basic_publish(
        exchange='lx',
        routing_key='lx.api',
        properties=props,
        body=create_message
    )

    #channel.start_consuming()


if __name__ == '__main__':
    main()
