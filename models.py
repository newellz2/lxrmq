from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class ProxySocket(BaseModel):
    ipaddress: str
    port: str

class Proxy(BaseModel):
    name: str
    listen: ProxySocket
    connect: ProxySocket

class Instance(BaseModel):
    id: Optional[str]
    name: str
    type: str
    status: Optional[str]
    control: Optional[bool]
    location: Optional[str]
    template: Optional[str]
    devices: Optional[dict]
    config: Optional[dict]
    services: Optional[list[dict]]

    def get_listen_address(self, name):
        proxies = [ v for k,v in self.devices.items() if k == name]
        proxy = None
        
        if len(proxies) > 0:
            proxy = proxies[0]

        if proxy:
            if proxy["listen"].startswith("tcp:"):
                return proxy["listen"].split(":",1)[1]
        
        return None

class User(BaseModel):
    id: str
    uid_number: str
    username: str

class Course(BaseModel):
    catalog_number: Optional[str]
    semester: Optional[str]
    subject: Optional[str]

class Environment(BaseModel):
    id: str
    name: str
    type: str
    instance: Instance
    user: User
    course: Optional[Course]

class CreateMessage(BaseModel):
    environment: Environment

class OperationsEnum(Enum):
    start = "start"
    stop = "stop"
    restart = "restart"
    status = "status"
    command = "command"

class OperationMessage(BaseModel):
    username: str
    instance: str
    operation: OperationsEnum

class EnvironmentStatus(BaseModel):
    id: str

class InstanceStatusMessage(BaseModel):
    id: str
    status: str
    name:str
    type: str
    environment: EnvironmentStatus


class CommandMessage(BaseModel):
    username: str
    instance: str
    command: list[str]

class MessageTypeEnum(Enum):
    create = "create"
    operation = "operation"
    command = "command"
    error = "error"
    response = "response"
    instance_creation = "instance-creation"
    environment_creation = "environment-creation"

class MessageHeaders(BaseModel):
    x_type: MessageTypeEnum = Field(alias='x-type')
    x_user: str= Field(alias='x-user')
    x_source: str= Field(alias='x-source')
    x_application: str= Field(alias='x-application')

    class Config:  
        use_enum_values = True 
        allow_population_by_field_name = True