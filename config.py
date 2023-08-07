import os
import pathlib

from typing import Optional
from pydantic import BaseSettings, SecretStr

working_dir = os.getcwd()

class Settings(BaseSettings):
    LOG_LEVEL: str = 'INFO'

    ETCD_HOST: str = '10.100.100.10'
    ETCD_PORT: int = 2379
    ETCD_CACERT: str = str(pathlib.Path(working_dir, 'ssl/ca.pem'))
    ETCD_CERT: str = str(pathlib.Path(working_dir,'ssl/lx-client.pem'))
    ETCD_KEY: str = str(pathlib.Path(working_dir, 'ssl/lx-client-key.pem'))
    ETCD_LOCK_NAME: str = 'lxd'

    RMQ_USER_ID: str = 'lxconsumer'
    RMQ_APPLCAITON: str = 'lxd-consumer'
    RMQ_CA_CERT: str = str(pathlib.Path(working_dir, 'ssl/rmq-ca.pem'))
    RMQ_CERT: str = str(pathlib.Path(working_dir, 'ssl/rmq-consumer.pem'))
    RMQ_KEY: str = str(pathlib.Path(working_dir, 'ssl/rmq-consumer-key.pem'))
    RMQ_SSL_NAME: str = 'rmq'

    RMQ_USERNAME: str
    RMQ_PASSWORD: SecretStr
    RMQ_HOST: str
    RMQ_HOST_PORT: int =  5671
    RMQ_VHOST: str = '/'
    RMQ_USER_ID: str

    NODES: dict
    PORT_RANGE: set[int] = set(range(9000, 15000))
    LXD_ENDPOINT: Optional[str] = None
    HTTPS_ENDPOINT: Optional[str] = None

    class Config:
        case_sensitive=False
        env_file = '.env'
        env_file_encoding = 'utf-8'

settings = Settings()