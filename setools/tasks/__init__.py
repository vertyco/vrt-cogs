from ..abc import CompositeMetaClass
from .chat import CrossChat
from .joinlog import JoinLog
from .status import StatusChannel


class SETasks(CrossChat, JoinLog, StatusChannel, metaclass=CompositeMetaClass):
    def start_tasks(self):
        self.get_chat.start()
        self.joinlogs.start()
        self.status_channel.start()

    def stop_tasks(self):
        self.get_chat.cancel()
        self.joinlogs.cancel()
        self.status_channel.cancel()
